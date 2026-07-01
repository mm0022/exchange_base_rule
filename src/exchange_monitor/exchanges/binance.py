"""Binance 数据源解析 + 适配器。中文靠请求头 lang: zh-CN。"""
import sys
import time

from exchange_monitor.config import (
    BINANCE_ANN_DEL_CATALOG,
    BINANCE_ANN_NEW_CATALOG,
    BINANCE_BASE,
    BINANCE_BODY_DIFF_LEAVES,
    BINANCE_CMS_DETAIL,
    BINANCE_CMS_LIST,
    BINANCE_FAQ_BRANCH,
    BINANCE_FAQ_ROOT_CATALOG,
    BINANCE_LANG,
)
from exchange_monitor.models import Announcement, DocMeta


def _catalogs(api_json: dict) -> list:
    data = api_json.get("data") or {}
    return data.get("catalogs") or []


def parse_announcements(api_json: dict, ann_type: str) -> list[Announcement]:
    cats = _catalogs(api_json)
    if not cats:
        return []
    arts = cats[0].get("articles") or []
    out: list[Announcement] = []
    for a in arts:
        out.append(
            Announcement(
                title=a["title"].strip(),
                url=f"{BINANCE_BASE}/zh-CN/support/announcement/{a['code']}",
                ptime=int(a["releaseDate"]) // 1000,
                ann_type=ann_type,
            )
        )
    return out


def announcements_total(api_json: dict) -> int:
    cats = _catalogs(api_json)
    if not cats:
        return 0
    return int(cats[0].get("total") or 0)


def collect_leaves(tree_json: dict) -> list[dict]:
    """返回全部叶节点（无 subcatalogs 的 catalog dict）。支持传入完整 tree JSON 或单个节点。"""
    leaves: list[dict] = []

    def walk(node: dict) -> None:
        subs = node.get("catalogs") or []
        if not subs:
            leaves.append(node)
            return
        for s in subs:
            walk(s)

    # 支持传入完整 API 响应或单个节点
    if "data" in tree_json or ("catalogId" not in tree_json and "catalogs" not in tree_json):
        for c in _catalogs(tree_json):
            walk(c)
    else:
        walk(tree_json)
    return leaves


def parse_detail(api_json: dict) -> tuple[str, int, str]:
    data = api_json.get("data")
    if not data or "body" not in data:
        raise ValueError("Binance detail: 缺少 data.body，接口可能已变更")
    body = data["body"]
    upd = int(data.get("lastUpdateTime") or data.get("publishDate") or 0) // 1000
    title = (data.get("title") or "").strip()
    return body, upd, title


def _find_branch(tree_json: dict, branch_id: int) -> dict | None:
    """在整棵树中找到 catalogId==branch_id 的节点。"""
    def walk(o: dict) -> dict | None:
        if o.get("catalogId") == branch_id:
            return o
        for s in (o.get("catalogs") or []):
            r = walk(s)
            if r:
                return r
        return None

    for c in (_catalogs(tree_json)):
        r = walk(c)
        if r:
            return r
    return None


_PAGE_SIZE = 20
_MAX_PAGES = 50  # 分页安全上限（最大叶 total/20 远小于此）


class BinanceAdapter:
    name = "Binance"
    snapshot_name = "binance"

    def __init__(self):
        self._body_cache: dict[str, str] = {}

    def fetch_docs(self, fetcher, config) -> list[DocMeta]:
        branch_leaf_ids: set[int] | None = None
        leaf_total: dict[int, int] = {}
        by_code: dict[str, tuple[dict, int]] = {}  # code -> (article_dict, leaf_catalog_id)
        page = 1
        while True:
            tree = fetcher.get_json(
                BINANCE_CMS_LIST,
                {"type": 2, "catalogId": BINANCE_FAQ_ROOT_CATALOG, "pageNo": page, "pageSize": _PAGE_SIZE},
                headers=BINANCE_LANG,
            )
            if page == 1:
                branch = _find_branch(tree, BINANCE_FAQ_BRANCH)
                if branch is None:
                    raise ValueError(f"Binance: 未找到合约交易分支({BINANCE_FAQ_BRANCH})")
                branch_leaves = collect_leaves(branch)
                branch_leaf_ids = {lf.get("catalogId") for lf in branch_leaves}
                leaf_total = {lf.get("catalogId"): int(lf.get("total") or 0) for lf in branch_leaves}
            # 从整棵树取所有叶，只保留属于分支 18 的叶
            page_count = 0
            for lf in collect_leaves(tree):
                lid = lf.get("catalogId")
                if lid not in branch_leaf_ids:
                    continue
                for a in (lf.get("articles") or []):
                    by_code[a["code"]] = (a, lid)
                    page_count += 1
            if page_count == 0:
                break
            page += 1
            if page > _MAX_PAGES:
                raise ValueError(f"Binance 文档分页超过 {_MAX_PAGES} 页，疑似异常")
        expected = sum(leaf_total.values())
        if expected and len(by_code) < expected:
            raise ValueError(f"Binance 合约交易文档截断: 取到 {len(by_code)}/{expected}")
        # 构造 docs：全部抓 detail 拿 lastUpdateTime；仅 BINANCE_BODY_DIFF_LEAVES 保留正文
        self._body_cache = {}
        docs: list[DocMeta] = []
        skipped: list[str] = []
        total = len(by_code)
        for code, (a, lid) in by_code.items():
            pub = int(a.get("releaseDate") or 0) // 1000
            if config.binance_detail_delay:
                time.sleep(config.binance_detail_delay)
            try:
                det = fetcher.get_json(BINANCE_CMS_DETAIL, {"articleCode": code}, headers=BINANCE_LANG)
                body, upd, title = parse_detail(det)
            except Exception:  # noqa: BLE001 — 单篇失败(限频等)跳过，不整体失败
                skipped.append(code)
                continue
            # 仅指定两叶保留正文做 diff；其余叶只用 lastUpdateTime，正文留空
            stored_body = body if lid in BINANCE_BODY_DIFF_LEAVES else ""
            self._body_cache[code] = stored_body
            docs.append(
                DocMeta(
                    slug=code,
                    title=title or a.get("title", "").strip(),
                    url=f"{BINANCE_BASE}/zh-CN/support/faq/{code}",
                    update_time=upd,
                    publish_time=pub,
                )
            )
        if skipped:
            print(f"[Binance] 跳过 {len(skipped)}/{total} 篇(限频): {skipped[:5]}...", file=sys.stderr)
        return docs

    def fetch_doc_body(self, fetcher, config, doc: DocMeta) -> str:
        if doc.slug in self._body_cache:
            return self._body_cache[doc.slug]
        det = fetcher.get_json(
            BINANCE_CMS_DETAIL, {"articleCode": doc.slug}, headers=BINANCE_LANG
        )
        return parse_detail(det)[0]

    def _collect_ann(self, fetcher, config, now_ts, catalog, ann_type):
        cutoff = now_ts - config.window_days * 86400
        out: list[Announcement] = []
        page = 1
        while True:
            data = fetcher.get_json(
                BINANCE_CMS_LIST,
                {"type": 1, "catalogId": catalog, "pageNo": page, "pageSize": _PAGE_SIZE},
                headers=BINANCE_LANG,
            )
            anns = parse_announcements(data, ann_type)
            if not anns:
                break
            out.extend([a for a in anns if a.ptime >= cutoff])
            if anns[-1].ptime < cutoff or page * _PAGE_SIZE >= announcements_total(data):
                break
            page += 1
            if page > _MAX_PAGES:
                raise ValueError(f"Binance 公告分页超过 {_MAX_PAGES} 页，疑似异常: catalog={catalog}")
        return out

    def fetch_announcements(
        self, fetcher, config, now_ts: int
    ) -> tuple[list[Announcement], list[Announcement]]:
        new = self._collect_ann(
            fetcher, config, now_ts, BINANCE_ANN_NEW_CATALOG, "binance-new-listings"
        )
        delist = self._collect_ann(
            fetcher, config, now_ts, BINANCE_ANN_DEL_CATALOG, "binance-delistings"
        )
        return new, delist

    def fetch_fees(self, fetcher, config) -> str | None:
        return None
