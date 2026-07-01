import json
import pathlib

from exchange_monitor.config import Config
from exchange_monitor.exchanges.binance import BinanceAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"


def _j(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeFetcher:
    """按 (type, catalogId, pageNo) 返回 fixture；detail 对任意 code 返回同一详情。"""

    def __init__(self):
        self.calls = 0

    def get_json(self, url, params=None, headers=None):
        self.calls += 1
        if "article/detail/query" in url:
            return _j("binance_detail.json")
        if "article/list/query" in url:
            t, page = params["type"], params.get("pageNo", 1)
            if t == 1:
                # type == 1 公告：仅第 1 页返回 fixture，>1 页返回空
                if page == 1:
                    return _j("binance_ann_new.json" if params["catalogId"] == 48 else "binance_ann_del.json")
                return {"code": "000000", "data": {"catalogs": []}}
            # type == 2 文档：按 catalogId + pageNo 路由
            cat = params.get("catalogId")
            if cat == 4:
                if page == 1:
                    return _j("binance_faq_tree.json")
                if page == 2:
                    return _j("binance_faq_tree_p2.json")
                return {"code": "000000", "data": {"catalogs": []}}  # page>=3 无更多
            if cat == 3:
                if page == 1:
                    return _j("binance_faq_tree3.json")
                return {"code": "000000", "data": {"catalogs": []}}  # page>=2 无更多
            return {"code": "000000", "data": {"catalogs": []}}
        raise AssertionError(url)

    def get_text(self, url, params=None, headers=None):
        raise AssertionError("Binance 不用 get_text")


def _expected_total():
    import exchange_monitor.exchanges.binance as bn
    tot = 0
    for name in ("binance_faq_tree.json",):  # 只有 cat4（catalogId=4）
        for lf in bn.collect_leaves(_j(name)):
            tot += int(lf.get("total") or 0)
    return tot  # ≈ 163（cat4 各叶 total 之和）


def test_identity():
    a = BinanceAdapter()
    assert a.name == "Binance" and a.snapshot_name == "binance"


def test_fetch_fees_none():
    assert BinanceAdapter().fetch_fees(FakeFetcher(), Config()) is None


def test_fetch_docs_enumerates_full_tree_with_update_time():
    docs = BinanceAdapter().fetch_docs(FakeFetcher(), Config(binance_detail_delay=0))
    assert len(docs) == _expected_total()
    assert all(d.url.startswith("https://www.binance.com/") for d in docs)
    assert all(d.update_time > 1_700_000_000 for d in docs)


def test_fetch_doc_body_uses_cache():
    a = BinanceAdapter()
    fetcher = FakeFetcher()
    docs = a.fetch_docs(fetcher, Config(binance_detail_delay=0))
    calls_after_fetch_docs = fetcher.calls
    body = a.fetch_doc_body(fetcher, Config(binance_detail_delay=0), docs[0])
    assert isinstance(body, str) and len(body) > 50
    assert fetcher.calls == calls_after_fetch_docs  # 命中缓存，未发额外请求


def test_fetch_announcements_window_and_split():
    a = BinanceAdapter()
    new, delist = a.fetch_announcements(FakeFetcher(), Config(binance_detail_delay=0), now_ts=99_999_999_999)
    # now_ts 极大 → cutoff 极大 → 窗口内为空（验证过滤生效，且不报错）
    assert new == [] and delist == []
    # now_ts 极小 → cutoff 极小 → 全部纳入
    a2 = BinanceAdapter()
    new2, del2 = a2.fetch_announcements(FakeFetcher(), Config(binance_detail_delay=0), now_ts=0)
    assert len(new2) > 0
    assert all(x.ann_type == "binance-new-listings" for x in new2)
    assert all(x.ann_type == "binance-delistings" for x in del2)
