"""把多交易所监控结果组装为 Slack 消息并发送（Incoming Webhook）。"""
from exchange_monitor.models import RunResult
from exchange_monitor.report import summary_lines

_KIND_CN = {"new": "新增", "updated": "更新", "removed": "下架"}


def build_slack_message(result: RunResult, window_days: int) -> dict:
    lines: list[str] = [f"*交易所监控*  {result.generated_at}"]
    for s in summary_lines(result):
        lines.append("• " + s)
    for ex in result.exchanges:
        seg: list[str] = []
        if not ex.is_baseline and ex.doc_changes:
            seg.append(f"*{ex.name} 规则变更：*")
            for c in ex.doc_changes:
                label = _KIND_CN.get(c.kind, c.kind)
                seg.append(f"• [{label}] <{c.url}|{c.title}>" if c.url else f"• [{label}] {c.title}")
        if ex.anns_new or ex.anns_del:
            seg.append(f"*{ex.name} 上下币（近 {window_days} 天）：*")
            for a in ex.anns_new:
                seg.append(f"• ⬆️ <{a.url}|{a.title}>")
            for a in ex.anns_del:
                seg.append(f"• ⬇️ <{a.url}|{a.title}>")
        if seg:
            lines.append("")
            lines.extend(seg)
    return {"text": "\n".join(lines)}


def send_report(fetcher, webhook_url: str, result: RunResult, window_days: int) -> None:
    """发送到 Slack。失败时由 fetcher.post_json 抛出，调用方负责处理。"""
    payload = build_slack_message(result, window_days)
    fetcher.post_json(webhook_url, payload)
