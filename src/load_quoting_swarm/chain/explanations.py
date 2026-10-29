"""Strict Parasail explanations; the model has no authority over the policy plan."""
import json
import math
from urllib.request import Request, urlopen

from ..inference import ParasailInference, InferenceError

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"summary": {"type": "string"},
                   "risk_flags": {"type": "array", "items": {"type": "string"}},
                   "confidence": {"type": "number"}},
    "required": ["summary", "risk_flags", "confidence"],
}


def validate_explanation(value):
    if not isinstance(value, dict) or not isinstance(value.get("summary"), str) or not value["summary"].strip():
        raise InferenceError("Parasail returned an empty explanation")
    if not isinstance(value.get("risk_flags"), list) or not all(isinstance(f, str) for f in value["risk_flags"]):
        raise InferenceError("Parasail returned invalid risk flags")
    confidence = value.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise InferenceError("Parasail returned invalid confidence")
    return value


class ChainExplanations(ParasailInference):
    def _complete(self, system, payload):
        body = {
            "model": self.model, "temperature": 0, "store": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(payload)}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "chain_explanation", "strict": True, "schema": SCHEMA}},
        }
        request = Request(self.base_url.rstrip("/") + "/chat/completions",
                          data=json.dumps(body).encode(), method="POST",
                          headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=90) as response:
                result = json.load(response)
            usage = result.get("usage", {})
            with self._usage_lock:
                self._usage["requests"] += 1
                self._usage["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
                self._usage["completion_tokens"] += int(usage.get("completion_tokens", 0))
            return validate_explanation(json.loads(result["choices"][0]["message"]["content"]))
        except InferenceError:
            raise
        except Exception as exc:
            raise InferenceError("Parasail chain explanation failed: " + type(exc).__name__) from exc
