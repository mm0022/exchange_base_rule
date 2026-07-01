"""Binance 数据源解析 + 适配器。中文靠请求头 lang: zh-CN。"""
import time

from exchange_monitor.config import (
    BINANCE_ANN_DEL_CATALOG,
    BINANCE_ANN_NEW_CATALOG,
    BINANCE_BASE,
    BINANCE_CMS_DETAIL,
    BINANCE_CMS_LIST,
    BINANCE_FAQ_CATALOGS,
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
    """返回全部叶节点（无 subcatalogs 的 catalog dict）。"""
    leaves: list[dict] = []

    def walk(node: dict) -> None:
        subs = node.get("catalogs") or []
        if not subs:
            leaves.append(node)
            return
        for s in subs:
            walk(s)

    for c in _catalogs(tree_json):
        walk(c)
    return leaves


def parse_detail(api_json: dict) -> tuple[str, int, str]:
    data = api_json.get("data")
    if not data or "body" not in data:
        raise ValueError("Binance detail: 缺少 data.body，接口可能已变更")
    body = data["body"]
    upd = int(data.get("lastUpdateTime") or data.get("publishDate") or 0) // 1000
    title = (data.get("title") or "").strip()
    return body, upd, title


_PAGE_SIZE = 20
_MAX_PAGES = 50  # 分页安全上限（最大叶 total/20 远小于此）


class BinanceAdapter:
    name = "Binance"
    snapshot_name = "binance"

    def __init__(self):
        self._body_cache: dict[str, str] = {}

    def fetch_docs(self, fetcher, config) -> list[DocMeta]:
        # 1) 多 catalog 全树全局分页枚举文章（按 code 跨 catalog 累积，去重）
        by_code: dict[str, dict] = {}
        leaf_total: dict[int, int] = {}
        for catalog in BINANCE_FAQ_CATALOGS:
            page = 1
            while True:
                tree = fetcher.get_json(
                    BINANCE_CMS_LIST,
                    {"type": 2, "catalogId": catalog, "pageNo": page, "pageSize": _PAGE_SIZE},
                    headers=BINANCE_LANG,
                )
                leaves = collect_leaves(tree)
                page_count = 0
                for leaf in leaves:
                    if page == 1 and leaf.get("catalogId") is not None:
                        leaf_total[leaf["catalogId"]] = int(leaf.get("total") or 0)
                    for a in (leaf.get("articles") or []):
                        by_code[a["code"]] = a
                        page_count += 1
                if page_count == 0:
                    break
                page += 1
                if page > _MAX_PAGES:
                    raise ValueError(f"Binance catalog {catalog} 文档分页超过 {_MAX_PAGES} 页，疑似异常")
        expected = sum(leaf_total.values())
        if expected and len(by_code) < expected:
            raise ValueError(f"Binance 文档截断: 取到 {len(by_code)}/{expected}")
        # 2) 逐篇抓 detail（update_time + 正文），缓存正文；节流用 config.binance_detail_delay
        self._body_cache = {}
        docs: list[DocMeta] = []
        for code, a in by_code.items():
            if config.binance_detail_delay:
                time.sleep(config.binance_detail_delay)
            det = fetcher.get_json(BINANCE_CMS_DETAIL, {"articleCode": code}, headers=BINANCE_LANG)
            body, upd, title = parse_detail(det)
            self._body_cache[code] = body
            docs.append(
                DocMeta(
                    slug=code,
                    title=title or a.get("title", "").strip(),
                    url=f"{BINANCE_BASE}/zh-CN/support/faq/{code}",
                    update_time=upd,
                    publish_time=int(a.get("releaseDate") or 0) // 1000,
                )
            )
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
