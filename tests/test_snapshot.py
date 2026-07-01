from exchange_monitor import snapshot


def test_load_missing_returns_none(tmp_path):
    assert snapshot.load_snapshot(tmp_path / "nope.json") is None


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "snap.json"
    snapshot.save_snapshot(p, {"a": 1, "中文": "值"})
    assert snapshot.load_snapshot(p) == {"a": 1, "中文": "值"}


def test_unified_diff_detects_change():
    d = snapshot.unified_diff("line1\nline2\n", "line1\nCHANGED\n", "doc")
    assert "CHANGED" in d
    assert d.startswith("---") or "@@" in d


def test_unified_diff_empty_when_same():
    assert snapshot.unified_diff("same\n", "same\n", "doc") == ""
