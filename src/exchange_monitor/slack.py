"""把监控结果组装为 Slack 消息并发送（Incoming Webhook）。"""
from exchange_monitor.models import RunResult
from exchange_monitor.report import summary_lines

_KIND_CN = {"new": "新增", "updated": "更新", "removed": "下架"}


def build_slack_message(result: RunResult, window_days: int) -> dict:
    """组装 Slack Incoming Webhook 的 payload（mrkdwn 文本）。每次运行都发。"""
    lines: list[str] = []
    title = "*OKX 监控*" + ("（基线建立）" if result.is_baseline else "")
    lines.append(f"{title}  {result.generated_at}")
    # 摘要行（复用 report.summary_lines）
    for s in summary_lines(result):
        lines.append("• " + s)
    # 变更文档（非基线且有变更时）
    if not result.is_baseline and result.doc_changes:
        lines.append("")
        lines.append("*交易规则变更：*")
        for c in result.doc_changes:
            label = _KIND_CN.get(c.kind, c.kind)
            url = f"https://www.okx.com{c.url}" if c.url.startswith("/") else c.url
            if url:
                lines.append(f"• [{label}] <{url}|{c.title}>")
            else:
                lines.append(f"• [{label}] {c.title}")
    # 近 N 天上/下币公告
    if result.anns_new or result.anns_del:
        lines.append("")
        lines.append(f"*上下币公告（近 {window_days} 天）：*")
        for a in result.anns_new:
            lines.append(f"• ⬆️ <{a.url}|{a.title}>")
        for a in result.anns_del:
            lines.append(f"• ⬇️ <{a.url}|{a.title}>")
    return {"text": "\n".join(lines)}


def send_report(fetcher, webhook_url: str, result: RunResult, window_days: int) -> None:
    """发送到 Slack。失败时由 fetcher.post_json 抛出，调用方负责处理。"""
    payload = build_slack_message(result, window_days)
    fetcher.post_json(webhook_url, payload)
