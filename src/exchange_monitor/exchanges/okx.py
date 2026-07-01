from exchange_monitor import parse
from exchange_monitor.config import (
    ANNOUNCEMENTS,
    ARTICLE_URL,
    BASE,
    CATEGORY,
    FEES_URL,
    SEARCH_ARTICLES,
)
from exchange_monitor.models import Announcement, DocMeta

_ANN_TYPES = ["announcements-new-listings", "announcements-delistings"]


class OkxAdapter:
    name = "OKX"
    snapshot_name = "okx"

    def fetch_docs(self, fetcher, config) -> list[DocMeta]:
        cat = fetcher.get_json(CATEGORY, {"slug": config.category_slug})
        sid = parse.resolve_section_id(cat, config.section_slug)
        data = fetcher.get_json(SEARCH_ARTICLES, {"sectionIds": sid, "page": 1, "size": 50})
        docs = parse.parse_doc_list(data)
        total = (data.get("data") or {}).get("total")
        if total is not None and int(total) > len(docs):
            raise ValueError(f"OKX doc list 截断: 共 {total} 篇但只取到 {len(docs)} 篇")
        for d in docs:
            if d.url.startswith("/"):
                d.url = f"{BASE}{d.url}"
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
        return parse.extract_fees_text(fetcher.get_text(FEES_URL))
