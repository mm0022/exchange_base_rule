import logging

from exchange_monitor import parse
from exchange_monitor.config import (
    ANNOUNCEMENTS,
    ARTICLE_URL,
    BASE,
    FEES_URL,
    SEARCH_ARTICLES,
    SECTION,
)
from exchange_monitor.models import Announcement, DocMeta

log = logging.getLogger(__name__)

_ANN_TYPES = ["announcements-new-listings", "announcements-delistings"]
# OKX 偶发返回不含 feeDataInfo 的精简版费率页（服务端非确定性，同机连抓都会 True/True/False
# 抖动）。抓到精简版就重抓换个服务端变体，直到拿到内联费率数据的完整版。
_FEES_RETRIES = 6


class OkxAdapter:
    name = "OKX"
    snapshot_name = "okx"

    def fetch_docs(self, fetcher, config) -> list[DocMeta]:
        docs: list[DocMeta] = []
        seen: set[str] = set()
        for slug in config.section_slugs:
            sec = fetcher.get_json(SECTION, {"slug": slug})
            sid = parse.resolve_section_id(sec, slug)
            data = fetcher.get_json(SEARCH_ARTICLES, {"sectionIds": sid, "page": 1, "size": 100})
            section_docs = parse.parse_doc_list(data)
            total = (data.get("data") or {}).get("total")
            if total is not None and int(total) > len(section_docs):
                raise ValueError(f"OKX section {slug} 截断: {len(section_docs)}/{total}")
            for d in section_docs:
                if d.slug in seen:
                    continue
                seen.add(d.slug)
                if d.url.startswith("/"):
                    d.url = f"{BASE}{d.url}"
                docs.append(d)
        return docs

    def fetch_doc_body(self, fetcher, config, doc: DocMeta) -> str:
        html = fetcher.get_text(f"{ARTICLE_URL}/{doc.slug}")
        return parse.extract_article_body(html)

    def fetch_announcements(
        self, fetcher, config, now_ts: int
    ) -> tuple[list[Announcement], list[Announcement]]:
        cutoff = now_ts - config.window_days * 86400
        out: dict[str, list[Announcement]] = {t: [] for t in _ANN_TYPES}
        for ann_type in _ANN_TYPES:
            page = 1
            while True:
                data = fetcher.get_json(ANNOUNCEMENTS, {"annType": ann_type, "page": page})
                anns = parse.parse_announcements(data, ann_type)
                if not anns:
                    break
                out[ann_type].extend([a for a in anns if a.ptime >= cutoff])
                if anns[-1].ptime < cutoff or page >= parse.announcements_total_pages(data):
                    break
                page += 1
        return out["announcements-new-listings"], out["announcements-delistings"]

    def fetch_fees(self, fetcher, config) -> str | None:
        last: ValueError | None = None
        for attempt in range(_FEES_RETRIES):
            try:
                return parse.extract_fees_text(fetcher.get_text(FEES_URL))
            except ValueError as e:  # 精简版页面缺 feeDataInfo；重抓换个服务端变体
                last = e
                log.warning(
                    "[OKX] 费率页无 feeDataInfo（精简版，第 %d/%d 次），重试",
                    attempt + 1, _FEES_RETRIES,
                )
        raise last
