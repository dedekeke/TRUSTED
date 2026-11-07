"""Measured search on small artificial inputs."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from server.select.search import _Evaluator, search
from server.select.select import select

KEY = b"test-key"


def lab(table, column, role, subtype, conf=0.95):
    return {"dataset": "d", "table": table, "column": column, "privacy_role": role, "subtype": subtype,
            "confidence": conf, "evidence": "test; person table"}


def inputs(n=400):
    rng = np.random.default_rng(0)
    ts = pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 365 * 24, n), unit="h")
    cities = rng.choice(["Turku"] * 6 + ["Salo"] * 3 + [f"Village{i}" for i in range(12)], n)
    tables = {"visits": pd.DataFrame({
        "vid": [f"V{i:05d}" for i in range(n)],
        "pid": [f"P{i % 300:04d}" for i in range(n)],
        "arrival": ts.strftime("%Y-%m-%d %H:%M"),
        "city": cities,
        "score": rng.integers(0, 100, n).astype(str),
    })}
    labels = pd.DataFrame([lab("visits", "vid", "record_key", "RECORD_ID"),
                           lab("visits", "pid", "direct_identifier", "PATIENT_ID"),
                           lab("visits", "arrival", "quasi_identifier", "TIMESTAMP"),
                           lab("visits", "city", "quasi_identifier", "MUNICIPALITY"),
                           lab("visits", "score", "non_sensitive", "MEASUREMENT")])
    rel = {"keys": [{"column": "visits.vid"}], "joins": [], "subject_keys": {"visits": "visits.pid"}}
    req = {"source": "scenario", "scenario": "T", "dataset": "d", "trust_level": "controlled_research",
           "targets": {"k": 5}, "required": {"visits.arrival": ["HOUR"], "visits.city": ["CITY"]},
           "precision": {"visits.arrival": "hour"}, "joins": [], "warnings": []}
    return tables, labels, rel, req


def hour_task():
    def fn(orig, prot):
        a = pd.to_datetime(prot["visits"]["arrival"], errors="coerce").dt.hour.value_counts(normalize=True)
        b = pd.to_datetime(orig["visits"]["arrival"]).dt.hour.value_counts(normalize=True)
        return {"score": None if a.empty else 1 - 0.5 * float((a - b).abs().sum())}
    return SimpleNamespace(id="HOUR", fn=fn)


def big_city_task():
    def fn(orig, prot):
        o, p = orig["visits"]["city"], prot["visits"]["city"]
        return {"score": float((p[o == "Turku"] == "Turku").mean())}
    return SimpleNamespace(id="CITY", fn=fn)


def run(**kw):
    tables, labels, rel, req = inputs()
    plan = select(tables, labels, rel, req, release_id="T/test")
    return search(tables, plan, KEY, [hour_task(), big_city_task()], tables, **kw)


def test_search_coarsens_until_target_and_keeps_required_analyses():
    out = run()
    risk = out["measured"]["risk"]["visits"]
    assert risk["share_below_k"] <= 0.02 or out["status"] == "target_unmet"
    assert out["measured"]["risk"]["visits"]["share_below_k"] < out["search_trace"][0]["risk_k"]
    cols = {c["column"]: c for c in out["columns"]}
    assert cols["arrival"]["method"] in ("floor_hour", "week_hour", "month_hour", "year_hour")  # hour kept
    assert all(s >= 0.8 * out["measured"]["baseline_utility"][t] for t, s in out["measured"]["utility"].items())


def test_unmet_target_is_reported_not_lowered():
    out = run(budget=2)
    if out["status"] == "target_unmet":
        assert out["conflict"]["remaining_risk"]["visits"] > 0.02 and out["targets"]["k"] == 5


def test_deterministic():
    a, b = run(), run()
    assert [c.get("method") for c in a["columns"]] == [c.get("method") for c in b["columns"]]
    assert a["measured"] == b["measured"]
    assert a['search_trace'] == b['search_trace']


def test_blocked_plan_refused():
    tables, labels, rel, req = inputs()
    plan = {**select(tables, labels, rel, req), "status": "blocked"}
    with pytest.raises(ValueError):
        search(tables, plan, KEY)


@pytest.mark.parametrize('budget', [0, 51, True])
def test_invalid_budget_rejected(budget):
    with pytest.raises(ValueError, match='budget'):
        run(budget=budget)


def test_every_evaluation_traced_and_budgeted():
    out = run(budget=3)
    assert out['measured']['evaluations'] == len(out['search_trace']) == 3
    assert out['status'] == 'target_unmet'
    assert 'budget' in out['conflict']['reason']


def test_no_tasks_uses_information_loss_and_preserves_unknown_subjects():
    tables, labels, rel, req = inputs(40)
    rel['subject_keys'] = {}
    out = search(tables, select(tables, labels, rel, req), KEY)
    assert out['status'] == 'target_unmet'
    assert out['conflict']['unknown_subjects'] == {'visits': 40}


def test_repeated_subject_rows_cannot_inflate_k():
    tables, labels, rel, req = inputs(40)
    tables['visits']['pid'] = 'one-person'
    out = search(tables, select(tables, labels, rel, req), KEY)
    assert out['status'] == 'target_unmet'
    assert out['measured']['risk']['visits']['k_anonymity']['min_k'] == 1


def test_homogeneous_majority_sensitive_group_fails_l():
    tables, labels, rel, req = inputs(40)
    tables['visits']['score'] = 'same'
    labels.loc[labels.column == 'score', ['privacy_role', 'subtype']] = ['sensitive_attribute', 'HEALTH_DATA']
    req['required']['visits.score'] = ['SCORE']
    req['targets']['l'] = 2
    out = search(tables, select(tables, labels, rel, req), KEY)
    assert out['status'] == 'target_unmet'
    assert out['measured']['risk']['visits']['sensitive']['score']['l_diversity']['min_distinct_l'] == 1


def test_unanswerable_baseline_is_never_a_pass():
    tables, labels, rel, req = inputs(40)
    task = SimpleNamespace(id='BROKEN', fn=lambda o, p: {'score': None})
    out = search(tables, select(tables, labels, rel, req), KEY, [task])
    assert out['status'] == 'target_unmet'
    assert 'BROKEN' in out['conflict']['unanswerable_tasks']


def test_joined_subject_resolution_and_blanks():
    from server.select.preview import resolved_subjects
    tables = {'p': pd.DataFrame({'id': ['a', 'b'], 'person': ['x', '']}),
              'c': pd.DataFrame({'parent': ['a', 'a', 'b', 'orphan']})}
    plan = {'subject_keys': {'c': 'p.person'}, 'joins': [{'child': 'c.parent', 'parent': 'p.id'}]}
    ids = resolved_subjects(tables, plan, 'c')
    assert ids.iloc[:2].tolist() == ['x', 'x']
    assert ids.iloc[2:].isna().all()


def test_t_closeness_is_measured_and_enforced():
    tables, labels, rel, req = inputs(40)
    labels.loc[labels.column == 'score', ['privacy_role', 'subtype']] = ['sensitive_attribute', 'HEALTH_DATA']
    req['required']['visits.score'] = ['SCORE']
    req['targets'].update(k=1, l=1, t=0.0)
    task = SimpleNamespace(id='SCORE', fn=lambda o, p: {'score': 1.})
    out = search(tables, select(tables, labels, rel, req), KEY, [hour_task(), big_city_task(), task])
    assert 't_closeness' in out['measured']['risk']['visits']['sensitive']['score']
    if out['status'] == 'measured_ok':
        assert out['measured']['risk']['visits']['sensitive']['score']['t_closeness']['max_t'] == 0


def test_plateau_steps_can_reach_a_joint_merge():
    tables, labels, rel, req = inputs(4)
    tables['visits']['arrival'] = ['2025-01-01 01:00', '2025-01-01 02:00',
                                  '2025-01-02 01:00', '2025-01-02 02:00']
    tables['visits']['city'] = ['a', 'b', 'c', 'd']
    req.update(source='spec', precision={}, targets={'k': 4}, required={'visits.arrival': ['TIME'], 'visits.city': ['CITY']})
    out = search(tables, select(tables, labels, rel, req), KEY)
    assert out['status'] == 'measured_ok'
    assert out['measured']['risk']['visits']['k_anonymity']['min_k'] == 4


def test_finest_degradation_does_not_lower_utility_baseline():
    tables, labels, rel, req = inputs(40)
    def score(orig, prot):
        return {'score': .5 if '00' in str(prot['visits']['arrival'].iloc[0]) else 1.}
    # Explicitly distinguish original precision from every floor-hour candidate.
    tables['visits']['arrival'] = tables['visits']['arrival'].str.replace(':00', ':37')
    out = search(tables, select(tables, labels, rel, req), KEY,
                 [SimpleNamespace(id='HOUR', fn=score), big_city_task()])
    assert out['measured']['baseline_utility']['HOUR'] == 1.
    assert out['status'] == 'target_unmet'


def suppression_plan():
    tables, labels, rel, req = inputs(100)
    tables['visits']['pid'] = [f'p{i}' for i in range(100)]
    tables['visits']['city'] = ['common'] * 98 + ['x', 'y']
    req.update(source='spec', required={'visits.city': ['CITY']}, precision={}, targets={'k': 2})
    plan = select(tables, labels, rel, req)
    city = next(c for c in plan['columns'] if c['column'] == 'city')
    city['rungs'] = city['rungs'][:1]
    return tables, plan


def test_local_suppression_budget_and_preview_parity():
    tables, plan = suppression_plan()
    out = search(tables, plan, KEY)
    assert out['status'] == 'measured_ok'
    assert out['suppression']
    evaluator = _Evaluator(tables, out, KEY, [], tables)
    levels = next(e['levels'] for e in out['search_trace'] if e['evaluation'] == out['measured']['chosen_evaluation'])
    transformed = evaluator.build(levels, out['suppression'])
    assert transformed['visits']['city'].eq('').sum() == 2
    assert out['search_trace'][-1]['suppressed_fraction'] == .02
    assert out['measured']['risk']['visits']['k_anonymity']['min_k'] == 2


def test_local_suppression_rejected_when_utility_breaks():
    tables, plan = suppression_plan()
    task = SimpleNamespace(id='CITY', fn=lambda o, p: {'score': float(p['visits']['city'].notna().all())})
    out = search(tables, plan, KEY, [task])
    assert out['status'] == 'target_unmet'
    assert out['suppression'] == {}
    assert out['measured']['evaluations'] == len(out['search_trace']) == 3


def test_suppression_over_two_percent_is_not_attempted():
    tables, plan = suppression_plan()
    tables['visits'].loc[97, 'city'] = 'z'
    out = search(tables, plan, KEY)
    assert out['status'] == 'target_unmet'
    assert out['suppression'] == {}


def test_numeric_sensitive_t_uses_numeric_emd():
    tables, labels, rel, req = inputs(40)
    labels.loc[labels.column == 'score', ['privacy_role', 'subtype']] = ['sensitive_attribute', 'MEASUREMENT']
    req.update(source='spec', required={'visits.score': ['SCORE'], 'visits.city': ['CITY']})
    out = search(tables, select(tables, labels, rel, req), KEY)
    assert out['measured']['risk']['visits']['sensitive']['score']['t_closeness']['numeric'] is True
    assert any('visits.score' in step['levels'] and step['levels']['visits.score'] > 0
               for step in out['search_trace'])


def test_budget_exhaustion_keeps_best_measured_partial_round():
    tables, labels, rel, req = inputs(4)
    tables['visits']['arrival'] = ['2025-01-01 01:00', '2025-01-01 02:00',
                                  '2025-01-02 01:00', '2025-01-02 02:00']
    tables['visits']['city'] = ['a', 'b', 'c', 'd']
    req.update(source='spec', precision={}, targets={'k': 4},
               required={'visits.arrival': ['TIME'], 'visits.city': ['CITY']})
    out = search(tables, select(tables, labels, rel, req), KEY, budget=14)
    accepted = [step for step in out['search_trace'] if step['accepted']]
    assert len(accepted) > 1
    assert out['measured']['risk'] == accepted[-1]['risk']
    assert out['measured']['evaluations'] <= 14


def test_budget_exhaustion_chooses_feasible_floor_probe():
    tables, plan = suppression_plan()
    city = next(c for c in plan['columns'] if c['column'] == 'city')
    city['rungs'] += [{'action': 'GENERALISE', 'method': 'merge_rare', 'params': {'min_count': 200}}]
    out = search(tables, plan, KEY, budget=2)
    assert out['status'] == 'measured_ok'
    assert out['measured']['evaluations'] == 2
    assert next(c for c in out['columns'] if c['column'] == 'city')['method'] == 'merge_rare'


def test_derived_age_baseline_uses_exact_original_age():
    tables, labels, rel, req = inputs(40)
    tables['visits']['dob'] = '2000-01-01'
    labels = pd.concat([labels, pd.DataFrame([lab('visits', 'dob', 'quasi_identifier', 'BIRTH_DATE')])], ignore_index=True)
    req.update(source='spec', required={'visits.dob': ['AGE'], 'visits.arrival': ['AGE']})
    plan = select(tables, labels, rel, req)
    task = SimpleNamespace(id='AGE', fn=lambda o, p: {'score': float(pd.to_numeric(p['visits']['age'], errors='coerce').notna().all())})
    out = search(tables, plan, KEY, [task])
    assert out['measured']['baseline_utility']['AGE'] == 1.
    assert out['status'] == 'target_unmet'
    assert out['measured']['utility']['AGE'] == 0.


def test_local_suppression_can_solve_l_when_k_already_passes():
    tables, labels, rel, req = inputs(1000)
    tables['visits']['pid'] = [f'p{i}' for i in range(1000)]
    tables['visits']['city'] = ['common'] * 990 + ['rare-a'] * 5 + ['rare-b'] * 5
    tables['visits']['score'] = ['A', 'B'] * 495 + ['A'] * 5 + ['B'] * 5
    labels.loc[labels.column == 'score', ['privacy_role', 'subtype']] = ['sensitive_attribute', 'HEALTH_DATA']
    req.update(source='spec', required={'visits.city': ['CITY'], 'visits.score': ['SCORE']},
               precision={}, targets={'k': 5, 'l': 2})
    plan = select(tables, labels, rel, req)
    for c in plan['columns']:
        if c['column'] in ('city', 'score'):
            c['rungs'] = c['rungs'][:1]
    out = search(tables, plan, KEY)
    assert out['status'] == 'measured_ok'
    assert out['search_trace'][0]['risk']['visits']['share_below_k'] == 0
    assert out['measured']['risk']['visits']['sensitive']['score']['l_diversity']['min_distinct_l'] == 2
    evaluator = _Evaluator(tables, out, KEY, [], tables)
    levels = next(e['levels'] for e in out['search_trace'] if e['evaluation'] == out['measured']['chosen_evaluation'])
    transformed = evaluator.build(levels, out['suppression'])
    assert transformed['visits']['city'].eq('').sum() == 10


@pytest.mark.parametrize('subtype, values', [('PATIENT_ID', [' person', 'person', 'person ']),
                                            ('NATIONAL_ID', ['010101-123a', '010101-123A', ' 010101-123a '])])
def test_subject_normalization_matches_pseudonymization(subtype, values):
    from server.select.preview import resolved_subjects
    tables = {'p': pd.DataFrame({'pid': values})}
    plan = {'subject_keys': {'p': 'p.pid'}, 'columns': [{'table': 'p', 'column': 'pid', 'subtype': subtype}]}
    assert resolved_subjects(tables, plan, 'p').nunique() == 1


def test_without_t_target_only_chosen_plan_measures_t(monkeypatch):
    from pets_eval import privacy
    tables, labels, rel, req = inputs(40)
    labels.loc[labels.column == 'score', ['privacy_role', 'subtype']] = ['sensitive_attribute', 'MEASUREMENT']
    req.update(source='spec', required={'visits.score': ['SCORE'], 'visits.city': ['CITY']})
    original = privacy.t_closeness
    calls = []
    def measured(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        return result
    monkeypatch.setattr(privacy, 't_closeness', measured)
    out = search(tables, select(tables, labels, rel, req), KEY)
    assert len(calls) == 1
    assert out['measured']['risk']['visits']['sensitive']['score']['t_closeness'] == calls[0]
    assert any(not step['risk']['visits']['sensitive']['score']['t_closeness']['evaluated']
               for step in out['search_trace'] if step['risk'])


def test_configured_t_is_measured_for_every_candidate():
    tables, labels, rel, req = inputs(40)
    labels.loc[labels.column == 'score', ['privacy_role', 'subtype']] = ['sensitive_attribute', 'MEASUREMENT']
    req.update(source='spec', targets={'k': 1, 't': 0.0},
               required={'visits.score': ['SCORE'], 'visits.city': ['CITY']})
    out = search(tables, select(tables, labels, rel, req), KEY)
    for step in out['search_trace']:
        if step['risk']:
            assert step['risk']['visits']['sensitive']['score']['t_closeness']['evaluated']


def test_conflicts_name_subjects_and_sensitive_targets():
    tables, labels, rel, req = inputs(40)
    tables['visits']['score'] = 'same'
    tables['visits'].loc[0, 'pid'] = ''
    labels.loc[labels.column == 'score', ['privacy_role', 'subtype']] = ['sensitive_attribute', 'HEALTH_DATA']
    req.update(source='spec', targets={'k': 5, 'l': 2}, required={'visits.score': ['SCORE']})
    out = search(tables, select(tables, labels, rel, req), KEY)
    assert 'visits: 1 rows have unresolved subject identity' in out['conflict']['violations']
    assert 'visits.score: l=1 < 2' in out['conflict']['violations']


def test_chosen_rungs_and_rejections_are_explained():
    from server.select.select import render
    tables, labels, rel, req = inputs()
    def exact_city(orig, prot):
        return {'score': float(prot['visits']['city'].equals(orig['visits']['city']))}
    out = search(tables, select(tables, labels, rel, req), KEY,
                 [hour_task(), SimpleNamespace(id='CITY', fn=exact_city)])
    city = next(c for c in out['columns'] if c['column'] == 'city')
    assert city['rejected_rungs']
    assert 'CITY' in city['rejected_rungs'][0]['reason']
    assert 'Chosen rung' in city['selection_explanation']
    assert city['selection_explanation'] in render(out)
    assert out['measured']['chosen_evaluation'] in {step['evaluation'] for step in out['search_trace']}


def test_success_clears_an_old_unmet_conflict():
    tables, plan = suppression_plan()
    plan['conflict'] = {'reason': 'old failure'}
    out = search(tables, plan, KEY)
    assert out['status'] == 'measured_ok'
    assert 'conflict' not in out


def test_search_cli_writes_decisions_and_diagnostics_without_export(tmp_path, monkeypatch, capsys):
    import json
    from server.select.__main__ import main
    from server.select import transform
    tables, labels, rel, req = inputs(40)
    req['source'] = 'spec'
    tables['visits'].loc[0, 'pid'] = ''
    plan = select(tables, labels, rel, req)
    data = tmp_path / 'data'
    data.mkdir()
    tables['visits'].to_csv(data / 'visits.csv', index=False)
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    def no_export(*args, **kwargs):
        pytest.fail('selection must not call transform.apply')
    monkeypatch.setattr(transform, 'apply', no_export)
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', 'test-key')
    out = tmp_path / 'search'
    assert main(['search', '--data', str(data), '--plan', str(plan_path),
                 '--out', str(out), '--budget', '2']) == 3
    measured = json.loads((out / 'decisions.json').read_text())
    assert measured['measured']['evaluations'] == 2
    assert {p.name for p in out.iterdir()} == {'decisions.json', 'decisions.md'}
    assert 'unresolved subject identity' in capsys.readouterr().out


@pytest.mark.parametrize('t, tried', [(None, False), (0.0, True)])
def test_greedy_skips_sensitive_steps_unless_t_is_a_target(t, tried):
    tables, labels, rel, req = inputs(400)
    labels.loc[labels.column == 'score', ['privacy_role', 'subtype']] = ['sensitive_attribute', 'MEASUREMENT']
    req.update(source='spec', precision={}, required={'visits.arrival': ['HOUR'], 'visits.city': ['CITY'],
                                                      'visits.score': ['SCORE']},
               targets={'k': 50, 'l': 2, **({} if t is None else {'t': t})})
    out = search(tables, select(tables, labels, rel, req), KEY)
    greedy = [e['changed_column'] for e in out['search_trace'] if e['phase'] == 'greedy']
    assert greedy and ('visits.score' in greedy) is tried
    # the budget goes to quasi-identifier rungs: every allowed city rung is reached in combination
    if not tried:
        assert max(e['levels']['visits.city'] for e in out['search_trace'] if e['phase'] == 'greedy') == 3
