import json
import pathlib

from exchange_monitor.config import Config
from exchange_monitor.exchanges.bybit import BybitAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeFetcher:
    def __init__(self):
        self.calls = 0

    def get_json(self, url, params=None, headers=None):
        self.calls += 1
        name = "bybit_ann_new.json" if params["type"] == "new_crypto" else "bybit_ann_del.json"
        return json.loads((FIX / name).read_text(encoding="utf-8"))

    def get_text(self, url, params=None, headers=None):
        self.calls += 1
        if "/topic-list/" in url:
            return (FIX / "bybit_topic.html").read_text(encoding="utf-8")
        if "/article/" in url:
            return (FIX / "bybit_article.html").read_text(encoding="utf-8")
        raise AssertionError(url)


def test_identity():
    a = BybitAdapter()
    assert a.name == "Bybit" and a.snapshot_name == "bybit"


def test_fetch_fees_none():
    assert BybitAdapter().fetch_fees(FakeFetcher(), Config()) is None


def test_fetch_docs_enumerates_topic_with_body_and_time():
    import exchange_monitor.exchanges.bybit as by
    data = by.extract_next_data((FIX / "bybit_topic.html").read_text(encoding="utf-8"))["props"]["pageProps"]["data"]
    expected = len(by.collect_articles(data))
    docs = BybitAdapter().fetch_docs(FakeFetcher(), Config())
    assert len(docs) == expected
    assert all(d.url.startswith("https://www.bybit.com/") for d in docs)
    assert all(d.update_time > 1_700_000_000 for d in docs)


def test_fetch_doc_body_cached():
    a = BybitAdapter()
    f = FakeFetcher()
    docs = a.fetch_docs(f, Config())
    n = f.calls
    body = a.fetch_doc_body(f, Config(), docs[0])
    assert isinstance(body, str) and len(body) > 200
    assert f.calls == n  # 命中缓存


def test_fetch_announcements_window_split():
    a = BybitAdapter()
    new, delist = a.fetch_announcements(FakeFetcher(), Config(), now_ts=0)
    assert new and all(x.ann_type == "bybit-new-listings" for x in new)
    assert delist and all(x.ann_type == "bybit-delistings" for x in delist)
