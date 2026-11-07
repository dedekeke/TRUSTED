import subprocess
import sys
from pathlib import Path


def test_flat_selection_cli_and_standard_library_select():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-m', 'server.select', '--help'], cwd=root,
                            capture_output=True, text=True, check=True)
    assert 'python -m server.select' in result.stdout
    subprocess.run([sys.executable, '-c',
                    'import server.select; import select; assert callable(select.select)'],
                   cwd=root, capture_output=True, text=True, check=True)
