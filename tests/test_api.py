"""server.api over a real HTTP server on an ephemeral port, with a synthetic package root and a fake detector."""
import json
import threading
import urllib.error
import urllib.request

import pandas as pd
import pytest

from server import api as server_api
from tests.contract_fixture import fingerprint, span, write_detect_dir

NOTE = 'Seen by Anna Virtanen today'
KEY = 'test-only-api-key'


def labels():
    rows = [('people', 'id', 'record_key', 'PATIENT_ID', '.95', 'False'),
            ('people', 'score', 'non_sensitive', 'MEASUREMENT', '.40', 'True'),
            ('people', 'note', 'free_text', 'FREE_TEXT', '.95', 'False'),
            ('visits', 'vid', 'record_key', 'RECORD_ID', '.95', 'False'),
            ('visits', 'pid', 'technical_identifier', 'PATIENT_ID', '.95', 'False')]
    return pd.DataFrame([{'dataset': 'demo', 'table': t, 'column': c, 'privacy_role': r, 'subtype': s,
                          'confidence': conf, 'needs_review': rev, 'reason': f'example value {NOTE}'}
                         for t, c, r, s, conf, rev in rows])


def fake_detect(model, data, out):
    write_detect_dir(out, data, labels(), [span(fingerprint(data)[1], 'people', 'note', 0, 8, 21)])


@pytest.fixture
def root(tmp_path):
    data = tmp_path / 'data' / 'demo'
    data.mkdir(parents=True)
    pd.DataFrame({'id': ['p1', 'p2', 'p3'], 'score': ['12', '14', '12'], 'note': [NOTE, '', 'ok']}) \
        .to_csv(data / 'people.csv', index=False)
    pd.DataFrame({'vid': ['v1', 'v2', 'v3', 'v4'], 'pid': ['p1', 'p1', 'p2', 'p3']}).to_csv(data / 'visits.csv',
                                                                                          index=False)
    (tmp_path / 'metadata').mkdir()
    (tmp_path / 'metadata' / 'scenarios.json').write_text(json.dumps([
        {'id': 'DEMO-S1', 'dataset': 'demo', 'title': 'Demo', 'trust_level': 'internal',
         'utility_requirements': [], 'suggested_privacy_targets': 'k>=1'}]))
    (tmp_path / 'metadata' / 'field_catalog.csv').write_text('dataset,table,column\n')
    (tmp_path / 'truth').mkdir()
    (tmp_path / 'truth' / 'demo__people.csv').write_text('record_id,person_id\n')
    return tmp_path


@pytest.fixture
def server(root):
    httpd = server_api.serve(server_api.Api(root, root / 'model', root / 'runs', detect=fake_detect), 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{httpd.server_port}'
    httpd.shutdown()


def call(base, path, body=None, method=None, headers=None):
    req = urllib.request.Request(base + path, method=method or ('POST' if body is not None else 'GET'),
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return r.status, json.loads(text) if text else None, text, dict(r.headers)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        return e.code, json.loads(text), text, dict(e.headers)


def confirm_all(base, run_id, state):
    items = [{k: x[k] for k in ('table', 'column', 'privacy_role', 'subtype')} for x in state['detect_review']]
    return call(base, f'/api/runs/{run_id}/confirm', {'confirmations': items, 'allow_downgrade': False})


def test_full_workflow_statuses_and_no_raw_values(server, root, monkeypatch):
    refused = server_api.guard(root)  # catalog / truth must never be opened while serving the workflow
    assert call(server, '/api/datasets')[1] == {'datasets': ['demo']}
    assert [s['id'] for s in call(server, '/api/scenarios')[1]['scenarios']] == ['DEMO-S1']
    status, run, *_ = call(server, '/api/runs', {'dataset': 'demo'})
    assert status == 200 and run['steps']['detect'] and run['manifest']['tables']['people'] == {'rows': 3,
                                                                                                'columns': 3}
    assert [x['column'] for x in run['detect_review']] == ['score'] and 'reason' not in run['labels'][0]
    rid = run['id']
    assert call(server, f'/api/runs/{rid}/search', {'budget': 5})[1]['error']['code'] == 'hmac_key_missing'
    status, state, *_ = confirm_all(server, rid, run)
    assert status == 200 and state['confirmation']['reviewer_confirmed'] and state['confirmations'][0]['column'] == 'score'
    assert confirm_all(server, rid, run)[1]['error']['code'] == 'step_done'
    status, state, *_ = call(server, f'/api/runs/{rid}/select', {'scenario': 'DEMO-S1'})
    sel = state['select']
    assert status == 200 and sel['status'] == 'policy_valid' and sel['outcome']['approved'] is False
    assert sel['reviews'][0]['confirmed'] == {'role': 'non_sensitive', 'subtype': 'MEASUREMENT'}
    assert sel['provenance']['confirm_sha256']
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', KEY)
    status, state, *_ = call(server, f'/api/runs/{rid}/search', {'budget': 5})
    res = state['search']
    assert status == 200 and res['status'] in ('measured_ok', 'target_unmet', 'budget_exhausted')
    assert res['outcome']['approved'] is (res['status'] == 'measured_ok') and res['trace']
    assert call(server, f'/api/runs/{rid}/select', {'scenario': 'DEMO-S1'})[1]['error']['code'] == 'step_done'
    text = call(server, f'/api/runs/{rid}')[2]
    assert 'Anna' not in text and 'Virtanen' not in text and KEY not in text and 'p1' not in text
    assert refused == []
    with pytest.raises(PermissionError):
        open(root / 'metadata' / 'field_catalog.csv')
    assert refused == [str(root / 'metadata' / 'field_catalog.csv')]


@pytest.mark.parametrize('path', ['/api/runs/..', '/api/runs/%2e%2e%2fdata', '/api/runs/x/../../data/confirm'])
def test_run_ids_cannot_traverse(server, path):
    status, body, *_ = call(server, path)
    assert status in (400, 404) and body['error']['code'] in ('bad_run_id', 'not_found')


def test_bad_dataset_scenario_and_confirmation_rejected(server):
    assert call(server, '/api/runs', {'dataset': '../metadata'})[1]['error']['code'] == 'unknown_dataset'
    rid = call(server, '/api/runs', {'dataset': 'demo'})[1]['id']
    assert call(server, f'/api/runs/{rid}/select', {'scenario': 'H-S1'})[1]['error']['code'] == 'unknown_scenario'
    down = {'confirmations': [{'table': 'people', 'column': 'id', 'privacy_role': 'non_sensitive',
                               'subtype': 'MEASUREMENT'}], 'allow_downgrade': False}
    status, body, *_ = call(server, f'/api/runs/{rid}/confirm', down)
    assert status == 400 and body['error']['code'] == 'invalid_confirmation'


def test_changed_input_after_detect_is_named_409(server, root):
    rid = call(server, '/api/runs', {'dataset': 'demo'})[1]['id']
    (root / 'data' / 'demo' / 'visits.csv').write_text('vid,pid\nv1,p9\n')
    status, body, *_ = call(server, f'/api/runs/{rid}/select', {'scenario': 'DEMO-S1'})
    assert status == 409 and body['error']['code'] == 'input_mismatch'
    assert call(server, f'/api/runs/{rid}')[1]['errors'][0]['code'] == 'input_mismatch'


def test_cors_only_for_vite_dev_origin(server):
    allowed = call(server, '/api/datasets', headers={'Origin': 'http://localhost:5173'})[3]
    other = call(server, '/api/datasets', headers={'Origin': 'http://evil.example'})[3]
    assert allowed.get('Access-Control-Allow-Origin') == 'http://localhost:5173'
    assert 'Access-Control-Allow-Origin' not in other
