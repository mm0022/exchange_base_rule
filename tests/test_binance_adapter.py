import json
import pathlib

from exchange_monitor.config import Config
from exchange_monitor.exchanges.binance import BinanceAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"


def _j(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeFetcher:
    """按 (type, catalogId, pageNo) 返回 fixture；detail 对任意 code 返回同一详情。"""

    def get_json(self, url, params=None, headers=None):
        if "article/detail/query" in url:
            return _j("binance_detail.json")
        if "article/list/query" in url:
            t, page = params["type"], params.get("pageNo", 1)
            if t == 1:
                return _j("binance_ann_new.json" if params["catalogId"] == 48 else "binance_ann_del.json")
            # type == 2 文档：全树全局分页
            if page == 1:
                return _j("binance_faq_tree.json")
            if page == 2:
                return _j("binance_faq_tree_p2.json")
            return {"code": "000000", "data": {"catalogs": []}}  # page>=3 无更多
        raise AssertionError(url)

    def get_text(self, url, params=None, headers=None):
        raise AssertionError("Binance 不用 get_text")


def test_identity():
    a = BinanceAdapter()
    assert a.name == "Binance" and a.snapshot_name == "binance"


def test_fetch_fees_none():
    assert BinanceAdapter().fetch_fees(FakeFetcher(), Config()) is None


def test_fetch_docs_enumerates_full_tree_with_update_time():
    docs = BinanceAdapter().fetch_docs(FakeFetcher(), Config())
    # 全树文章数 = 各叶 total 之和（fixture 数据）
    total_expected = sum((lf.get("total") or 0) for lf in __import__(
        "exchange_monitor.exchanges.binance", fromlist=["collect_leaves"]
    ).collect_leaves(_j("binance_faq_tree.json")))
    assert len(docs) == total_expected
    assert all(d.url.startswith("https://www.binance.com/") for d in docs)
    assert all(d.update_time > 1_700_000_000 for d in docs)  # 来自 detail 的 lastUpdateTime(秒)


def test_fetch_doc_body_uses_cache():
    a = BinanceAdapter()
    docs = a.fetch_docs(FakeFetcher(), Config())
    # fetch_docs 已缓存正文；fetch_doc_body 直接返回，不再请求
    body = a.fetch_doc_body(FakeFetcher(), Config(), docs[0])
    assert isinstance(body, str) and len(body) > 50


def test_fetch_announcements_window_and_split():
    a = BinanceAdapter()
    new, delist = a.fetch_announcements(FakeFetcher(), Config(), now_ts=99_999_999_999)
    # now_ts 极大 → cutoff 极大 → 窗口内为空（验证过滤生效，且不报错）
    assert new == [] and delist == []
    # now_ts 极小 → cutoff 极小 → 全部纳入
    a2 = BinanceAdapter()
    new2, del2 = a2.fetch_announcements(FakeFetcher(), Config(), now_ts=0)
    assert len(new2) > 0
    assert all(x.ann_type == "binance-new-listings" for x in new2)
