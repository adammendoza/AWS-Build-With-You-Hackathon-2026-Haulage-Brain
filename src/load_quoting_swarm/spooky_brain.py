"""Auditable closed-loop dispatch suggestions. No booking or provider side effects."""
from __future__ import annotations

from datetime import datetime, time, timedelta
import math
import re
from typing import Any
from zoneinfo import ZoneInfo

# Approximate town centres, not road-routing or postcode geocoding.
TOWNS = {
    'LONDON': (51.507, -.128), 'BIRMINGHAM': (52.486, -1.890),
    'MANCHESTER': (53.481, -2.243), 'BRISTOL': (51.455, -2.588),
    'SOUTHAMPTON': (50.910, -1.404), 'LUTON': (51.879, -.418),
    'WITHAM': (51.800, .640), 'BASILDON': (51.576, .489),
    'BRIGHTON': (50.823, -.137), 'CAMBRIDGE': (52.205, .122),
    'CARDIFF': (51.481, -3.179), 'CARLISLE': (54.893, -2.933),
    'CHELMSFORD': (51.736, .469), 'CORBY': (52.488, -.690),
    'COVENTRY': (52.406, -1.512), 'CROYDON': (51.372, -.100),
    'DARTFORD': (51.446, .219), 'DAVENTRY': (52.257, -1.161),
    'DONCASTER': (53.522, -1.128), 'DOVER': (51.128, 1.313),
    'EDINBURGH': (55.953, -3.189), 'EXETER': (50.719, -3.534),
    'FELIXSTOWE': (51.961, 1.351), 'GLASGOW': (55.864, -4.252),
    'HULL': (53.768, -.328), 'IPSWICH': (52.057, 1.148),
    'LEEDS': (53.801, -1.549), 'LEICESTER': (52.636, -1.139),
    'LIVERPOOL': (53.408, -2.992), 'MILTON KEYNES': (52.040, -.759),
    'NEWCASTLE': (54.978, -1.617), 'NORTHAMPTON': (52.240, -.903),
    'NORWICH': (52.630, 1.297), 'NOTTINGHAM': (52.954, -1.158),
    'OXFORD': (51.752, -1.258), 'PETERBOROUGH': (52.570, -.240),
    'PLYMOUTH': (50.375, -4.142), 'PORTSMOUTH': (50.819, -1.089),
    'PRESTON': (53.763, -2.704), 'READING': (51.454, -.978),
    'SHEFFIELD': (53.381, -1.470), 'SLOUGH': (51.510, -.595),
    'STOKE-ON-TRENT': (53.003, -2.179), 'SWINDON': (51.556, -1.782),
    'TILBURY': (51.462, .358), 'WARRINGTON': (53.390, -2.597),
    'WATFORD': (51.656, -.390), 'WOLVERHAMPTON': (52.587, -2.129),
    'YORK': (53.960, -1.087),
}
UK = ZoneInfo('Europe/London')


def stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed.replace(tzinfo=UK) if parsed.tzinfo is None else parsed.astimezone(UK)


def road_miles(a: str, b: str) -> float:
    if a == b:
        return 0.0
    lat1, lon1 = map(math.radians, TOWNS[a])
    lat2, lon2 = map(math.radians, TOWNS[b])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return round(3958.8 * 2 * math.asin(min(1, math.sqrt(h))) * 1.2, 1)


def request_options(body: dict[str, Any]) -> dict[str, Any]:
    options = {k: str(body.get(k) or default) for k, default in (
        ('date', '2026-10-30'), ('base', 'fleet'), ('objective', 'balanced'), ('return_by', '20:00'))}
    prompt = str(body.get('prompt') or '').strip()
    if len(prompt) > 2000:
        raise ValueError('Keep the dispatch request under 2,000 characters.')
    if prompt:
        understood = False
        date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', prompt)
        if date_match:
            options['date'] = date_match[1]
            understood = True
        base_match = re.search(r'\b(?:from|base(?:\s+in)?|based\s+in)\s+([a-z -]+)', prompt, re.I)
        if base_match:
            place = base_match[1].upper().strip()
            city = next((city for city in sorted(TOWNS, key=len, reverse=True)
                         if place == city or place.startswith(city + ' ')), None)
            if city is None:
                raise ValueError('Unknown base. Use a supported UK town, for example London, Manchester or Bristol.')
            options['base'] = city
            understood = True
        return_match = re.search(r'\b(?:by|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', prompt, re.I)
        if return_match:
            hour = int(return_match[1])
            suffix = (return_match[3] or '').lower()
            if suffix and not 1 <= hour <= 12:
                raise ValueError('Use a valid return time, for example 18:00 or 6pm.')
            if suffix:
                hour = hour % 12 + (12 if suffix == 'pm' else 0)
            options['return_by'] = f'{hour:02d}:{return_match[2] or "00"}'
            understood = True
        if re.search(r'empty|unloaded|deadhead|backhaul', prompt, re.I):
            options['objective'] = 'empty'
            understood = True
        elif re.search(r'profit|margin|revenue', prompt, re.I):
            options['objective'] = 'profit'
            understood = True
        elif re.search(r'plan|loop|home|match|calculate|connect|trucks|vehicles', prompt, re.I):
            understood = True
        if not understood:
            raise ValueError('I can calculate loops using a base, date, return time and objective. Try “Plan from London on 2026-10-29, home by 18:00, reduce empty miles.”')
    datetime.strptime(options['date'], '%Y-%m-%d')
    if not re.fullmatch(r'\d{2}:\d{2}', options['return_by']):
        raise ValueError('Return time must use HH:MM in UK time.')
    time.fromisoformat(options['return_by'])
    if options['base'] != 'fleet' and options['base'].upper() not in TOWNS:
        raise ValueError('Base is not in the supported town-centre dataset.')
    if options['objective'] not in {'balanced', 'empty', 'profit'}:
        raise ValueError('Choose balanced, empty or profit as the objective.')
    options['base'] = options['base'] if options['base'] == 'fleet' else options['base'].upper()
    for key in ('vehicle_ids', 'exclude_towns'):
        if key in body:
            values = body[key]
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values) or len(values) > 100:
                raise ValueError(f'{key} must be an array of names.')
            if key == 'exclude_towns':
                values = [v.upper() for v in values]
                if set(values) - TOWNS.keys():
                    raise ValueError('An excluded town is not supported.')
            options[key] = values
    if 'start_time' in body:
        value = body['start_time']
        if not isinstance(value, str) or not re.fullmatch(r'\d{2}:\d{2}', value):
            raise ValueError('Start time must use HH:MM in UK time.')
        time.fromisoformat(value)
        options['start_time'] = value
    for key, maximum in (('max_empty_miles', 2000), ('max_driving_hours', 9)):
        if key not in body:
            continue
        value = body[key]
        if key == 'max_empty_miles' and value is None:
            options[key] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0 or value > maximum or (key == 'max_driving_hours' and value == 0):
            raise ValueError(f'{key} must be a number within the supported limits (maximum {maximum}).')
        options[key] = value
    return options


def compatible(load: dict, vehicle: dict, profile: dict) -> bool:
    requested = str(load.get('vehicle_requested', '')).lower()
    kind = vehicle['vehicle_type'].lower()
    matches = ('luton' in kind and 'luton' in requested or
               '7.5' in kind and '7.5' in requested or
               'artic' in kind and 'artic' in requested)
    weight = load.get('weight_kg')
    return bool(matches and (weight is None or float(weight) <= profile['max_payload_kg']))


def plan_loops(loads: list[dict], fleet: dict, body: dict, ledger: dict | None = None) -> dict:
    options = request_options(body)
    start = stamp(options['date'] + 'T' + options.get('start_time', '06:00'))
    deadline = stamp(options['date'] + 'T' + options['return_by'])
    if deadline <= start:
        raise ValueError('Return time must be after the dispatch start.')
    profiles = {p['vehicle_type']: p for p in fleet['vehicle_profiles']}
    ledger = ledger or {}
    candidates = [load for load in loads if load.get('status') == 'Available'
                  and ledger.get(f"Q-{load['load_id']}", {}).get('status') not in {'BOOKED', 'PASSED'}
                  and all(load.get(k, {}).get('town', '').upper() in TOWNS
                          and load.get(k, {}).get('town', '').upper() not in options.get('exclude_towns', []) for k in ('from_', 'to'))]
    used: set[str] = set()
    plans = []
    penalty = {'balanced': .7, 'empty': 2.5, 'profit': 0}[options['objective']]
    for vehicle in fleet['vehicles']:
        if options.get('vehicle_ids') and vehicle['vehicle_id'] not in options['vehicle_ids']:
            continue
        profile = profiles[vehicle['vehicle_type']]
        base = (vehicle.get('base') or vehicle['location']).split(',')[0].upper() if options['base'] == 'fleet' else options['base'].upper()
        if base not in TOWNS:
            raise ValueError(f'Unsupported fleet base: {base}')
        available = max(start, stamp(vehicle['available_from']))
        until = min(deadline, stamp(vehicle['available_until']), available + timedelta(hours=13))
        speed = float(profile['typical_speed_mph'])
        # Diesel £1.50/litre is an explicit scenario assumption, not live research.
        mile_cost = float(profile['fixed_cost_per_mile_gbp']) + 4.54609 / float(profile['mpg']) * 1.50
        driver_cost = float(fleet['driver_cost_per_hour_gbp'])

        def close(path):
            home_miles = road_miles(path['town'], base)
            drive = path['drive'] + home_miles / speed * 60
            # Conservative allowance: 45 minutes after each 4.5h block of driving.
            breaks = 45 * int(max(0, drive - .001) // 270)
            home_at = path['at'] + timedelta(minutes=home_miles / speed * 60 + breaks - path['breaks'])
            if home_at > until or drive > options.get('max_driving_hours', 9)*60:
                return None
            empty = path['empty'] + home_miles
            if options.get('max_empty_miles') is not None and empty > options['max_empty_miles']:
                return None
            cost = (empty + path['loaded']) * mile_cost + (home_at-available).total_seconds()/3600 * driver_cost
            return dict(path, home_miles=home_miles, home_at=home_at, empty=empty,
                        drive=drive, cost=cost, score=path['revenue']-cost-penalty*empty,
                        breaks=breaks)

        seed = dict(town=base, at=available, jobs=[], legs=[], empty=0., loaded=0., revenue=0., drive=0., breaks=0)
        best = None
        beam = [seed]
        if available < until:
            for _ in range(4):
                expanded = []
                for path in beam:
                    for load in candidates:
                        load_id = str(load['load_id'])
                        if load_id in used or load_id in path['jobs'] or not compatible(load, vehicle, profile):
                            continue
                        origin, destination = (load[k]['town'].upper() for k in ('from_', 'to'))
                        deadhead = road_miles(path['town'], origin)
                        arrival_drive = path['drive'] + deadhead/speed*60
                        arrival_breaks = 45 * int(max(0, arrival_drive-.001)//270)
                        arrival = path['at'] + timedelta(minutes=deadhead/speed*60+arrival_breaks-path['breaks'])
                        pickup = load.get('pickup') or {}
                        try:
                            latest = stamp(pickup.get('end') or pickup.get('time') or pickup['start'])
                            earliest = start if pickup.get('type') == 'before' else stamp(pickup.get('start') or pickup['time'])
                        except (ValueError, KeyError, TypeError):
                            continue
                        if latest.date() != start.date():
                            continue
                        pickup_at = max(arrival, earliest)
                        if pickup_at > latest or pickup_at.date() != start.date():
                            continue
                        # 30 minutes each for loading and unloading; unknown handling remains a review flag.
                        journey = float(load['journey_minutes_est'])
                        next_drive = arrival_drive + journey
                        next_breaks = 45 * int(max(0, next_drive-.001)//270)
                        delivered = pickup_at + timedelta(minutes=journey+60+next_breaks-arrival_breaks)
                        delivery = load.get('deliver') or 'ASAP'
                        if isinstance(delivery, dict):
                            try:
                                if delivered > stamp(delivery.get('time') or delivery['end']):
                                    continue
                            except (ValueError, KeyError):
                                continue
                        elif str(delivery).upper() == 'SAME DAY':
                            if delivered.date() != pickup_at.date():
                                continue
                        elif str(delivery).upper() == 'NEXT DAY AM':
                            if delivered > datetime.combine(pickup_at.date()+timedelta(days=1), time(12), tzinfo=UK):
                                continue
                        elif str(delivery).upper() != 'ASAP':
                            continue
                        nxt = dict(town=destination, at=delivered, jobs=path['jobs']+[load_id],
                                   legs=path['legs']+[dict(load_id=load_id, origin=origin, destination=destination,
                                       pickup_at=pickup_at.isoformat(), delivered_at=delivered.isoformat(),
                                       empty_before_miles=round(deadhead, 1), loaded_miles=float(load['distance_miles']),
                                       revenue_gbp=float(load.get('agreed_rate_gbp') or 0))],
                                   empty=path['empty']+deadhead, loaded=path['loaded']+float(load['distance_miles']),
                                   revenue=path['revenue']+float(load.get('agreed_rate_gbp') or 0),
                                   drive=next_drive, breaks=next_breaks)
                        # Retain intermediate paths even if returning now is infeasible:
                        # another load can move the truck closer to home.
                        if delivered <= until and nxt['drive'] <= options.get('max_driving_hours', 9)*60:
                            expanded.append(nxt)
                            closed = close(nxt)
                            if closed and closed['score'] > 0 and (best is None or closed['score'] > best['score']):
                                best = closed
                beam = sorted(expanded, key=lambda p: p['revenue']-(p['empty']+p['loaded'])*mile_cost-penalty*p['empty'], reverse=True)[:32]
                if not beam:
                    break
        if best:
            used.update(best['jobs'])
            total = best['loaded'] + best['empty']
            plans.append(dict(vehicle_id=vehicle['vehicle_id'], vehicle_type=vehicle['vehicle_type'], base=base,
                status='REVIEW', legs=best['legs'], return_at=best['home_at'].isoformat(),
                loaded_miles=round(best['loaded'], 1), empty_miles=round(best['empty'], 1),
                home_empty_miles=round(best['home_miles'], 1), revenue_gbp=round(best['revenue'], 2),
                estimated_cost_gbp=round(best['cost'], 2), estimated_surplus_gbp=round(best['revenue']-best['cost'], 2),
                loaded_pct=round(best['loaded']/total*100) if total else 0,
                driving_minutes=round(best['drive']), break_minutes=best['breaks'],
                review_flags=['Verify payload, dimensions, equipment and ULEZ compliance for every load.',
                              'Confirm handling times, delivery slots, road routing and driver duty compliance.']))
        else:
            plans.append(dict(vehicle_id=vehicle['vehicle_id'], vehicle_type=vehicle['vehicle_type'], base=base,
                status='AT_BASE', legs=[], loaded_miles=0, empty_miles=0, home_empty_miles=0,
                revenue_gbp=0, estimated_cost_gbp=0, estimated_surplus_gbp=0, loaded_pct=0,
                return_at=None, reason='Unavailable on this day.' if available >= until else 'No positive-scoring feasible loop. Vehicle stays at base.'))
    loaded = sum(p['loaded_miles'] for p in plans)
    empty = sum(p['empty_miles'] for p in plans)
    return dict(mode='local-calculation', options=options, routes=plans,
        summary=dict(matched_loads=len(used), vehicles_planned=sum(bool(p['legs']) for p in plans),
            loaded_miles=round(loaded, 1), empty_miles=round(empty, 1),
            loaded_pct=round(loaded/(loaded+empty)*100) if loaded+empty else 0,
            revenue_gbp=round(sum(p['revenue_gbp'] for p in plans), 2),
            estimated_surplus_gbp=round(sum(p['estimated_surplus_gbp'] for p in plans), 2)),
        explanation='Each suggestion starts and ends at its base. Loads are assigned once, in pickup order, with time for repositioning, handling, breaks and the return. Empty legs remain visible when no feasible paying load closes the gap.',
        assumptions=['Synthetic fleet and loadboard; suggestions require manager review.',
            'Bounded beam search (32 candidates, 4 loads per vehicle), greedy fleet allocation; not a global optimum.',
            'Connecting and home legs use town-centre straight-line miles × 1.2; loaded legs use fixture estimates.',
            'Scenario costs: diesel £1.50/litre, configured vehicle costs and driver wage; excludes tolls and overnight costs.',
            f"{options.get('start_time', '06:00')} UK start, at most 13 duty hours and {options.get('max_driving_hours', 9)} driving hours, 30 minutes each for loading/unloading; a 45-minute break per 4.5-hour driving block. This is not a driver-hours compliance check.",
            'Choosing a shared base assumes vehicles start there; relocation from configured fleet bases is not included.',
            'Route calculations use a deterministic solver. The server chat uses Parasail to interpret conversations and explain calculated routes.'])
