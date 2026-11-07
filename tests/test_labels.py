"""Detect artifact boundary and combined CLI; no training catalog or data exports."""
import json

import pandas as pd
import pytest

from server.select.labels import from_detection
from server.select.relations import discover
from server.select.select import confirm, select


def inputs():
    tables = {'people': pd.DataFrame({'id': ['p1', 'p2'], 'score': ['12', '14']})}
    labels = pd.DataFrame([
        {'dataset': 'demo', 'table': 'people', 'column': 'id', 'privacy_role': 'record_key',
         'subtype': 'PATIENT_ID', 'confidence': '.95', 'needs_review': 'False'},
        {'dataset': 'demo', 'table': 'people', 'column': 'score', 'privacy_role': 'non_sensitive',
         'subtype': 'MEASUREMENT', 'confidence': '.95', 'needs_review': 'False'}])
    return tables, labels


def test_v3_artifact_preserves_review_without_copying_raw_reasons():
    tables, labels = inputs()
    labels['reason'] = 'LLM saw secret@example.com in this column'
    labels.loc[labels.column.eq('score'), 'needs_review'] = 'True'
    out = from_detection(labels, tables, 'demo')
    req = {'source': 'spec', 'dataset': 'demo', 'trust_level': 'internal',
           'required': {'people.score': ['SCORE'], 'people.id': ['SUBJECT']}}
    plan = select(tables, out, discover(tables, out), req)
    assert plan['status'] == 'blocked'
    score = next(c for c in plan['columns'] if c['column'] == 'score')
    assert score['detector_confidence'] == .95 and score['detector_needs_review'] is True
    assert score['confidence'] < .6 and score['needs_review']
    assert 'secret@example.com' not in json.dumps(plan) + out.to_json()
    reviewed = confirm(out, pd.DataFrame([{'table': 'people', 'column': 'score',
                                         'privacy_role': 'non_sensitive', 'subtype': 'MEASUREMENT'}]))
    assert select(tables, reviewed, discover(tables, reviewed), req)['status'] == 'ready_for_transform'


@pytest.mark.parametrize('value', ['nan', 'inf', '-.1', '1.1', 'unknown'])
def test_bad_confidence_rejected(value):
    tables, labels = inputs()
    labels.loc[0, 'confidence'] = value
    with pytest.raises(ValueError, match='confidence'):
        from_detection(labels, tables, 'demo')


def test_nullable_confidence_is_rejected():
    tables, labels = inputs()
    labels['confidence'] = labels['confidence'].astype('string')
    labels.loc[0, 'confidence'] = pd.NA
    with pytest.raises(ValueError, match='confidence'):
        from_detection(labels, tables, 'demo')


def test_dataset_filter_and_complete_schema_required():
    tables, labels = inputs()
    other = labels.assign(dataset='another')
    assert len(from_detection(pd.concat([labels, other]), tables, 'demo')) == 2
    for invalid in (labels.iloc[:1], pd.concat([labels, labels.iloc[:1]]),
                    labels.assign(column=['id', 'unknown']), labels.assign(dataset='another')):
        with pytest.raises(ValueError):
            from_detection(invalid, tables, 'demo')
    with pytest.raises(ValueError, match='explained labels'):
        from_detection(labels.drop(columns='confidence'), tables, 'demo')


@pytest.mark.parametrize('field,value', [('privacy_role', 'unknown'), ('subtype', 'raw text'),
                                        ('needs_review', 'perhaps'), ('art9', 'True')])
def test_inconsistent_labels_rejected(field, value):
    tables, labels = inputs()
    if field not in labels:
        labels[field] = 'False'
    labels.loc[0, field] = value
    with pytest.raises(ValueError):
        from_detection(labels, tables, 'demo')


def test_detect_to_select_to_search_cli(tmp_path, monkeypatch):
    from server.select.__main__ import main
    import server.select.__main__ as cli
    from server.select import transform
    tables, labels = inputs()
    data = tmp_path / 'demo'
    data.mkdir()
    tables['people'].to_csv(data / 'people.csv', index=False)
    label_path = tmp_path / 'detect.csv'
    labels.to_csv(label_path, index=False)
    spec = tmp_path / 'spec.json'
    spec.write_text(json.dumps({'dataset': 'demo', 'trust_level': 'internal', 'targets': {'k': 1},
                                'required': [{'column': 'people.score', 'task': 'SCORE'}]}))
    def forbidden(*args, **kwargs):
        pytest.fail('external labels must bypass built-in detection and exports')
    monkeypatch.setattr(cli, 'detect_table', forbidden)
    monkeypatch.setattr(transform, 'apply', forbidden)
    planned, measured = tmp_path / 'select', tmp_path / 'search'
    assert main(['select', '--data', str(data), '--spec', str(spec), '--labels', str(label_path),
                 '--out', str(planned)]) == 0
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', 'test-only-key')
    assert main(['search', '--data', str(data), '--plan', str(planned / 'decisions.json'),
                 '--out', str(measured)]) == 0
    assert json.loads((measured / 'decisions.json').read_text())['status'] == 'measured_ok'
    assert {p.name for p in measured.iterdir()} == {'decisions.json', 'decisions.md'}
    with pytest.raises(SystemExit, match='existing'):
        main(['select', '--data', str(data), '--spec', str(spec), '--labels', str(label_path),
              '--out', str(planned)])
