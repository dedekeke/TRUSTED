import threading

import pytest

from server.guard import evaluation, guard


def test_evaluation_lifts_the_guard_only_on_its_own_thread(tmp_path):
    (tmp_path / "truth").mkdir()
    secret = tmp_path / "truth" / "x.csv"
    secret.write_text("a\n")
    guard(tmp_path)
    with pytest.raises(PermissionError):
        open(secret)
    other = []
    with evaluation():
        assert open(secret).read() == "a\n"
        t = threading.Thread(target=lambda: other.append(_refused(secret)))
        t.start()
        t.join()
    assert other == [True]
    with pytest.raises(PermissionError):
        open(secret)


def _refused(path):
    try:
        open(path)
    except PermissionError:
        return True
    return False
