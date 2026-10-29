"""The opt-in fleet server must preserve the AI workspace and its separate ledgers."""
import json
import os
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from load_quoting_swarm.chain.economics import ROOT
from load_quoting_swarm.chain.service import ChainService
from load_quoting_swarm.chain.web import load_environment, make_handler
from load_quoting_swarm.web import LoadboardState


@pytest.fixture
def workspace(tmp_path):
    state = LoadboardState(ROOT / 'data/loads_v2.json', tmp_path / 'manual.jsonl')
    fleet = json.loads((ROOT / 'data/fleet/fleet_100_v1.json').read_text())
    fleet['trucks'] = fleet['trucks'][:3]
    fleet_path = tmp_path / 'fleet.json'
    fleet_path.write_text(json.dumps(fleet))
    service = ChainService(storage=tmp_path / 'policy', fleet_path=fleet_path)
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(state, service))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f'http://127.0.0.1:{server.server_port}', state, service
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


def test_combined_workspace_preserves_loop_calculation_and_assets(workspace, monkeypatch):
    url, state, service = workspace
    monkeypatch.setenv('HB_ENABLE_CHAIN', '1')
    with urlopen(url + '/') as response:
        page = response.read().decode()
        assert 'Fleet simulation' in page and 'href="/fleet.html"' in page
        assert 'brain-workspace' in page and 'brain-replies.js' in page
    for asset in ('brain-replies.css', 'creature-brain.webp', 'spooky-brain.js'):
        with urlopen(url + '/' + asset) as response:
            assert response.status == 200 and response.read()
    request = Request(url + '/api/plan', data=b'{"source":"demo","date":"2026-10-30"}',
                      headers={'Content-Type': 'application/json'})
    with urlopen(request) as response:
        plan = json.load(response)
    assert plan['summary']['matched_loads'] == 6
    assert plan['summary']['empty_miles'] == 0
    with urlopen(url + '/api/fleet') as response:
        assert len(json.load(response)['trucks']) == 3
    assert not state.ledger.events()
    assert not service.ledger.events()


def test_disabled_fleet_is_absent_while_brain_workspace_stays_available(workspace, monkeypatch):
    url, _, _ = workspace
    monkeypatch.delenv('HB_ENABLE_CHAIN', raising=False)
    with urlopen(url + '/') as response:
        page = response.read().decode()
        assert 'href="/fleet.html"' not in page
        assert 'brain-workspace' in page
    for path in ('/fleet.html', '/api/fleet', '/api/chain'):
        with pytest.raises(HTTPError) as error:
            urlopen(url + path)
        assert error.value.code == 404


def test_local_env_precedence_and_explicit_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('PARASAIL_MODEL', raising=False)
    monkeypatch.delenv('HB_WORKSPACE_ENV_TEST', raising=False)
    monkeypatch.setattr('load_quoting_swarm.chain.web._resolve_parameter', lambda _: None)
    (tmp_path / '.env').write_text('PARASAIL_MODEL=fallback\nHB_WORKSPACE_ENV_TEST=fallback\n')
    (tmp_path / '.env.local').write_text('PARASAIL_MODEL=local-test-model\n')
    load_environment()
    assert os.environ['PARASAIL_MODEL'] == 'local-test-model'
    assert os.environ['HB_WORKSPACE_ENV_TEST'] == 'fallback'
    explicit = tmp_path / 'explicit.env'
    explicit.write_text('PARASAIL_MODEL=explicit-test-model\n')
    monkeypatch.delenv('PARASAIL_MODEL')
    load_environment(explicit)
    assert os.environ['PARASAIL_MODEL'] == 'explicit-test-model'
    monkeypatch.setenv('PARASAIL_MODEL', 'process-wins')
    load_environment(explicit)
    assert os.environ['PARASAIL_MODEL'] == 'process-wins'
    with pytest.raises(SystemExit, match='does not exist'):
        load_environment(tmp_path / 'missing.env')


def test_environment_resolves_lambda_secrets_after_loading_file(tmp_path, monkeypatch):
    monkeypatch.delenv('DISCORD_WEBHOOK_URL_SSM_PARAMETER', raising=False)
    env_file = tmp_path / 'lambda.env'
    env_file.write_text('DISCORD_WEBHOOK_URL_SSM_PARAMETER=/haulage/discord-webhook\n')
    resolved = {}

    def resolve(name):
        resolved[name] = os.getenv(f'{name}_SSM_PARAMETER')

    monkeypatch.setattr('load_quoting_swarm.chain.web._resolve_parameter', resolve)
    load_environment(env_file)

    assert set(resolved) == {'YDC_API_KEY', 'PARASAIL_API_KEY', 'DEMO_PASSWORD', 'DISCORD_WEBHOOK_URL'}
    assert resolved['DISCORD_WEBHOOK_URL'] == '/haulage/discord-webhook'
