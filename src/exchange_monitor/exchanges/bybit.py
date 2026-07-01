"""Bybit 数据源解析 + 适配器。公告用 V5 API；文档为 Next.js SSR(__NEXT_DATA__)。中文靠 zh-MY 路径。"""
import json
import re
from datetime import UTC, datetime

from exchange_monitor.models import Announcement, DocMeta

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def parse_announcements(api_json: dict, ann_type: str) -> list[Announcement]:
    lst = (api_json.get("result") or {}).get("list") or []
    out: list[Announcement] = []
    for a in lst:
        pt = a.get("publishTime") or a.get("dateTimestamp")
        if not pt:
            continue
        out.append(
            Announcement(
                title=a["title"].strip(),
                url=a["url"],
                ptime=int(pt) // 1000,
                ann_type=ann_type,
            )
        )
    return out


def announcements_total(api_json: dict) -> int:
    return int((api_json.get("result") or {}).get("total") or 0)


def extract_next_data(html: str) -> dict:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("Bybit: 未找到 __NEXT_DATA__，页面结构可能已变更")
    return json.loads(m.group(1))


def collect_articles(topic_data: dict) -> list[dict]:
    """递归 topic 树，收集全部文章 dict（含 url/title/code）。"""
    out: list[dict] = []

    def walk(node: dict) -> None:
        for a in (node.get("articles") or []):
            out.append(a)
        for ch in (node.get("children") or []):
            walk(ch)

    walk(topic_data)
    return out


def parse_last_updated(s: str) -> int:
    dt = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return int(dt.timestamp())


def parse_article(article_html: str) -> tuple[str, int, str]:
    art = extract_next_data(article_html).get("props", {}).get("pageProps", {}).get("article")
    if not art:
        raise ValueError("Bybit article: article 为空（可能该语言无内容，需 zh-MY/zh-TW）")
    tabs = art.get("tabs") or []
    if not tabs:
        raise ValueError("Bybit article: 无 tabs")
    tab = tabs[0]
    body = tab.get("tab_content") or ""
    upd = parse_last_updated(tab["last_updated"]) if tab.get("last_updated") else 0
    title = (art.get("title") or "").strip()
    return body, upd, title


# 供 Task 3 适配器使用
_ = DocMeta
