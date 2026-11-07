"""In-memory selection previews; file export remains the separate transform step."""
import numpy as np
import pandas as pd

from .transform import _blank, apply_column as _apply_column, check_plan, derive_age_band
from .detect import normalise_hetu, safe_datetime


def apply_column(s, decision, key, release_id, df=None, columns=None):
    method = decision.get('method')
    if decision['action'] != 'GENERALISE' or method not in ('week_hour', 'month_hour', 'year_hour'):
        return _apply_column(s, decision, key, release_id, df, columns)
    dt = safe_datetime(s.where(~_blank(s))).dt.floor('h')
    if method == 'week_hour':
        dt = dt - pd.to_timedelta(dt.dt.day_of_week, unit='D')
    elif method == 'month_hour':
        dt = dt - pd.to_timedelta(dt.dt.day - 1, unit='D')
    fmt = '%Y-01-01 %H:00' if method == 'year_hour' else '%Y-%m-%d %H:00'
    out = dt.dt.strftime(fmt).where(dt.notna(), '')
    return out, int((~_blank(s) & dt.isna()).sum())


def small_classes(protected, qis, subjects, k):
    if not qis:
        return pd.Series(False, index=protected.index)
    keys = pd.util.hash_pandas_object(protected[qis].astype(str), index=False)
    people = pd.Series(subjects.values, index=protected.index).groupby(keys.values).transform('nunique')
    return people < k


def resolved_subjects(tables, plan, table):
    """Resolve subjects through unique-parent joins without inventing IDs for missing people."""
    target = (plan.get('subject_keys') or {}).get(table)

    def walk(name, seen):
        df = tables[name]
        if target and target.split('.', 1)[0] == name:
            column = target.split('.', 1)[1]
            if column in df:
                subtype = next((c.get('subtype') for c in plan.get('columns', [])
                                if c['table'] == name and c['column'] == column), '')
                normalise = normalise_hetu if subtype == 'NATIONAL_ID' else (lambda value: value.strip())
                return df[column].astype(str).map(normalise).where(~_blank(df[column]))
        for join in plan.get('joins', []):
            child, cc = join['child'].split('.', 1)
            parent, pc = join['parent'].split('.', 1)
            if child != name or parent in seen or parent not in tables or cc not in df or pc not in tables[parent]:
                continue
            values = walk(parent, seen | {parent})
            keys = tables[parent][pc]
            good = ~_blank(keys) & ~keys.duplicated(keep=False)
            mapped = df[cc].map(pd.Series(values[good].values, index=keys[good]))
            if mapped.notna().any():
                return mapped
        return pd.Series(np.nan, index=df.index)

    return walk(table, {table})
