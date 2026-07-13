import logging
import time
from datetime import UTC, datetime

from exchange_monitor import snapshot
from exchange_monitor.config import Config
from exchange_monitor.models import (
    Announcement,
    DocChange,
    DocMeta,
    ExchangeResult,
    RunResult,
)

log = logging.getLogger(__name__)


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
        elif bodies[d.slug] != base.get("body", ""):
            diff = snapshot.unified_diff(base.get("body", ""), bodies[d.slug], d.title)
            changes.append(DocChange(d.slug, d.title, d.url, _date(d.update_time), "updated", diff))
    for slug, base in baseline_docs.items():
        if slug not in seen:
            changes.append(DocChange(slug, base["title"], "", "", "removed", ""))
    return changes


def _run_one(config: Config, fetcher, now_ts: int, adapter) -> ExchangeResult:
    """抓取单个交易所。文档/费率/公告三块各自隔离：一块失败只记 warning，
    另两块照常跑；三块全失败才置 error（供全交易所失败退出码判断）。
    快照按块保留——失败的块不覆盖旧基线。"""
    t0 = time.monotonic()
    log.info("[%s] 开始抓取", adapter.name)
    snap_path = config.snapshot_dir / f"{adapter.snapshot_name}.json"
    baseline = snapshot.load_snapshot(snap_path)
    is_baseline = baseline is None
    baseline = baseline or {"docs": {}}

    warnings: list[str] = []
    new_snap: dict = dict(baseline)  # 从旧基线拷贝，成功的块覆盖之，失败的块原样保留

    # --- 文档块 ---
    docs: list[DocMeta] | None = None
    doc_changes: list[DocChange] = []
    try:
        docs = adapter.fetch_docs(fetcher, config)
        log.info("[%s] 文档 %d 篇%s", adapter.name, len(docs), "（首次基线）" if is_baseline else "")
        # 变更检测只看正文内容（交易所常静默改正文而不更新时间戳），故每次都抓正文。
        bodies: dict[str, str] = {d.slug: adapter.fetch_doc_body(fetcher, config, d) for d in docs}
        doc_changes = [] if is_baseline else build_doc_changes(docs, bodies, baseline["docs"])
        new_snap["docs"] = {
            d.slug: {"title": d.title, "update_time": d.update_time, "body": bodies[d.slug]}
            for d in docs
        }
    except Exception as e:  # noqa: BLE001 — 单块失败不拖垮其它块
        log.exception("[%s] 文档抓取失败", adapter.name)
        warnings.append(f"文档抓取失败: {e}")

    # --- 费率块 ---
    fees_text = None
    fee_supported = False
    fee_diff = ""
    try:
        fees_text = adapter.fetch_fees(fetcher, config)
        fee_supported = fees_text is not None
        if fee_supported:
            if not is_baseline:
                fee_diff = snapshot.unified_diff(baseline.get("fees_text", ""), fees_text, "费率")
            new_snap["fees_text"] = fees_text
    except Exception as e:  # noqa: BLE001
        log.exception("[%s] 费率抓取失败", adapter.name)
        warnings.append(f"费率抓取失败: {e}")
    fee_changed = bool(fee_diff)

    # --- 公告块 ---
    anns_new: list[Announcement] = []
    anns_del: list[Announcement] = []
    try:
        anns_new, anns_del = adapter.fetch_announcements(fetcher, config, now_ts)
    except Exception as e:  # noqa: BLE001
        log.exception("[%s] 公告抓取失败", adapter.name)
        warnings.append(f"公告抓取失败: {e}")

    if fee_supported:
        fee_status = "变化" if fee_changed else "无变化"
    elif any(w.startswith("费率") for w in warnings):
        fee_status = "失败"
    else:
        fee_status = "未监控"
    log.info(
        "[%s] 完成：文档变更 %d 篇 / 费率%s / 公告 上%d 下%d / 耗时 %.1fs%s",
        adapter.name, len(doc_changes), fee_status,
        len(anns_new), len(anns_del), time.monotonic() - t0,
        f" / ⚠️{len(warnings)} 块失败" if warnings else "",
    )

    # 快照：文档成功时落盘（含被保留的旧费率/新费率）；文档失败时仅当已有旧基线才落盘
    # （成功的费率仍能持久化），首次运行文档就失败则不建空基线。
    if docs is not None or not is_baseline:
        snapshot.save_snapshot(snap_path, new_snap)

    # 三块全失败 → 整体失败（如代理未启动），置 error 供 __main__ 全失败退出码判断
    error = "; ".join(warnings) if len(warnings) == 3 else ""

    return ExchangeResult(
        name=adapter.name,
        is_baseline=is_baseline,
        doc_changes=doc_changes,
        doc_inventory=docs or [],
        fee_changed=fee_changed,
        fee_diff=fee_diff,
        fee_supported=fee_supported,
        anns_new=anns_new,
        anns_del=anns_del,
        warnings=warnings,
        error=error,
    )


def run(config: Config, fetcher, now_ts: int, adapters: list) -> RunResult:
    return RunResult(
        generated_at=datetime.fromtimestamp(now_ts, tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        exchanges=[_run_one(config, fetcher, now_ts, a) for a in adapters],
    )
