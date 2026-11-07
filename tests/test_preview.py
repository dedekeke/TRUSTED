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


def test_legacy_export_command_delegates_to_the_gated_executor(tmp_path, monkeypatch):
    """The old `server.select transform` no longer has its own export path: unmeasured plans are refused."""
    import json
    from server.select.__main__ import main
    data = tmp_path / 'demo'
    data.mkdir()
    pd.DataFrame({'id': ['1']}).to_csv(data / 't.csv', index=False)
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps({'status': 'ready_for_transform', 'tables': {}, 'columns': [],
                                     'suppression': {'t': {'k': 5}}}))
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', 'test-key')
    out = tmp_path / 'export'
    assert main(['transform', '--data', str(data), '--plan', str(plan_path), '--out', str(out), '--no-scorecard']) == 2
    assert not (out / 'protected').exists() and (out / 'diagnostics.json').exists()
