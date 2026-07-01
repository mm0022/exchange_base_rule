from exchange_monitor.config import Config
from exchange_monitor.fetcher import Fetcher


def test_merge_headers_overrides_defaults():
    f = Fetcher(Config())
    merged = f._merge_headers({"lang": "zh-CN"})
    assert merged["lang"] == "zh-CN"
    assert merged["User-Agent"]  # 默认头仍在
    # 默认 Accept-Language 仍在（未被自定义头覆盖），且是当前期望的英文默认值
    assert merged["Accept-Language"] == "en-US,en"


def test_merge_headers_none_returns_defaults():
    f = Fetcher(Config())
    merged = f._merge_headers(None)
    assert "User-Agent" in merged and "Accept-Language" in merged
