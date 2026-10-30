"""HTTP security, bounded queries and process-independent experiment ownership."""
from contextlib import contextmanager
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread

import pytest

from astromembench.webui.server import Application, LocalServer

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server_at(root):
    app = Application(ROOT / 'data/benchmark', root)
    with LocalServer(('127.0.0.1', 0), app) as server:
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        try:
            yield app, server
        finally:
            server.shutdown()
            thread.join(timeout=3)


def request(server, path, body=None, headers=None):
    connection = HTTPConnection('127.0.0.1', server.server_address[1], timeout=10)
    values = {'Origin': f'http://127.0.0.1:{server.server_address[1]}',
              'Content-Type': 'application/json', 'X-CSRF-Token': server.application.token}
    values.update(headers or {})
    try:
        connection.request('GET' if body is None else 'POST', path,
                           body=None if body is None else json.dumps(body), headers=values)
        response = connection.getresponse()
        content = response.read()
        parsed = json.loads(content) if response.getheader('Content-Type', '').startswith('application/json') else content
        return response.status, parsed, dict(response.getheaders())
    finally:
        connection.close()


def test_bootstrap_static_allowlist_and_no_bulk_case_payload(tmp_path):
    with server_at(tmp_path) as (app, server):
        status, value, headers = request(server, '/api/bootstrap')
        assert status == 200 and value['bank']['task_count'] == 2240
        assert value['csrf'] == app.token and value['author'] == 'you wu'
        assert value['version'] == '1.0.0' and value['team'].endswith('Zhejiang University')
        assert 'cases' not in value['bank']
        assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
        for path in ('/../../pyproject.toml', '/%2e%2e/secret', '/index.json', '/assets/../secret'):
            assert request(server, path)[0] == 404
        assert request(server, '/')[0] == 200


def test_cross_origin_csrf_and_dns_rebinding_rejected(tmp_path):
    with server_at(tmp_path) as (_, server):
        for headers in ({'Origin': 'https://example.org'}, {'X-CSRF-Token': 'wrong'},
                        {'Host': 'attacker.example', 'Origin': 'http://attacker.example'},
                        {'Sec-Fetch-Site': 'cross-site'}, {'Origin': 'null'}):
            assert request(server, '/api/experiments', {}, headers)[0] == 403
        assert request(server, '/api/bootstrap', headers={'Host': 'attacker.example'})[0] == 403
        assert request(server, '/api/experiments', [], {})[0] == 400


def test_non_loopback_binding_refused(tmp_path):
    with pytest.raises(ValueError, match='127.0.0.1'):
        LocalServer(('0.0.0.0', 0), Application(ROOT / 'data/benchmark', tmp_path))


@pytest.mark.skipif(not (ROOT / 'data/benchmark/tasks.jsonl').is_file(), reason='Install the complete release dataset for lazy preview integration tests')
def test_case_preview_is_lazy_and_does_not_expose_evaluator_answers(tmp_path):
    with server_at(tmp_path) as (_, server):
        value = request(server, '/api/catalog?limit=2&offset=2')[1]
        assert value['total'] == 2240 and len(value['items']) == 2
        assert request(server, '/api/catalog?limit=100000')[0] == 400
        assert request(server, '/api/catalog?offset=-1')[0] == 400
        preview = request(server, '/api/task?case_id=FM-C1-P1-001')[1]
        assert 'public' in preview and 'history' not in preview
        assert not {'initial', 'world', 'rubric', 'design'} & set(preview)
        history = request(server, '/api/task?case_id=FM-C1-P1-001&round=1')[1]
        assert history['round'] == 1 and 'input' in history
        assert request(server, '/api/task?case_id=FM-C1-P1-001&round=0')[0] == 400
        assert request(server, '/api/asset?path=../../pyproject.toml')[0] == 400
        assert request(server, '/api/asset?path=landmarks/a01.jpg')[0] == 200


def test_draft_survives_http_restart_and_poll_revision_changes(tmp_path):
    with server_at(tmp_path) as (_, server):
        imported = request(server, '/api/adapters/import', {'path': str(ROOT / 'examples/random-adapter.json')})[1]
        saved = request(server, '/api/experiments', {'name': 'Saved draft', 'groups': [
            {'name': 'Baseline', 'adapter_id': imported['id'], 'selection': {'limit': 1}}]})[1]
        identifier = saved['id']
        path = f'/api/experiments/{identifier}/state'
        state = request(server, path)[1]
        assert request(server, path + '?since=' + state['revision'])[1]['unchanged']
    with server_at(tmp_path) as (_, server):
        assert request(server, '/api/experiments')[1]['items'][0]['name'] == 'Saved draft'
        assert not request(server, path + '?since=' + state['revision'])[1].get('unchanged')
        check = request(server, '/api/adapters/check', {'id': imported['id']})[1]
        assert check['valid'] and check['model_calls'] == 0
