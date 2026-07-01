import httpx
import pytest
from exchange_monitor.config import Config
from exchange_monitor.fetcher import Fetcher


class _Resp:
    def __init__(self, status):
        self.status_code = status
        self.request = httpx.Request("GET", "https://x/y")
        self._json = {"ok": True}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=self.request, response=self)

    def json(self):
        return self._json

    @property
    def text(self):
        return "ok"


class _Client:
    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.calls = 0

    def get(self, url, params=None, headers=None):
        self.calls += 1
        return _Resp(self._statuses.pop(0))

    def close(self):
        pass


def test_429_then_success_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    f = Fetcher(Config(retries=3, rate_limit_backoff=0))
    f._client = _Client([429, 200])
    data = f.get_json("https://x/y")
    assert data == {"ok": True}
    assert f._client.calls == 2  # 第1次429退避重试，第2次成功


def test_429_exhausted_raises(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    f = Fetcher(Config(retries=2, rate_limit_backoff=0))
    f._client = _Client([429, 429])
    with pytest.raises(RuntimeError):
        f.get_json("https://x/y")
