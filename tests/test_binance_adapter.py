import json
import pathlib

from exchange_monitor.config import Config
from exchange_monitor.exchanges.binance import BinanceAdapter, _find_branch, collect_leaves

FIX = pathlib.Path(__file__).parent / "fixtures"


def _j(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeFetcher:
    """按 (type, pageNo) 路由 fixture；detail 对任意 code 返回同一详情。"""

    def __init__(self, fail_codes: set | None = None):
        self.calls = 0
        self.fail_codes = fail_codes or set()

    def get_json(self, url, params=None, headers=None):
        self.calls += 1
        if "article/detail/query" in url:
            code = (params or {}).get("articleCode", "")
            if code in self.fail_codes:
                raise RuntimeError(f"fake 429: {code}")
            return _j("binance_detail.json")
        if "article/list/query" in url:
            t, page = params["type"], params.get("pageNo", 1)
            if t == 1:
                if page == 1:
                    return _j("binance_ann_new.json" if params["catalogId"] == 48 else "binance_ann_del.json")
                return {"code": "000000", "data": {"catalogs": []}}
            # type == 2 文档
            if page == 1:
                return _j("binance_faq_tree.json")
            if page == 2:
                return _j("binance_faq_tree_p2.json")
            return {"code": "000000", "data": {"catalogs": []}}
        raise AssertionError(url)

    def get_text(self, url, params=None, headers=None):
        raise AssertionError("Binance 不用 get_text")


def _branch18_leaf_total() -> int:
    """从 fixture 动态计算 branch-18 叶的 total 之和（不硬编码）。"""
    tree = _j("binance_faq_tree.json")
    branch = _find_branch(tree, 18)
    assert branch is not None, "fixture 中找不到 branch 18"
    return sum(int(lf.get("total") or 0) for lf in collect_leaves(branch))


def _build_code_to_leaf(tree) -> dict[str, int]:
    """从 tree fixture 建立 article code -> leaf catalogId 的映射（用于校验正文归属）。"""
    branch = _find_branch(tree, 18)
    assert branch is not None
    branch_leaf_ids = {lf.get("catalogId") for lf in collect_leaves(branch)}
    mapping: dict[str, int] = {}
    # 从 p1 和 p2 两页收集
    for name in ("binance_faq_tree.json", "binance_faq_tree_p2.json"):
        t = _j(name)
        for lf in collect_leaves(t):
            lid = lf.get("catalogId")
            if lid not in branch_leaf_ids:
                continue
            for a in (lf.get("articles") or []):
                mapping[a["code"]] = lid
    return mapping


def test_identity():
    a = BinanceAdapter()
    assert a.name == "Binance" and a.snapshot_name == "binance"


def test_fetch_fees_none():
    assert BinanceAdapter().fetch_fees(FakeFetcher(), Config()) is None


def test_fetch_docs_only_contract_branch():
    """只抓 branch-18（合约交易）的文章；count == 从 fixture 动态算出的 145。"""
    docs = BinanceAdapter().fetch_docs(FakeFetcher(), Config(binance_detail_delay=0))
    expected = _branch18_leaf_total()
    assert len(docs) == expected  # 从 fixture 算出，不硬编码（当前 = 145）
    # URL 全是绝对路径
    assert all(d.url.startswith("https://www.binance.com/") for d in docs)
    # 分支外的叶（期权 43、事件合约 305）不出现
    tree = _j("binance_faq_tree.json")
    branch = _find_branch(tree, 18)
    branch_leaf_ids = {lf.get("catalogId") for lf in collect_leaves(branch)}
    code_to_leaf = _build_code_to_leaf(tree)
    slugs = {d.slug for d in docs}
    for code, lid in code_to_leaf.items():
        assert code in slugs, f"branch-18 文章 {code}(leaf {lid}) 未出现在结果里"
    # 验证没有来自分支外的 slug（反向：fixture 里所有分支外 article code 不应出现）
    for lf in collect_leaves(tree):
        if lf.get("catalogId") not in branch_leaf_ids:
            for a in (lf.get("articles") or []):
                assert a["code"] not in slugs, f"分支外文章 {a['code']} 不应出现在结果里"


def test_all_docs_have_text_body_and_update_time():
    """
    所有文档都存有纯文本正文（供逐字 diff），且 update_time 来自 detail 的 lastUpdateTime。
    正文为提取后的纯文本（非 JSON 树）。
    """
    a = BinanceAdapter()
    fetcher = FakeFetcher()
    docs = a.fetch_docs(fetcher, Config(binance_detail_delay=0))

    detail_upd = int(_j("binance_detail.json")["data"]["lastUpdateTime"]) // 1000

    for d in docs:
        assert d.update_time == detail_upd, f"{d.slug}: update_time 不等于 detail.lastUpdateTime"
        body = a.fetch_doc_body(fetcher, Config(binance_detail_delay=0), d)
        assert body, f"文章 {d.slug} 应有正文（全部文档均存正文），实际为空"
        assert not body.lstrip().startswith("{"), f"{d.slug}: 正文应是纯文本，不应是 JSON 树"


def test_skips_on_detail_failure():
    """单篇 detail 抓取失败时跳过，不整体失败；返回总数 = 145 - 失败数。"""
    tree = _j("binance_faq_tree.json")
    code_to_leaf = _build_code_to_leaf(tree)
    all_codes = list(code_to_leaf.keys())
    # 取前 3 个 code 作为失败目标
    fail_codes = set(all_codes[:3])

    a = BinanceAdapter()
    fetcher = FakeFetcher(fail_codes=fail_codes)
    docs = a.fetch_docs(fetcher, Config(binance_detail_delay=0))

    expected = _branch18_leaf_total() - len(fail_codes)
    assert len(docs) == expected
    returned_slugs = {d.slug for d in docs}
    for code in fail_codes:
        assert code not in returned_slugs, f"失败的 code {code} 不应出现在结果里"


def test_fetch_doc_body_uses_cache():
    """fetch_doc_body 从缓存读（body-diff 叶非空，其余叶 ""），不发额外请求。"""
    a = BinanceAdapter()
    fetcher = FakeFetcher()
    docs = a.fetch_docs(fetcher, Config(binance_detail_delay=0))
    calls_after_fetch_docs = fetcher.calls

    # 任意文档都有缓存正文（全部文档均存正文）
    body = a.fetch_doc_body(fetcher, Config(binance_detail_delay=0), docs[0])
    assert isinstance(body, str) and len(body) > 50
    assert fetcher.calls == calls_after_fetch_docs  # 命中缓存，未发额外请求


def test_fetch_announcements_window_and_split():
    a = BinanceAdapter()
    new, delist = a.fetch_announcements(FakeFetcher(), Config(binance_detail_delay=0), now_ts=99_999_999_999)
    # now_ts 极大 → cutoff 极大 → 窗口内为空
    assert new == [] and delist == []
    # now_ts 极小 → cutoff 极小 → 全部纳入
    a2 = BinanceAdapter()
    new2, del2 = a2.fetch_announcements(FakeFetcher(), Config(binance_detail_delay=0), now_ts=0)
    assert len(new2) > 0
    assert all(x.ann_type == "binance-new-listings" for x in new2)
    assert all(x.ann_type == "binance-delistings" for x in del2)
