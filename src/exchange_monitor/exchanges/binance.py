"""Binance 数据源解析 + 适配器。中文靠请求头 lang: zh-CN。"""
from exchange_monitor.config import BINANCE_BASE
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


# DocMeta 供 Task 3 适配器构造使用（此处仅 import 供类型对齐）
_ = DocMeta
