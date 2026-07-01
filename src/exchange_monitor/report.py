from datetime import UTC, datetime

from exchange_monitor.models import ExchangeResult, RunResult

_KIND_CN = {"new": "新增", "updated": "更新", "removed": "下架"}


def _d(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


def _render_exchange(lines: list[str], ex: ExchangeResult, window_days: int) -> None:
    if ex.error:
        lines.append(f"\n# {ex.name}")
        lines.append(f"\n⚠️ 抓取失败：{ex.error}\n")
        return
    tag = "（基线建立，无 diff）" if ex.is_baseline else ""
    lines.append(f"\n# {ex.name}{tag}")

    lines.append("\n## 一、交易规则")
    if ex.is_baseline:
        lines.append(f"\n首次运行，记录 {len(ex.doc_inventory)} 篇文档为基线：\n")
        for d in ex.doc_inventory:
            lines.append(f"- {d.title} — 更新于 {_d(d.update_time)} — {d.url}")
    elif not ex.doc_changes:
        lines.append("\n相对基线无变化。")
    else:
        lines.append(f"\n相对基线有变化的文档（{len(ex.doc_changes)} 篇）：\n")
        for c in ex.doc_changes:
            head = f"### [{_KIND_CN.get(c.kind, c.kind)}] {c.title}"
            if c.update_date:
                head += f" — 更新于 {c.update_date}"
            lines.append(head)
            if c.url:
                lines.append(c.url)
            if c.diff:
                lines.append("\n```diff")
                lines.append(c.diff.rstrip())
                lines.append("```")
            lines.append("")

    if ex.fee_supported:
        lines.append("\n## 二、费率规则")
        if ex.is_baseline:
            lines.append("\n已记录费率页为基线，无 diff。")
        elif ex.fee_changed:
            lines.append("\n费率页**有变化**：\n")
            lines.append("```diff")
            lines.append(ex.fee_diff.rstrip())
            lines.append("```")
        else:
            lines.append("\n费率页无变化。")

    lines.append(f"\n## 三、上下币公告（近 {window_days} 天）")
    lines.append(f"\n### 上币（{len(ex.anns_new)} 条）")
    for a in ex.anns_new:
        lines.append(f"- {a.title} — {_d(a.ptime)} — {a.url}")
    lines.append(f"\n### 下币（{len(ex.anns_del)} 条）")
    for a in ex.anns_del:
        lines.append(f"- {a.title} — {_d(a.ptime)} — {a.url}")


def render_markdown(result: RunResult, window_days: int) -> str:
    lines = [f"# 交易所监控报告 {result.generated_at}"]
    for ex in result.exchanges:
        _render_exchange(lines, ex, window_days)
    return "\n".join(lines) + "\n"


def summary_lines(result: RunResult) -> list[str]:
    out: list[str] = []
    for ex in result.exchanges:
        if ex.error:
            out.append(f"[{ex.name}] 抓取失败：{ex.error}")
        elif ex.is_baseline:
            out.append(
                f"[{ex.name}] 基线: 文档 {len(ex.doc_inventory)} 篇 / "
                f"上币 {len(ex.anns_new)} 下币 {len(ex.anns_del)}"
            )
        else:
            fee = ("费率有变化" if ex.fee_changed else "费率无变化") if ex.fee_supported else "费率未监控"
            out.append(
                f"[{ex.name}] 文档变更 {len(ex.doc_changes)} 篇 / {fee} / "
                f"上币 {len(ex.anns_new)} 下币 {len(ex.anns_del)}"
            )
    return out
