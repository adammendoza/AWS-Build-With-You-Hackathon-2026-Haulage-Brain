"""Model-backed conversation; deterministic routing remains the calculation authority."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .inference import InferenceError, ParasailInference
from .spooky_brain import TOWNS, request_options

CONSTRAINTS = {
    'date', 'base', 'return_by', 'objective', 'start_time', 'vehicle_ids',
    'exclude_towns', 'max_empty_miles', 'max_driving_hours', 'source',
}


def history_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 12:
        raise ValueError('Conversation must contain at most 12 messages.')
    messages = []
    for item in value:
        if not isinstance(item, dict) or item.get('role') not in {'user', 'assistant'}:
            raise ValueError('Conversation roles must be user or assistant.')
        content = item.get('content')
        if not isinstance(content, str) or len(content) > 2000:
            raise ValueError('Conversation messages must be text under 2,000 characters.')
        messages.append({'role': item['role'], 'content': content})
    return messages


async def respond(
    body: dict[str, Any], fleet: dict, calculate: Callable[[dict], dict],
    inference=None,
) -> dict[str, Any]:
    prompt = body.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
        raise ValueError('Enter a dispatch request under 2,000 characters.')
    history = history_messages(body.get('history', []))
    current = {k: v for k, v in body.items() if k in CONSTRAINTS}
    current.update(request_options(dict(current, prompt='')))
    current.setdefault('source', 'demo')
    for key, value in dict(start_time='06:00', vehicle_ids=[], exclude_towns=[],
                           max_empty_miles=None, max_driving_hours=9).items():
        current.setdefault(key, value)
    client = inference if inference is not None else ParasailInference()
    manifest = [dict(vehicle_id=v['vehicle_id'], vehicle_type=v['vehicle_type'],
                     base=v.get('base') or v['location']) for v in fleet['vehicles']]
    intent = await client.dispatch_intent({
        'request': prompt, 'conversation': history, 'current_constraints': current,
        'reference_date': datetime.now(ZoneInfo('Europe/London')).date().isoformat(),
        'supported_towns': sorted(TOWNS), 'fleet': manifest,
        'source_options': ['demo', 'loadboard'],
    })
    if not isinstance(intent, dict) or intent.get('action') not in {'plan', 'clarify', 'explain'}:
        raise InferenceError('Parasail returned an invalid dispatch action. Please retry.')
    if not isinstance(intent.get('message'), str) or not intent['message'].strip():
        raise InferenceError('Parasail returned an empty dispatch response. Please retry.')
    unsupported = intent.get('unsupported', [])
    if not isinstance(unsupported, list) or any(not isinstance(v, str) for v in unsupported):
        raise InferenceError('Parasail returned invalid unsupported requirements. Please retry.')
    metadata = dict(provider='Parasail', model=client.model, usage=client.usage())
    if intent['action'] == 'clarify' or unsupported:
        return dict(type='clarification', message=intent['message'][:1200],
                    unsupported=unsupported[:10], ai=metadata)
    proposed = current
    if intent['action'] == 'plan':
        constraints = intent.get('constraints')
        if not isinstance(constraints, dict) or set(constraints)-CONSTRAINTS:
            raise InferenceError('Parasail returned unsupported constraint fields. Please retry.')
        proposed = dict(current, **constraints)
    try:
        validated = request_options(dict(proposed, prompt=''))
        unknown_ids = set(validated.get('vehicle_ids', [])) - {v['vehicle_id'] for v in fleet['vehicles']}
        if unknown_ids:
            raise ValueError('One of the requested vehicles is not in this fleet.')
        result = calculate(dict(validated, source=proposed.get('source', 'demo'), prompt=''))
    except (ValueError, TypeError) as exc:
        return dict(type='clarification', message=f'I need to adjust that request: {exc}', ai=metadata)
    # Explain only the verified result, rather than letting the model invent routes or arithmetic.
    try:
        narration = await client.explain_dispatch({
            'request': prompt, 'conversation': history[-6:], 'plan': result,
        })
        if not isinstance(narration, dict) or not isinstance(narration.get('message'), str) or not narration['message'].strip():
            raise InferenceError('Parasail returned an empty plan explanation.')
        answer = narration['message'][:1600]
        narration_error = None
    except InferenceError:
        summary = result['summary']
        answer = (f"I calculated {summary['matched_loads']} loads across {summary['vehicles_planned']} "
                  f"vehicles, with {summary['empty_miles']} estimated empty miles including the trip home. "
                  'The AI explanation was unavailable; the verified calculation is shown. Human review is required.')
        narration_error = 'AI explanation unavailable; solver result retained.'
    return dict(type='plan', message=answer, plan=result, narration_error=narration_error,
                ai=dict(provider='Parasail', model=client.model, usage=client.usage()),
                applied_constraints=dict(result['options'], source=result['source']))
