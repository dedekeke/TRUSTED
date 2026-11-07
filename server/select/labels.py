"""Validate the Detect CSV handoff without loading its training catalog or copying free-text reasons."""
import numpy as np
import pandas as pd

from .detect import REVIEW_BELOW
from .select import ROLES


def from_detection(labels, tables, dataset):
    required = {'dataset', 'table', 'column', 'privacy_role', 'subtype', 'confidence'}
    if not required <= set(labels.columns):
        raise ValueError(f'detect labels need columns {sorted(required)}; use the explained labels export')
    labels = labels.loc[labels['dataset'].eq(dataset)].copy()
    if labels.empty:
        raise ValueError(f'detect labels contain no rows for dataset {dataset}')
    if labels.duplicated(['table', 'column']).any():
        raise ValueError('detect labels list a column twice')
    expected = {(table, column) for table, df in tables.items() for column in df.columns}
    actual = set(zip(labels['table'], labels['column']))
    if actual != expected:
        raise ValueError(f'detect labels do not match input columns; missing={sorted(expected-actual)}, '
                         f'unknown={sorted(actual-expected)}')
    if not labels['privacy_role'].isin(ROLES).all():
        raise ValueError('detect labels contain an unknown privacy role')
    if not labels['subtype'].astype(str).str.fullmatch(r'[A-Z][A-Z0-9_]{0,63}').all():
        raise ValueError('detect labels need taxonomy subtype names')
    confidence = pd.to_numeric(labels['confidence'], errors='coerce')
    if not (confidence.notna() & np.isfinite(confidence) & confidence.between(0, 1)).all():
        raise ValueError('detect confidence must be finite and between 0 and 1')

    def flag(name):
        if name not in labels:
            return pd.Series(False, index=labels.index)
        values = labels[name].astype(str).str.lower()
        if not values.isin(['true', 'false', '1', '0']).all():
            raise ValueError(f'detect {name} must be true or false')
        return values.isin(['true', '1'])

    review, art9, art9_table = flag('needs_review'), flag('art9'), flag('art9_table')
    if (art9 & ~labels['privacy_role'].isin(['sensitive_attribute', 'free_text'])).any():
        raise ValueError('Art. 9 labels must have a sensitive_attribute or free_text role')
    out = labels[['dataset', 'table', 'column', 'privacy_role', 'subtype']].copy()
    out['detector_confidence'] = confidence
    out['detector_needs_review'] = review
    out['art9'], out['art9_table'] = art9, art9_table
    out['confidence'] = confidence.where(~review, confidence.clip(upper=REVIEW_BELOW - .01))
    out['evidence'] = 'external detect artifact; free-text reasons excluded'
    out.loc[art9_table, 'evidence'] += '; person table (Art. 9 context)'
    return out.sort_values(['table', 'column']).reset_index(drop=True)
