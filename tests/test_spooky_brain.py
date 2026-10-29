import copy
import json
from pathlib import Path

import pytest

from load_quoting_swarm.spooky_brain import plan_loops, request_options, stamp
from load_quoting_swarm.web import LoadboardState

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    return (json.loads((ROOT/'src/load_quoting_swarm/web_assets/loop-demo.json').read_text()),
            json.loads((ROOT/'config/fleet.demo.json').read_text()))


def test_matches_return_loads_and_closes_every_vehicle_loop(inputs):
    result = plan_loops(*inputs, {})
    ids = []
    assert result['summary']['matched_loads'] == 6
    assert result['summary']['vehicles_planned'] == 3
    for route in result['routes']:
        assert route['legs'][0]['origin'] == route['base']
        assert route['legs'][-1]['destination'] == route['base']
        assert stamp(route['return_at']) <= stamp('2026-10-30T20:00')
        assert route['status'] == 'REVIEW'
        ids.extend(leg['load_id'] for leg in route['legs'])
    assert len(ids) == len(set(ids))


def test_no_load_is_assigned_twice_across_vehicles(inputs):
    loads, fleet = inputs
    duplicate_vehicle = copy.deepcopy(fleet['vehicles'][0])
    duplicate_vehicle['vehicle_id'] = 'OTHER-LUTON'
    fleet['vehicles'].append(duplicate_vehicle)
    result = plan_loops(loads, fleet, {})
    ids = [leg['load_id'] for route in result['routes'] for leg in route['legs']]
    assert len(ids) == len(set(ids))


def test_return_deadline_changes_the_plan_and_keeps_empty_home_visible(inputs):
    result = plan_loops(*inputs, {'return_by': '14:00'})
    routes = [route for route in result['routes'] if route['legs']]
    assert routes
    assert all(stamp(route['return_at']) <= stamp('2026-10-30T14:00') for route in routes)
    assert any(route['home_empty_miles'] > 0 for route in routes)
    assert all(route['empty_miles'] >= route['home_empty_miles'] for route in routes)


def test_impossible_day_keeps_vehicles_at_base(inputs):
    result = plan_loops(*inputs, {'date': '2026-11-02'})
    assert result['summary']['matched_loads'] == 0
    assert all(route['status'] == 'AT_BASE' and route['empty_miles'] == 0 for route in result['routes'])


def test_rejects_overweight_and_incompatible_loads(inputs):
    loads, fleet = inputs
    loads = [loads[0]]
    loads[0]['weight_kg'] = 90000
    assert plan_loops(loads, fleet, {})['summary']['matched_loads'] == 0
    loads[0]['weight_kg'] = 100
    loads[0]['vehicle_requested'] = 'Refrigerated 18t'
    assert plan_loops(loads, fleet, {})['summary']['matched_loads'] == 0


def test_tight_pickup_window_and_breaks_cannot_be_skipped(inputs):
    loads, fleet = inputs
    loads = loads[:2]
    loads[0]['journey_minutes_est'] = 290
    loads[1]['pickup'] = {'type': 'exact', 'time': '2026-10-30T14:30'}
    result = plan_loops(loads, fleet, {})
    assert result['summary']['matched_loads'] < 2
    for route in result['routes']:
        if route['legs']:
            assert route['driving_minutes'] <= 540
            assert route['break_minutes'] >= 45


def test_ledger_decisions_are_excluded(inputs):
    loads, fleet = inputs
    ledger = {f"Q-{l['load_id']}": {'status':'BOOKED'} for l in loads}
    assert plan_loops(loads, fleet, {}, ledger)['summary']['matched_loads'] == 0


def test_before_pickups_do_not_become_available_on_an_earlier_day(inputs):
    loads, fleet = inputs
    loads = [loads[0]]
    loads[0]['pickup'] = {'type':'before', 'time':'2026-10-31T18:00'}
    assert plan_loops(loads, fleet, {})['summary']['matched_loads'] == 0


def test_delivery_deadline_is_respected(inputs):
    loads, fleet = inputs
    loads = [loads[0]]
    loads[0]['deliver'] = {'type':'by','time':'2026-10-30T09:01'}
    assert plan_loops(loads, fleet, {})['summary']['matched_loads'] == 0


def test_chat_extracts_supported_constraints():
    assert request_options({'prompt':'Plan from Bristol on 2026-10-30, home by 6pm, reduce empty miles'}) == {
        'date':'2026-10-30','base':'BRISTOL','return_by':'18:00','objective':'empty'}


@pytest.mark.parametrize('body', [
    {'prompt':'Book and email everyone'}, {'prompt':'Plan from Atlantis'},
    {'return_by':'03:00'}, {'date':'broken'}, {'base':'UNKNOWN'},
    {'prompt':'Home by 29:00'}, {'objective':'anything'},
])
def test_invalid_or_unsupported_requests_are_recoverable(inputs, body):
    with pytest.raises(ValueError):
        plan_loops(*inputs, body)


def test_plan_endpoint_is_read_only_and_uses_configured_fleet(tmp_path):
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from load_quoting_swarm.web import make_handler

    ledger = tmp_path/'ledger.jsonl'
    state = LoadboardState(ROOT/'data/loads_v2.json', ledger, ROOT/'config/fleet.demo.json')
    server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(state))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}/api/plan'
        with urlopen(Request(url, data=b'{}', headers={'Content-Type':'application/json'})) as response:
            payload = json.load(response)
            assert payload['source'] == 'demo' and payload['summary']['matched_loads'] == 6
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url, data=b'{"return_by":"bad"}'))
        assert error.value.code == 400
        assert not ledger.exists()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
