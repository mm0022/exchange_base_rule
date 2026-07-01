from datetime import UTC, datetime

from exchange_monitor import snapshot
from exchange_monitor.config import Config
from exchange_monitor.models import DocChange, DocMeta, ExchangeResult, RunResult


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


def build_doc_changes(
    docs: list[DocMeta], bodies: dict[str, str], baseline_docs: dict
) -> list[DocChange]:
    changes: list[DocChange] = []
    seen = set()
    for d in docs:
        seen.add(d.slug)
        base = baseline_docs.get(d.slug)
        if base is None:
            changes.append(DocChange(d.slug, d.title, d.url, _date(d.update_time), "new", ""))
            continue
        if d.update_time != base["update_time"]:
            diff = snapshot.unified_diff(base.get("body", ""), bodies[d.slug], d.title)
            changes.append(DocChange(d.slug, d.title, d.url, _date(d.update_time), "updated", diff))
    for slug, base in baseline_docs.items():
        if slug not in seen:
            changes.append(DocChange(slug, base["title"], "", "", "removed", ""))
    return changes


def _run_one(config: Config, fetcher, now_ts: int, adapter) -> ExchangeResult:
    try:
        snap_path = config.snapshot_dir / f"{adapter.snapshot_name}.json"
        baseline = snapshot.load_snapshot(snap_path)
        is_baseline = baseline is None
        baseline = baseline or {"docs": {}}

        docs = adapter.fetch_docs(fetcher, config)
        bodies: dict[str, str] = {}
        for d in docs:
            base = baseline["docs"].get(d.slug)
            if is_baseline or base is None or d.update_time != base["update_time"]:
                bodies[d.slug] = adapter.fetch_doc_body(fetcher, config, d)
            else:
                bodies[d.slug] = base.get("body", "")
        doc_changes = [] if is_baseline else build_doc_changes(docs, bodies, baseline["docs"])

        fees_text = adapter.fetch_fees(fetcher, config)
        fee_supported = fees_text is not None
        fee_diff = ""
        if fee_supported and not is_baseline:
            fee_diff = snapshot.unified_diff(baseline.get("fees_text", ""), fees_text, "费率")
        fee_changed = bool(fee_diff)

        anns_new, anns_del = adapter.fetch_announcements(fetcher, config, now_ts)

        new_snap: dict = {
            "docs": {
                d.slug: {"title": d.title, "update_time": d.update_time, "body": bodies[d.slug]}
                for d in docs
            }
        }
        if fee_supported:
            new_snap["fees_text"] = fees_text
        snapshot.save_snapshot(snap_path, new_snap)

        return ExchangeResult(
            name=adapter.name,
            is_baseline=is_baseline,
            doc_changes=doc_changes,
            doc_inventory=docs,
            fee_changed=fee_changed,
            fee_diff=fee_diff,
            fee_supported=fee_supported,
            anns_new=anns_new,
            anns_del=anns_del,
        )
    except Exception as e:  # noqa: BLE001 — 单交易所失败不拖垮其他交易所
        return ExchangeResult(name=adapter.name, is_baseline=False, error=str(e))


def run(config: Config, fetcher, now_ts: int, adapters: list) -> RunResult:
    return RunResult(
        generated_at=datetime.fromtimestamp(now_ts, tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        exchanges=[_run_one(config, fetcher, now_ts, a) for a in adapters],
    )
