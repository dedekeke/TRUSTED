"""Detect -> Select handoff contract v1: provenance, coverage, reviews, spans/linkage, outcome statuses."""
import builtins
import hashlib
import io
import json

import pandas as pd
import pytest

from server.select import policy
from server.select.__main__ import main
from tests.contract_fixture import fingerprint, span, write_detect_dir

NOTE = 'Seen by Anna Virtanen today'


def label(table, column, role, subtype, conf='.95', review='False'):
    return {'dataset': 'demo', 'table': table, 'column': column, 'privacy_role': role, 'subtype': subtype,
            'confidence': conf, 'needs_review': review}


def labels():
    return pd.DataFrame([label('people', 'id', 'record_key', 'PATIENT_ID'),
                         label('people', 'score', 'non_sensitive', 'MEASUREMENT'),
                         label('people', 'note', 'free_text', 'FREE_TEXT'),
                         label('visits', 'vid', 'record_key', 'RECORD_ID'),
                         label('visits', 'pid', 'technical_identifier', 'PATIENT_ID')])


def write_data(root, name='demo'):
    data = root / name
    data.mkdir()
    pd.DataFrame({'id': ['p1', 'p2', 'p3'], 'score': ['12', '14', '12'], 'note': [NOTE, '', 'ok']}) \
        .to_csv(data / 'people.csv', index=False)
    pd.DataFrame({'vid': ['v1', 'v2', 'v3', 'v4'], 'pid': ['p1', 'p1', 'p2', 'p3']}) \
        .to_csv(data / 'visits.csv', index=False)
    return data


def spec(root, required=('people.score',), name='spec.json'):
    path = root / name
    path.write_text(json.dumps({'dataset': 'demo', 'trust_level': 'internal', 'targets': {'k': 1},
                                'required': [{'column': c, 'task': 'T-' + c.split('.')[1]} for c in required]}))
    return path


def note_span(data):
    return span(fingerprint(data)[1], 'people', 'note', 0, 8, 21)


def join(rel_id='r1', review=False):
    return {'relation_id': rel_id, 'kind': 'join', 'left': {'table': 'visits', 'column': 'pid'},
            'right': {'table': 'people', 'column': 'id'}, 'evidence': {'coverage': 1.0}, 'confidence': .9,
            'needs_review': review}


@pytest.fixture
def env(tmp_path):
    data = write_data(tmp_path)
    lab = write_detect_dir(tmp_path / 'detect', data, labels(), [note_span(data)], [join()])
    return tmp_path, data, lab


def run_select(tmp, data, lab, *extra, out='select', required=('people.score',)):
    args = ['select', '--data', str(data), '--spec', str(spec(tmp, required)), '--out', str(tmp / out)]
    return main(args + (['--labels', str(lab)] if lab else []) + list(extra))


def plan(tmp, out='select'):
    return json.loads((tmp / out / 'decisions.json').read_text())


# ---------------------------------------------------------------- provenance

def test_bound_select_then_search_keeps_provenance_and_plan_sha(env, monkeypatch):
    tmp, data, lab = env
    assert run_select(tmp, data, lab) == 0
    p = plan(tmp)
    assert p['status'] == 'policy_valid' and p['outcome']['approved'] is False
    prov = p['provenance']
    assert prov['bound'] and prov['schema'] == 'pets.select.provenance/1'
    assert prov['inputs'] == fingerprint(data)[0] and prov['dataset_fingerprint'] == fingerprint(data)[1]
    assert prov['labels_sha256'] == hashlib.sha256(lab.read_bytes()).hexdigest()
    assert prov['detector']['name'] == 'pets_detect_v3' and prov['confirm_sha256'] is None
    assert p['evidence']['spans'] == {'count': 1, 'by_column': {'people.note': 1}, 'stale': 0}
    text = (tmp / 'select' / 'decisions.json').read_text()
    assert 'Anna' not in text and 'Virtanen' not in text and 'not an approved release' in render_md(tmp)
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', 'test-only-key')
    assert main(['search', '--data', str(data), '--plan', str(tmp / 'select' / 'decisions.json'),
                 '--out', str(tmp / 'search')]) == 0
    s = plan(tmp, 'search')
    assert s['status'] == 'measured_ok' and s['outcome']['approved'] is True
    assert s['provenance'] == prov
    assert s['plan_sha256'] == hashlib.sha256((tmp / 'select' / 'decisions.json').read_bytes()).hexdigest()


def render_md(tmp, out='select'):
    return (tmp / out / 'decisions.md').read_text()


def rejected(capsys, code):
    err = capsys.readouterr().err
    assert f'[{code}]' in err, err
    return err


def test_one_changed_cell_rejects_labels_with_named_table(env, capsys):
    tmp, data, lab = env
    df = pd.read_csv(data / 'people.csv', dtype=str, keep_default_na=False)
    df.loc[1, 'score'] = '15'  # same schema and row count, different bytes
    df.to_csv(data / 'people.csv', index=False)
    assert run_select(tmp, data, lab) == 2
    assert 'people' in rejected(capsys, 'input_mismatch') and not (tmp / 'select').exists()


def test_replaced_labels_rejected(env, capsys):
    tmp, data, lab = env
    swapped = labels()
    swapped.loc[swapped.column.eq('score'), 'privacy_role'] = 'sensitive_attribute'
    swapped.to_csv(lab, index=False)
    assert run_select(tmp, data, lab) == 2
    rejected(capsys, 'labels_mismatch')


def test_labels_without_manifest_rejected(env, capsys):
    tmp, data, lab = env
    (lab.parent / 'manifest.json').unlink()
    assert run_select(tmp, data, lab) == 2
    rejected(capsys, 'manifest_missing')


def test_dataset_and_table_set_mismatch_rejected(tmp_path, capsys):
    data = write_data(tmp_path)
    lab = write_detect_dir(tmp_path / 'd1', data, labels(), [note_span(data)], dataset='other')
    assert run_select(tmp_path, data, lab, out='a') == 2
    rejected(capsys, 'dataset_mismatch')
    lab = write_detect_dir(tmp_path / 'd2', data, labels(), [note_span(data)])
    (data / 'extra.csv').write_text('x\n1\n')
    assert run_select(tmp_path, data, lab, out='b') == 2
    rejected(capsys, 'table_set_mismatch')


def test_search_rejects_plan_from_another_revision(env, monkeypatch, capsys):
    tmp, data, lab = env
    assert run_select(tmp, data, lab) == 0
    other = write_data(tmp, 'rev2')
    (other / 'people.csv').write_text((other / 'people.csv').read_text().replace('14', '13'))
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', 'test-only-key')
    assert main(['search', '--data', str(other), '--plan', str(tmp / 'select' / 'decisions.json'),
                 '--out', str(tmp / 'search')]) == 2
    assert 'people' in rejected(capsys, 'input_mismatch') and not (tmp / 'search').exists()
    unbound = plan(tmp)
    del unbound['provenance']
    (tmp / 'old.json').write_text(json.dumps(unbound))
    assert main(['search', '--data', str(data), '--plan', str(tmp / 'old.json'), '--out', str(tmp / 's2')]) == 2
    rejected(capsys, 'provenance_missing')


def test_legacy_detector_is_marked_unbound(tmp_path, monkeypatch):
    data = write_data(tmp_path)
    assert main(['select', '--data', str(data), '--no-purpose', 'internal', '--out', str(tmp_path / 'select')]) in (0, 2)
    p = plan(tmp_path)
    assert p['provenance']['bound'] is False and p['provenance']['labels_sha256'] is None
    assert p['provenance']['inputs'] == fingerprint(data)[0]
    assert any('provenance unbound' in w for w in p['warnings']) and 'UNBOUND' in render_md(tmp_path)


# ---------------------------------------------------------------- spans and linkage

def test_stale_span_offsets_and_ids_block(tmp_path):
    data = write_data(tmp_path)
    good = note_span(data)
    long = span(fingerprint(data)[1], 'people', 'note', 0, 8, 99)  # beyond the cell
    old = {**good, 'span_id': span('0' * 64, 'people', 'note', 0, 8, 21)['span_id']}  # other revision
    lab = write_detect_dir(tmp_path / 'detect', data, labels(), [good, long, old])
    assert run_select(tmp_path, data, lab) == 2
    p = plan(tmp_path)
    assert any(e.startswith('stale_span: 2 span(s)') for e in p['errors']) and p['evidence']['spans']['stale'] == 2


def test_missing_span_evidence_blocks_released_free_text_only(tmp_path):
    data = write_data(tmp_path)
    lab = write_detect_dir(tmp_path / 'detect', data, labels())
    assert run_select(tmp_path, data, lab, out='dropped') == 0
    assert any(w.startswith('missing_span_evidence: free-text column people.note') for w in plan(tmp_path, 'dropped')['warnings'])
    assert run_select(tmp_path, data, lab, out='released', required=('people.score', 'people.note')) == 2
    assert any(e.startswith('missing_span_evidence') for e in plan(tmp_path, 'released')['errors'])


@pytest.mark.parametrize('relations', [[join(review=True)],
                                       [join(), {**join('r2'), 'right': {'table': 'people', 'column': 'note'}}]])
def test_ambiguous_or_conflicting_join_blocks(tmp_path, relations):
    data = write_data(tmp_path)
    lab = write_detect_dir(tmp_path / 'detect', data, labels(), [note_span(data)], relations)
    assert run_select(tmp_path, data, lab, out='unused') == 0  # touches no released column: warning only
    assert any(w.startswith('ambiguous_join') for w in plan(tmp_path, 'unused')['warnings'])
    assert run_select(tmp_path, data, lab, required=('people.score', 'people.id')) == 2
    p = plan(tmp_path)
    assert any(e.startswith('ambiguous_join') for e in p['errors']) and p['evidence']['linkage']['ambiguous']


# ---------------------------------------------------------------- coverage and reviews

def test_whole_vocabulary_maps_to_a_policy_or_unsupported_label():
    for role in sorted(policy.ROLES):
        for sub in sorted(policy.TAXONOMY_SUBTYPES):
            for trust in policy.TRUST_LEVELS:
                c = policy.candidates({'privacy_role': role, 'subtype': sub, 'confidence': 1.0}, trust, True)
                actions = [r['action'] for r in c['rungs']]
                if c['unsupported']:
                    assert actions == ['DROP'] and c['needs_review'] and c['notes'][0].startswith('unsupported_label')
                    continue
                assert actions == ['DROP'] and trust == 'public' or [a for a in actions if a != 'DROP'], (role, sub, trust)
                if 'KEEP' in actions:
                    assert role not in policy.IDS and sub not in policy.ID_SUBTYPE_ROLE and sub != 'SECRET'


def test_unsupported_vocabulary_pair_is_named(tmp_path):
    data = write_data(tmp_path)
    # (URL gained a ladder in S5; AGGREGATE as a quasi-identifier still has none)
    vocab = [['non_sensitive', 'MEASUREMENT'], ['non_sensitive', 'SECRET'], ['quasi_identifier', 'AGGREGATE']]
    lab = write_detect_dir(tmp_path / 'detect', data, labels(), [note_span(data)], vocabulary=vocab)
    assert run_select(tmp_path, data, lab) == 0
    p = plan(tmp_path)
    assert [(u['role'], u['subtype']) for u in p['label_coverage']['vocabulary']['unsupported']] == \
        [('non_sensitive', 'SECRET'), ('quasi_identifier', 'AGGREGATE')]
    assert any(w.startswith('unsupported_label: 2 of 3') for w in p['warnings'])


def test_suggested_subject_is_reported_not_adopted(tmp_path):
    data = write_data(tmp_path)
    subject = {'relation_id': 'ab12ab12ab12ab12', 'kind': 'subject', 'left': {'table': 'people', 'column': 'score'}, 'right': None,
               'evidence': {}, 'confidence': .5, 'needs_review': True}
    lab = write_detect_dir(tmp_path / 'detect', data, labels(), [note_span(data)], [subject])
    assert run_select(tmp_path, data, lab) == 0
    p = plan(tmp_path)
    assert any(w.startswith('ambiguous_subject: detect relation ab12ab12ab12ab12') for w in p['warnings'])
    assert 'people.score' not in p['subject_keys'].values() and p['evidence']['linkage']['subjects'] == 1


def test_required_unsupported_label_blocks(tmp_path):
    data = write_data(tmp_path)
    lab_df = labels()
    lab_df.loc[lab_df.column.eq('score'), 'subtype'] = 'SECRET'
    lab = write_detect_dir(tmp_path / 'detect', data, lab_df, [note_span(data)])
    assert run_select(tmp_path, data, lab) == 2
    assert any(e.startswith('unsupported_label: people.score') for e in plan(tmp_path)['errors'])


def test_unconfirmed_required_review_blocks_and_confirmation_is_recorded(tmp_path):
    data = write_data(tmp_path)
    lab_df = labels()
    lab_df.loc[lab_df.column.eq('score'), 'needs_review'] = 'True'
    lab = write_detect_dir(tmp_path / 'detect', data, lab_df, [note_span(data)])
    assert run_select(tmp_path, data, lab, out='a') == 2
    assert any(e.startswith('review_required: people.score') for e in plan(tmp_path, 'a')['errors'])
    confirm = tmp_path / 'confirm.csv'
    confirm.write_text('table,column,privacy_role,subtype\npeople,score,non_sensitive,MEASUREMENT\n')
    assert run_select(tmp_path, data, lab, '--confirm', str(confirm), out='b') == 0
    p = plan(tmp_path, 'b')
    assert p['reviews'] == [{'table': 'people', 'column': 'score',
                             'detected': {'role': 'non_sensitive', 'subtype': 'MEASUREMENT', 'confidence': .95,
                                          'needs_review': True},
                             'confirmed': {'role': 'non_sensitive', 'subtype': 'MEASUREMENT'}, 'downgrade': False}]
    assert p['provenance']['confirm_sha256'] == hashlib.sha256(confirm.read_bytes()).hexdigest()


def test_downgrade_guard_and_recorded_downgrade(tmp_path):
    data = write_data(tmp_path)
    lab_df = labels()
    lab_df.loc[lab_df.column.eq('score'), ['privacy_role', 'subtype']] = ['sensitive_attribute', 'HEALTH_DATA']
    lab = write_detect_dir(tmp_path / 'detect', data, lab_df, [note_span(data)])
    confirm = tmp_path / 'confirm.csv'
    confirm.write_text('table,column,privacy_role,subtype\npeople,score,non_sensitive,MEASUREMENT\n')
    with pytest.raises(ValueError, match='downgrade'):
        run_select(tmp_path, data, lab, '--confirm', str(confirm), out='a')
    assert run_select(tmp_path, data, lab, '--confirm', str(confirm), '--allow-downgrade', out='b') == 0
    p = plan(tmp_path, 'b')
    assert p['reviews'][0]['downgrade'] is True and any('downgrade explicitly allowed' in w for w in p['warnings'])


# ---------------------------------------------------------------- runtime guard

def test_selection_never_reads_catalog_truth_or_gold_spans(env, monkeypatch):
    tmp, data, lab = env
    real = builtins.open

    def guarded(file, *args, **kwargs):
        name = str(file)
        if 'field_catalog' in name or '/truth/' in name or 'pii_spans' in name:
            pytest.fail(f'selection opened {name}')
        return real(file, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', guarded)
    monkeypatch.setattr(io, 'open', guarded)
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', 'test-only-key')
    assert run_select(tmp, data, lab) == 0
    assert main(['search', '--data', str(data), '--plan', str(tmp / 'select' / 'decisions.json'),
                 '--out', str(tmp / 'search')]) == 0


# ---------------------------------------------------------------- review fixes

def test_scanned_clean_free_text_column_is_not_missing_evidence(tmp_path):
    data = write_data(tmp_path)
    clean = {'people.note': {'cells': 3, 'spans': 0}}
    lab = write_detect_dir(tmp_path / 'clean', data, labels(), scanned=clean)
    assert run_select(tmp_path, data, lab, out='a', required=('people.score', 'people.note')) == 0
    assert not any('missing_span_evidence' in x for x in plan(tmp_path, 'a')['errors'] + plan(tmp_path, 'a')['warnings'])
    lab = write_detect_dir(tmp_path / 'unscanned', data, labels(), scanned={})
    assert run_select(tmp_path, data, lab, out='b', required=('people.score', 'people.note')) == 2
    assert any(e.startswith('missing_span_evidence: free-text column people.note') for e in plan(tmp_path, 'b')['errors'])


def test_missing_linkage_warns_and_blocks_released_join_or_subject_keys(tmp_path):
    data = write_data(tmp_path)
    lab = write_detect_dir(tmp_path / 'detect', data, labels(), [note_span(data)], linkage=False)
    assert run_select(tmp_path, data, lab, out='a') == 0
    p = plan(tmp_path, 'a')
    assert any(w.startswith('missing_linkage_evidence') for w in p['warnings']) and not p['evidence']['linkage']['present']
    assert run_select(tmp_path, data, lab, out='b', required=('people.score', 'people.id')) == 2
    assert any(e.startswith('missing_linkage_evidence') and 'people.id' in e for e in plan(tmp_path, 'b')['errors'])


def test_bound_labels_need_review_column(tmp_path, capsys):
    data = write_data(tmp_path)
    lab = write_detect_dir(tmp_path / 'detect', data, labels().drop(columns='needs_review'), [note_span(data)])
    assert run_select(tmp_path, data, lab) == 2
    rejected(capsys, 'labels_schema')


def test_artifact_free_strings_are_never_echoed(tmp_path):
    data = write_data(tmp_path)
    bad_span = {**note_span(data), 'span_id': 'Anna Virtanen', 'end': 999}
    rel = {**join('Anna Virtanen r1', review=True), 'left': {'table': 'people', 'column': 'Anna Virtanen'}}
    subject = {'relation_id': 'Mikko', 'kind': 'subject', 'left': {'table': 'x', 'column': 'Laine'}, 'right': None}
    lab = write_detect_dir(tmp_path / 'detect', data, labels(), [bad_span], [rel, subject])
    assert run_select(tmp_path, data, lab) == 2
    text = (tmp_path / 'select' / 'decisions.json').read_text() + render_md(tmp_path)
    assert 'Anna' not in text and 'Mikko' not in text and 'Laine' not in text
    p = plan(tmp_path)
    assert any('line 1' in e for e in p['errors']) and p['evidence']['linkage']['ambiguous'] == ['relation 0', 'relation 1']


@pytest.mark.parametrize('breakage', ['entry', 'linkage'])
def test_malformed_manifest_entry_or_linkage_json_is_named(tmp_path, capsys, breakage):
    data = write_data(tmp_path)
    lab = write_detect_dir(tmp_path / 'detect', data, labels(), [note_span(data)])
    manifest_path = lab.parent / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if breakage == 'entry':
        manifest['artifacts']['spans'] = 'spans.jsonl'
    else:
        (lab.parent / 'linkage.json').write_text('{not json')
        manifest['artifacts']['linkage']['sha256'] = hashlib.sha256(b'{not json').hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    assert run_select(tmp_path, data, lab) == 2
    rejected(capsys, 'manifest_schema')


def test_non_sensitive_url_in_a_person_table_is_not_kept_raw(tmp_path):
    from server.select.relations import discover
    from server.select.select import select
    tables = {'people': pd.DataFrame({'id': ['p1', 'p2'], 'name': ['A B', 'C D'], 'site': ['u1', 'u2'],
                                      'zip': ['20100', '20200'], 'score': ['1', '2']})}
    lab = pd.DataFrame([{'dataset': 'demo', 'table': 'people', 'column': c, 'privacy_role': r, 'subtype': s,
                         'confidence': .95, 'evidence': ''}
                        for c, r, s in [('id', 'record_key', 'PATIENT_ID'), ('name', 'direct_identifier', 'PERSON_NAME'),
                                        ('site', 'non_sensitive', 'URL'), ('zip', 'non_sensitive', 'POSTCODE'),
                                        ('score', 'non_sensitive', 'MEASUREMENT')]])
    req = {'source': 'none', 'dataset': 'demo', 'trust_level': 'internal', 'required': {}}
    cols = {c['column']: c for c in select(tables, lab, discover(tables, lab), req)['columns']}
    assert cols['site']['privacy_role'] == 'quasi_identifier' and cols['site']['action'] == 'DROP'
    assert cols['zip']['privacy_role'] == 'quasi_identifier' and cols['zip']['action'] == 'DROP'
    assert cols['score']['action'] == 'KEEP'


def test_embedded_identifier_released_in_a_revealing_form_warns_without_echoing(tmp_path):
    from server.select.artifacts import check_evidence
    path = tmp_path / 'linkage.json'
    rel = lambda rid, col: {'relation_id': rid, 'kind': 'embedded', 'left': {'table': 'people', 'column': col},  # noqa: E731
                            'right': None, 'evidence': {'encodes': ['SECRET-FREE-TEXT']}, 'confidence': .9,
                            'needs_review': False}
    path.write_text(json.dumps({'schema': 'pets.detect.linkage/1',
                                'relations': [rel('a' * 16, 'ip'), rel('b' * 16, 'id'), rel('c' * 16, 'gone')]}))
    tables = {'people': pd.DataFrame({'id': ['p1'], 'ip': ['10.0.0.1']})}
    plan = {'columns': [{'table': 'people', 'column': 'ip', 'action': 'HMAC', 'method': 'ipv4_prefix'},
                        {'table': 'people', 'column': 'id', 'action': 'HMAC', 'method': 'hmac_sha256'}],
            'joins': [], 'subject_keys': {}}
    lab = pd.DataFrame([label('people', 'id', 'record_key', 'PATIENT_ID'),
                        label('people', 'ip', 'technical_identifier', 'IP_ADDRESS')])
    errors, warnings, summary = check_evidence(plan, tables, lab, {'dataset_fingerprint': 'f' * 64,
                                                                   '_paths': {'linkage': path}})
    emb = [w for w in warnings if w.startswith('embedded_qi')]
    assert len(emb) == 1 and 'people.ip' in emb[0] and 'a' * 16 in emb[0]  # the /24 keeps provider/location
    assert not errors and summary['linkage']['embedded'] == 3
    assert 'SECRET-FREE-TEXT' not in json.dumps([errors, warnings, summary]) and 'gone' not in json.dumps(warnings)
