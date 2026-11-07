import pandas as pd
import pytest

from server.select.preview import apply_column


@pytest.mark.parametrize('method,expected', [('week_hour', '2025-12-22 23:00'),
                                           ('month_hour', '2025-12-01 23:00'),
                                           ('year_hour', '2025-01-01 23:00')])
def test_hour_preserving_preview_floors_and_counts_bad_dates(method, expected):
    source = pd.Series(['2025-12-28 23:59', 'bad date', ''])
    result, lost = apply_column(source, {'action': 'GENERALISE', 'method': method, 'params': {}}, b'test', 'test')
    assert result.tolist() == [expected, '', '']
    assert lost == 1


@pytest.mark.parametrize('plan', [{'suppression': {'t': {'k': 5}}},
                                 {'columns': [{'method': 'year_hour'}]}])
def test_legacy_export_cannot_ignore_preview_operations(plan, tmp_path, monkeypatch):
    import json
    from server.select.__main__ import main
    from server.select import transform
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    def no_export(*args, **kwargs):
        pytest.fail('unsupported preview plans must be rejected before export')
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', 'test-key')
    monkeypatch.setattr(transform, 'apply', no_export)
    out = tmp_path / 'export'
    with pytest.raises(SystemExit, match='complete the transform integration'):
        main(['transform', '--data', str(tmp_path), '--plan', str(plan_path), '--out', str(out)])
    assert not out.exists()
