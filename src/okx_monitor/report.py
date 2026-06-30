from okx_monitor.models import RunResult

_KIND_CN = {"new": "新增", "updated": "更新", "removed": "下架"}


def render_markdown(result: RunResult, window_days: int) -> str:
    lines: list[str] = []
    tag = "（基线建立，无 diff）" if result.is_baseline else ""
    lines.append(f"# OKX 监控报告 {result.generated_at} {tag}".rstrip())

    # 一、交易规则
    lines.append("\n## 一、交易规则")
    if result.is_baseline:
        lines.append(f"\n首次运行，记录 {len(result.doc_inventory)} 篇文档为基线：\n")
        for d in result.doc_inventory:
            lines.append(f"- {d.title} — 更新于 {_d(d.update_time)} — https://www.okx.com{d.url}")
    elif not result.doc_changes:
        lines.append("\n相对基线无变化。")
    else:
        lines.append(f"\n相对基线有变化的文档（{len(result.doc_changes)} 篇）：\n")
        for c in result.doc_changes:
            head = f"### [{_KIND_CN.get(c.kind, c.kind)}] {c.title}"
            if c.update_date:
                head += f" — 更新于 {c.update_date}"
            lines.append(head)
            if c.url:
                lines.append(f"https://www.okx.com{c.url}" if c.url.startswith("/") else c.url)
            if c.diff:
                lines.append("\n```diff")
                lines.append(c.diff.rstrip())
                lines.append("```")
            lines.append("")

    # 二、费率规则
    lines.append("\n## 二、费率规则")
    if result.is_baseline:
        lines.append("\n已记录费率页为基线，无 diff。")
    elif result.fee_changed:
        lines.append("\n费率页**有变化**：\n")
        lines.append("```diff")
        lines.append(result.fee_diff.rstrip())
        lines.append("```")
    else:
        lines.append("\n费率页无变化。")

    # 三、上下币公告
    lines.append(f"\n## 三、上下币公告（近 {window_days} 天）")
    lines.append(f"\n### 上币（{len(result.anns_new)} 条）")
    for a in result.anns_new:
        lines.append(f"- {a.title} — {_d(a.ptime)} — {a.url}")
    lines.append(f"\n### 下币（{len(result.anns_del)} 条）")
    for a in result.anns_del:
        lines.append(f"- {a.title} — {_d(a.ptime)} — {a.url}")

    return "\n".join(lines) + "\n"


def summary_lines(result: RunResult) -> list[str]:
    if result.is_baseline:
        return [
            f"[基线] 文档 {len(result.doc_inventory)} 篇已记录",
            f"[基线] 上币 {len(result.anns_new)} / 下币 {len(result.anns_del)}（近窗口）",
        ]
    return [
        f"交易规则变化：{len(result.doc_changes)} 篇",
        f"费率：{'有变化' if result.fee_changed else '无变化'}",
        f"上币 {len(result.anns_new)} / 下币 {len(result.anns_del)}（近窗口）",
    ]


def _d(ts: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
