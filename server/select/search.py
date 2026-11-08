"""Bounded, deterministic measured search over policy ladders; no attacker inputs."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import math

import numpy as np
import pandas as pd
from pets_eval import privacy

from server.actions import age_years

from . import preview as T
from .policy import NUMERIC


def _items(plan):
    columns = [c for c in plan['columns'] if c['action'] != 'DROP' and
               c['privacy_role'] in ('quasi_identifier', 'sensitive_attribute')]
    return sorted(columns + plan.get('derived', []), key=lambda c: (c['table'], c['column']))


def _ref(c):
    return f"{c['table']}.{c['column']}"


def _subject_col(plan, table):
    ref = (plan.get('subject_keys') or {}).get(table)
    return ref.split('.', 1)[1] if ref and ref.split('.', 1)[0] == table else None


class _Evaluator:
    def __init__(self, tables, plan, key, tasks, orig, spans=None):
        self.tables, self.plan, self.key, self.tasks, self.orig = tables, plan, key, tasks or [], orig
        self.spans = spans or {}  # validated Detect spans per free-text column: previews redact as the export will
        self.cache = {}
        self.metric_cache = {}
        self.subjects = {}
        for table in tables:
            self.subjects[table] = T.resolved_subjects(tables, plan, table)

    def build(self, levels, suppression=None):
        out = {}
        for table, td in self.plan['tables'].items():
            if td['action'] != 'RELEASE':
                continue
            res = {}
            for c in [c for c in self.plan['columns'] if c['table'] == table] + [
                    d for d in self.plan.get('derived', []) if d['table'] == table]:
                level = levels.get(_ref(c))
                cache_key = (_ref(c), level)
                if cache_key not in self.cache:
                    rung = c['rungs'][level] if level is not None else c
                    if 'sources' in c:
                        value = T.derive_age_band(self.tables[table], *c['sources'], **rung['params'], ref_date=c.get('ref_date'))
                    else:
                        value = T.apply_column(self.tables[table][c['column']], {**c, **rung}, self.key,
                                               self.plan['release_id'], self.tables[table], self.plan['columns'],
                                               self.spans.get(_ref(c)) if c.get('action') == 'REDACT' else None)[0]
                    self.cache[cache_key] = value
                if self.cache[cache_key] is not None:
                    res[c['column']] = self.cache[cache_key]
            df = pd.DataFrame(res, index=self.tables[table].index)
            if suppression and table in suppression:
                rule = suppression[table]
                rows = T.small_classes(df, rule['qis'], self.subjects[table], rule['k'])
                df.loc[rows, rule['qis']] = ''
            out[table] = df
        return out

    def qis(self, table, df):
        cols = [c['column'] for c in self.plan['columns'] if c['table'] == table and
                c['privacy_role'] == 'quasi_identifier']
        cols += [c['column'] for c in self.plan.get('derived', []) if c['table'] == table]
        return [c for c in cols if c in df]

    def risk(self, prot, measure_t=False):
        out = {}
        k = self.plan['targets']['k']
        measure_t = measure_t or 't' in self.plan['targets']
        for table, df in prot.items():
            qis = self.qis(table, df)
            subjects = self.subjects[table]
            unknown = int(subjects.isna().sum())
            # One contribution per subject/class; repeated visits never inflate k. Unresolved rows of a class
            # together count as one person (T.with_unknown), the most conservative reading.
            known = df.copy()
            marker = object()
            known[marker] = T.with_unknown(subjects).values
            people = known.drop_duplicates([marker] + qis)
            km = privacy.k_anonymity(people, qis, thresholds=(k,))
            sizes = privacy.class_sizes(people, qis)
            r = {'qis': qis, 'rows': len(df), 'unknown_subject_rows': unknown,
                 'unknown_subject_share': unknown / len(df) if len(df) else 0.,
                 'k_anonymity': km, 'sample_uniqueness': privacy.sample_uniqueness(people, qis),
                 'share_below_k': float((sizes < k).mean()) if len(sizes) else 0.,
                 'mean_reid': float((1 / sizes).mean()) if len(sizes) else 0.,
                 'sensitive': {}}
            for c in self.plan['columns']:
                s = c['column']
                if c['table'] != table or c['privacy_role'] != 'sensitive_attribute' or s not in df:
                    continue
                # Multi-valued subjects contribute once per distinct class/value, never once per visit.
                values = known.drop_duplicates(list(dict.fromkeys([marker] + qis + [s])))
                fingerprint = sha256(pd.util.hash_pandas_object(values[qis + [s]].astype(str), index=False).values.tobytes()).digest()
                metric_key = (table, tuple(qis), s, fingerprint, measure_t)
                if metric_key not in self.metric_cache:
                    self.metric_cache[metric_key] = (privacy.l_diversity(values, qis, s),
                        privacy.t_closeness(values, qis, s, numeric=c.get('subtype') in NUMERIC) if measure_t else
                        {'evaluated': False, 'reason': 'no t target; measured on the chosen plan'})
                lm, tm = self.metric_cache[metric_key]
                r['sensitive'][s] = {'l_diversity': lm, 't_closeness': tm}
            r['share_below_l'] = float(any(v['l_diversity'].get('min_distinct_l', 0) <
                                                   self.plan['targets'].get('l', 1) for v in r['sensitive'].values()))
            out[table] = r
        return out

    def utility(self, prot):
        scores = {}
        p = {t: df.replace('', np.nan) for t, df in prot.items()}
        for task in self.tasks:
            try:
                result = task.fn(self.orig, p)
                score = result.get('score')
                scores[task.id] = float(score) if score is not None and math.isfinite(float(score)) and result.get('answerable', True) else None
            except Exception:
                scores[task.id] = None
        return scores


def _unknown_breach(r: dict, targets: dict) -> bool:
    """S4: unresolved subjects are allowed up to targets['max_unknown_subjects'] (plans without it: none)."""
    share = r.get('unknown_subject_share', 1.0 if r['unknown_subject_rows'] else 0.0)
    return bool(r['unknown_subject_rows']) and share > targets.get('max_unknown_subjects', 0.0)


def risk_violations(risk: dict, targets: dict) -> list[str]:
    """Named k/l/t and subject-identity breaches of measured risk; empty means the risk targets are met."""
    out = []
    for table, r in risk.items():
        if _unknown_breach(r, targets):
            out.append(f"{table}: {r['unknown_subject_rows']} rows ({r['unknown_subject_share']:.1%}) have unresolved "
                       f"subject identity, above {targets.get('max_unknown_subjects', 0):.0%}")
        if r['share_below_k'] > 0:
            out.append(f"{table}: k={r['k_anonymity'].get('min_k')} < {targets['k']}; "
                       f"{r['share_below_k']:.2%} of known subject/class entries below target")
        for column, metrics in r['sensitive'].items():
            observed_l = metrics['l_diversity'].get('min_distinct_l', 0)
            if observed_l < targets.get('l', 1):
                out.append(f"{table}.{column}: l={observed_l} < {targets.get('l', 1)}")
            if 't' in targets and metrics['t_closeness'].get('max_t', 1.) > targets['t']:
                out.append(f"{table}.{column}: t={metrics['t_closeness'].get('max_t')} > {targets['t']}")
    return out


def _worst(risk, key):
    return max((r.get(key, 0.) for r in risk.values()), default=0.)


def _info_loss(levels, items):
    return float(np.mean([levels[_ref(c)] / max(1, len(c['rungs']) - 1) for c in items])) if items else 0.


def _outcome(plan, current, failed, tau, base, budget, used, unexplored):
    targets = {k: v for k, v in plan['targets'].items() if k != 'notes'}
    tasks = {}
    for ref, ids in plan.get('required', {}).items():
        tasks.setdefault(ref, []).extend(t for t in ids if not t.startswith('any_of:'))

    def needs(table, column=None):
        refs = [f'{table}.{column}'] if column and tasks.get(f'{table}.{column}') else \
            [r for r in tasks if r.split('.', 1)[0] == table]
        return sorted({t for r in refs for t in tasks[r]})

    achieved, violations = {}, []
    for table, r in current['risk'].items():
        ls = {c: m['l_diversity'].get('min_distinct_l', 0) for c, m in r['sensitive'].items()}
        ts = {c: m['t_closeness'].get('max_t') for c, m in r['sensitive'].items()}
        achieved[table] = {'min_k': r['k_anonymity'].get('min_k'), 'share_below_k': r['share_below_k'],
                           'unknown_subject_rows': r['unknown_subject_rows'], 'l': ls, 't': ts}
        if _unknown_breach(r, targets):
            violations.append({'metric': 'subject_identity', 'table': table,
                               'target': targets.get('max_unknown_subjects', 0.0),
                               'achieved': round(r['unknown_subject_share'], 4),
                               'rows': r['unknown_subject_rows'], 'requirements': needs(table)})
        if r['share_below_k']:
            violations.append({'metric': 'k', 'table': table, 'target': targets['k'],
                               'achieved': r['k_anonymity'].get('min_k'), 'share_below_k': r['share_below_k'],
                               'requirements': needs(table)})
        for column, l in ls.items():
            if l < targets.get('l', 1):
                violations.append({'metric': 'l', 'table': table, 'column': column, 'target': targets.get('l', 1),
                                   'achieved': l, 'requirements': needs(table, column)})
            if 't' in targets and (ts[column] is None or ts[column] > targets['t']):
                violations.append({'metric': 't', 'table': table, 'column': column, 'target': targets['t'],
                                   'achieved': ts[column], 'requirements': needs(table, column)})
    achieved['utility'] = current['utility']
    for task in failed:
        violations.append({'metric': 'utility', 'table': None, 'target': None if base.get(task) is None else tau * base[task],
                           'achieved': current['utility'].get(task), 'requirements': [task]})
    # approval also needs inputs bound to a detect manifest; the built-in detector is never approval evidence
    bound = (plan.get('provenance') or {}).get('bound') is True
    issues = [] if bound else ['provenance_unbound']
    return {'policy_valid': True, 'targets_met': not violations, 'approved': plan['status'] == 'measured_ok' and bound,
            'issues': issues,
            'budget': {'used': used, 'limit': budget, 'exhausted': used >= budget and unexplored > 0,
                       'unexplored': unexplored},
            'targets': {**targets, 'tau': tau}, 'achieved': achieved, 'violations': violations}


def search(tables, plan, key, tasks=None, orig=None, budget=50, tau=0.8, spans=None):
    """Return chosen plan, measured results, requirement floors and every evaluated candidate."""
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 50:
        raise ValueError('budget must be an integer from 1 to 50')
    if not math.isfinite(tau) or not 0 < tau <= 1:
        raise ValueError('tau must be in (0, 1]')
    targets = plan.get('targets', {})
    for name in ('k', 'l'):
        value = targets.get(name, 1)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f'{name} must be a positive integer')
    if not 0 <= targets.get('max_suppression', .02) <= .02:
        raise ValueError('local suppression budget must be between 0 and 0.02')
    if 't' in targets and (not math.isfinite(targets['t']) or not 0 <= targets['t'] <= 1):
        raise ValueError('t must be between 0 and 1')
    if not key:
        raise ValueError('an HMAC key is required')
    T.check_plan(tables, plan)
    if plan['status'] == 'blocked':
        raise ValueError('cannot search a blocked plan')
    ev = _Evaluator(tables, plan, key, tasks, orig if orig is not None else tables, spans)
    items = _items(plan)
    levels = {_ref(c): 0 for c in items}
    floors = {_ref(c): 0 for c in items}
    trace, cache, limits = [], {}, {}
    unexplored = 0  # candidates the search would still try; > 0 at a budget stop means budget_exhausted

    def evaluate(lv, phase, suppression=None, changed_column=None):
        cache_key = (tuple(sorted(lv.items())), tuple(sorted((suppression or {}).keys())))
        if cache_key in cache:
            return cache[cache_key]
        if len(trace) >= budget:
            return None
        prot = ev.build(lv, suppression)
        risk, utility = ev.risk(prot), ev.utility(prot)
        loss = _info_loss(lv, items)
        suppressed = 0.
        if suppression:
            before = ev.build(lv)
            count = sum(int(T.small_classes(before[t], rule['qis'], ev.subjects[t], rule['k']).sum())
                        for t, rule in suppression.items())
            suppressed = count / max(1, sum(len(df) for df in before.values()))
            loss += suppressed
        entry = {'evaluation': len(trace) + 1, 'phase': phase, 'levels': dict(lv), 'risk': risk,
                 'risk_k': _worst(risk, 'share_below_k'), 'utility': utility,
                 'information_loss': loss, 'suppressed_fraction': suppressed, 'accepted': False,
                 'changed_column': changed_column}
        trace.append(entry)
        cache[cache_key] = entry
        return entry

    baseline = evaluate(levels, 'baseline')
    baseline['accepted'] = True
    # Keep required schema/derived fields and shared pseudonyms, but restore source precision.
    minimized = ev.build(levels)
    for c in plan['columns']:
        if c['action'] != 'DROP' and c['privacy_role'] not in ('direct_identifier', 'technical_identifier', 'record_key', 'free_text'):
            minimized[c['table']][c['column']] = tables[c['table']][c['column']]
    for d in plan.get('derived', []):
        minimized[d['table']][d['column']] = age_years(tables[d['table']], *d['sources'], d.get('ref_date'))
    base = {task.id: None for task in ev.tasks}
    if ev.tasks and len(trace) >= budget:
        unexplored += 1
    elif ev.tasks:
        base = ev.utility(minimized)
        trace.append({'evaluation': len(trace) + 1, 'phase': 'utility_baseline', 'levels': {},
                      'risk': {}, 'utility': base, 'accepted': False})
    if plan.get('source') == 'scenario':
        for ids in plan.get('required', {}).values():
            for task_id in ids:
                if not task_id.startswith('any_of:'):
                    base.setdefault(task_id, None)

    def failures(result):
        return [t for t, b in base.items() if b is None or result['utility'].get(t) is None or result['utility'][t] < tau * b]

    def met(result):
        return not risk_violations(result['risk'], targets) and not failures(result)

    def risk_score(result):
        score = 0.
        for r in result['risk'].values():
            score += r['share_below_k'] + r['mean_reid'] + r['sample_uniqueness']
            for metrics in r['sensitive'].values():
                score += max(0, targets.get('l', 1) - metrics['l_diversity'].get('min_distinct_l', 0))
                if 't' in targets:
                    score += max(0., metrics['t_closeness'].get('max_t', 1.) - targets['t'])
        return score

    # Probe independently, one rung at a time against the finest allowed plan.
    for c in items:
        ref = _ref(c)
        for level in range(1, len(c['rungs'])):
            candidate = evaluate({**levels, ref: level}, 'requirement_floor', changed_column=ref)
            if candidate is None:
                limits[ref] = 'evaluation budget exhausted during floor probes'
                unexplored += len(c['rungs']) - level
                break
            bad = failures(candidate)
            if bad:
                limits[ref] = f"{', '.join(bad)} needs {c['rungs'][level - 1]['method'] or c['rungs'][level - 1]['action']}"
                candidate['reason'] = limits[ref]
                break
            floors[ref] = level
        rung = c['rungs'][floors[ref]]
        limits.setdefault(ref, f"{', '.join(c.get('required_by', [])) or 'policy'}: coarsest allowed "
                               f"{rung['method'] or rung['action']} {rung['params']}")
    current = baseline
    stalled = False
    while not met(current) and len(trace) < budget:
        best = None
        complete = True
        for c in items:
            ref = _ref(c)
            if levels[ref] >= floors[ref]:
                continue
            # Without t, coarsening a sensitive value cannot raise k or l (only lower l): dominated, skip it.
            if c.get('privacy_role') == 'sensitive_attribute' and 't' not in targets:
                continue
            trial = {**levels, ref: levels[ref] + 1}
            candidate = evaluate(trial, 'greedy', changed_column=ref)
            if candidate is None:
                complete = False
                break
            bad = failures(candidate)
            if bad:
                candidate['reason'] = 'combined utility floor: ' + ', '.join(bad)
                continue
            gain = risk_score(current) - risk_score(candidate)
            loss = (sum(max(0., current['utility'][t] - candidate['utility'][t]) for t in base)
                    if base else max(0., candidate['information_loss'] - current['information_loss']))
            ratio = gain / loss if loss > 0 else (math.inf if gain > 0 else 0.)
            if gain >= 0 and (best is None or ratio > best[0]):
                best = ratio, trial, candidate
        if best is None:
            stalled = True
            break
        _, levels, current = best
        current['accepted'] = True
        if not complete:
            break
    if not met(current) and not stalled:
        unexplored += sum((tuple(sorted({**levels, _ref(c): levels[_ref(c)] + 1}.items())), ()) not in cache
                          for c in items if levels[_ref(c)] < floors[_ref(c)] and
                          (c.get('privacy_role') != 'sensitive_attribute' or 't' in targets))
    suppression = {}
    if not met(current) and len(trace) >= budget:
        unexplored += 1  # local suppression not tried
    elif not met(current):
        prot = ev.build(levels)
        rules = {}
        cap = targets.get('max_suppression', .02)
        for table, df in prot.items():
            qis = ev.qis(table, df)
            threshold = targets['k']
            small = T.small_classes(df, qis, ev.subjects[table], threshold)
            # Merge rare classes within budget even when k passes but l/t still fails.
            keys = pd.util.hash_pandas_object(df[qis].astype(str), index=False)
            sizes = ev.subjects[table].groupby(keys).transform('nunique')
            for size in sorted(sizes.unique()):
                if size < threshold:
                    continue
                trial = T.small_classes(df, qis, ev.subjects[table], int(size) + 1)
                if len(df) and int(trial.sum()) / len(df) <= cap:
                    threshold, small = int(size) + 1, trial
                else:
                    break
            if len(df) and 0 < int(small.sum()) / len(df) <= cap:
                rules[table] = {'qis': qis, 'k': threshold, 'subject': _subject_col(plan, table)}
        if rules:
            candidate = evaluate(levels, 'local_suppression', rules)
            if candidate is not None and not failures(candidate) and risk_score(candidate) < risk_score(current):
                candidate['accepted'] = True
                current, suppression = candidate, rules
    if len(trace) >= budget and not suppression:
        feasible = [entry for entry in trace if entry['phase'] != 'utility_baseline' and not failures(entry)]
        if feasible:
            best = min(feasible, key=lambda entry: (not met(entry), risk_score(entry), entry['information_loss']))
            if (not met(best), risk_score(best), best['information_loss']) < (
                    not met(current), risk_score(current), current['information_loss']):
                current, levels = best, best['levels']
                current['accepted'] = True
    # Without a t target it cannot affect selection; measure it once for the chosen candidate.
    current['risk'] = ev.risk(ev.build(levels, suppression), measure_t=True)
    out = deepcopy(plan)
    out.pop('conflict', None)
    for c in out['columns'] + out.get('derived', []):
        if _ref(c) in levels:
            rung = c['rungs'][levels[_ref(c)]]
            c.update(level=levels[_ref(c)], params=dict(rung['params']), method=rung['method'])
            if 'sources' not in c:
                c['action'] = rung['action']
            c['selection_explanation'] = (
                f"Chosen rung {levels[_ref(c)]}: {rung['method'] or rung['action']} {rung['params']}; "
                f"required by {', '.join(c.get('required_by', [])) or 'policy'}; "
                f"measured candidate {current['evaluation']}")
            c['rejected_rungs'] = [
                {'level': entry['levels'][_ref(c)], 'reason': entry['reason']}
                for entry in trace if entry.get('changed_column') == _ref(c) and entry.get('reason')]
    out['suppression'] = suppression
    out['status'] = 'measured_ok' if met(current) else 'budget_exhausted' if unexplored else 'target_unmet'
    out['measured'] = {'risk': current['risk'], 'utility': current['utility'], 'baseline_utility': base,
                       'tau': tau, 'evaluations': len(trace), 'information_loss': current['information_loss'],
                       'baseline_definition': 'minimised source precision; shared pseudonyms and exact derived age',
                       'method': 'pets_eval.privacy; distinct subject/class; distinct subject/class/value for l/t',
                       'chosen_evaluation': current['evaluation'],
                       't_measurement': 'every candidate when t is a target; otherwise chosen plan only',
                       'requirement_floors': floors,
                       'text_redaction': 'detect_spans' if spans else 'rules_only'}
    out['search_trace'] = trace
    out['outcome'] = _outcome(out, current, failures(current), tau, base, budget, len(trace), unexplored)
    if 'provenance_unbound' in out['outcome']['issues']:
        out['warnings'] = out.get('warnings', []) + [
            'provenance_unbound: plan is not bound to a detect manifest; measured results cannot approve a release']
    if out['status'] != 'measured_ok':
        violations = risk_violations(current['risk'], targets)
        violations += [f"{task}: unanswerable or below tau={tau} of source-precision utility"
                       for task in failures(current)]
        out['conflict'] = {'remaining_risk': {t: r['share_below_k'] for t, r in current['risk'].items()},
                           'violations': violations,
                           'limited_by': limits, 'unanswerable_tasks': failures(current),
                           'unknown_subjects': {t: r['unknown_subject_rows'] for t, r in current['risk'].items()
                                                if r['unknown_subject_rows']},
                           'reason': (f'evaluation budget exhausted with {unexplored} unexplored candidates; '
                                      'not a proof of infeasibility' if unexplored else
                                      'no allowed step meets k/l/t targets while preserving required utility'),
                           'targets': dict(targets)}
    return out
