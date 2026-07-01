import json
import pathlib

from exchange_monitor.config import Config
from exchange_monitor.exchanges.bybit import BybitAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeFetcher:
    def __init__(self, fail_urls: set | None = None):
        self.calls = 0
        self.fail_urls = fail_urls or set()

    def get_json(self, url, params=None, headers=None):
        self.calls += 1
        name = "bybit_ann_new.json" if params["type"] == "new_crypto" else "bybit_ann_del.json"
        return json.loads((FIX / name).read_text(encoding="utf-8"))

    def get_text(self, url, params=None, headers=None):
        self.calls += 1
        if "/topic-list/" in url:
            return (FIX / "bybit_topic.html").read_text(encoding="utf-8")
        if "/article/" in url:
            # 从 URL 中提取 article slug（最后一段路径）
            slug = url.rstrip("/").split("/")[-1]
            if slug in self.fail_urls:
                raise RuntimeError(f"fake 308: {slug}")
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


def test_fetch_docs_skips_failed_article():
    """单篇 article 抓取失败时跳过，不整体失败；返回总数 = 总数 - 1。"""
    import exchange_monitor.exchanges.bybit as by
    data = by.extract_next_data((FIX / "bybit_topic.html").read_text(encoding="utf-8"))["props"]["pageProps"]["data"]
    all_articles = by.collect_articles(data)
    total = len(all_articles)
    assert total > 1, "fixture 必须有多于 1 篇文章才能测试跳过逻辑"

    # 让第一篇 article 的抓取失败
    fail_slug = all_articles[0]["url"]
    a = BybitAdapter()
    docs = a.fetch_docs(FakeFetcher(fail_urls={fail_slug}), Config())

    assert len(docs) == total - 1, f"应跳过 1 篇，返回 {total - 1} 篇，实际 {len(docs)}"
    returned_slugs = {d.slug for d in docs}
    assert fail_slug not in returned_slugs, f"失败的 slug {fail_slug} 不应出现在结果里"
