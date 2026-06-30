from datetime import UTC, datetime

from okx_monitor import parse, snapshot
from okx_monitor.config import (
    ANNOUNCEMENTS,
    ARTICLE_URL,
    CATEGORY,
    FEES_URL,
    SEARCH_ARTICLES,
    Config,
)
from okx_monitor.models import Announcement, DocChange, DocMeta, RunResult

ANN_TYPES = ["announcements-new-listings", "announcements-delistings"]


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


def _fetch_docs(cfg: Config, fetcher) -> list[DocMeta]:
    cat = fetcher.get_json(CATEGORY, {"slug": cfg.category_slug})
    sid = parse.resolve_section_id(cat, cfg.section_slug)
    data = fetcher.get_json(SEARCH_ARTICLES, {"sectionIds": sid, "page": 1, "size": 50})
    parsed_docs = parse.parse_doc_list(data)
    total = (data.get("data") or {}).get("total")
    if total is not None and int(total) > len(parsed_docs):
        raise ValueError(
            f"doc list 截断: 共 {total} 篇但只取到 {len(parsed_docs)} 篇，需要分页"
        )
    return parsed_docs


def _fetch_body(cfg: Config, fetcher, slug: str) -> str:
    html = fetcher.get_text(f"{ARTICLE_URL}/{slug}")
    return parse.extract_article_body(html)


def _fetch_announcements(cfg: Config, fetcher, now_ts: int) -> dict[str, list[Announcement]]:
    cutoff = now_ts - cfg.window_days * 86400
    result: dict[str, list[Announcement]] = {t: [] for t in ANN_TYPES}
    for ann_type in ANN_TYPES:
        page = 1
        while True:
            data = fetcher.get_json(ANNOUNCEMENTS, {"annType": ann_type, "page": page})
            anns = parse.parse_announcements(data, ann_type)
            if not anns:
                break
            in_window = [a for a in anns if a.ptime >= cutoff]
            result[ann_type].extend(in_window)
            # 倒序：本页最旧一条已早于窗口 → 后续页更早，停止
            if anns[-1].ptime < cutoff or page >= parse.announcements_total_pages(data):
                break
            page += 1
    return result


def build_doc_changes(
    docs: list[DocMeta], bodies: dict[str, str], baseline_docs: dict
) -> list[DocChange]:
    changes: list[DocChange] = []
    seen = set()
    for d in docs:
        seen.add(d.slug)
        base = baseline_docs.get(d.slug)
        if base is None:
            changes.append(
                DocChange(d.slug, d.title, d.url, _date(d.update_time), "new", "")
            )
            continue
        if d.update_time != base["update_time"]:
            diff = snapshot.unified_diff(base.get("body", ""), bodies[d.slug], d.title)
            changes.append(
                DocChange(d.slug, d.title, d.url, _date(d.update_time), "updated", diff)
            )
    for slug, base in baseline_docs.items():
        if slug not in seen:
            changes.append(
                DocChange(slug, base["title"], "", "", "removed", "")
            )
    return changes


def run(config: Config, fetcher, now_ts: int) -> RunResult:
    snap_path = config.snapshot_dir / "okx.json"
    baseline = snapshot.load_snapshot(snap_path)
    is_baseline = baseline is None
    baseline = baseline or {"docs": {}, "fees_text": ""}

    # --- 文档 ---
    docs = _fetch_docs(config, fetcher)
    # 仅对"可能变化"的文档抓正文：首次全抓做基线；后续抓 update_time 变化或新文档
    bodies: dict[str, str] = {}
    for d in docs:
        base = baseline["docs"].get(d.slug)
        if is_baseline or base is None or d.update_time != base["update_time"]:
            bodies[d.slug] = _fetch_body(config, fetcher, d.slug)
        else:
            bodies[d.slug] = base.get("body", "")

    doc_changes = [] if is_baseline else build_doc_changes(docs, bodies, baseline["docs"])

    # --- 费率 ---
    fees_text = parse.extract_fees_text(fetcher.get_text(FEES_URL))
    fee_diff = "" if is_baseline else snapshot.unified_diff(
        baseline.get("fees_text", ""), fees_text, "费率"
    )
    fee_changed = bool(fee_diff)

    # --- 公告 ---
    anns = _fetch_announcements(config, fetcher, now_ts)

    # --- 落盘新快照 ---
    new_snap = {
        "docs": {
            d.slug: {"title": d.title, "update_time": d.update_time, "body": bodies[d.slug]}
            for d in docs
        },
        "fees_text": fees_text,
    }
    snapshot.save_snapshot(snap_path, new_snap)

    return RunResult(
        is_baseline=is_baseline,
        generated_at=datetime.fromtimestamp(now_ts, tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        doc_changes=doc_changes,
        doc_inventory=docs,
        fee_changed=fee_changed,
        fee_diff=fee_diff,
        anns_new=anns["announcements-new-listings"],
        anns_del=anns["announcements-delistings"],
    )
