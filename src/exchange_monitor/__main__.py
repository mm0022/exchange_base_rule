import os
import sys
from datetime import UTC, datetime

from exchange_monitor.config import Config
from exchange_monitor.fetcher import Fetcher
from exchange_monitor.monitor import run
from exchange_monitor.report import render_markdown, summary_lines
from exchange_monitor.slack import send_report


def main() -> int:
    cfg = Config(slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL"))
    now = datetime.now(tz=UTC)
    now_ts = int(now.timestamp())
    try:
        with Fetcher(cfg) as fetcher:
            result = run(cfg, fetcher, now_ts)
    except Exception as e:  # noqa: BLE001 — 顶层兜底，明确报错不静默
        print(f"运行失败: {e}", file=sys.stderr)
        return 1

    # 仅在有实质变更时写报告文件（首次基线也写，作为参照起点）。
    # "变更" = 文档变化 或 费率变化；上下币公告是滚动窗口、每次都有，不计为变更。
    has_changes = result.is_baseline or bool(result.doc_changes) or result.fee_changed
    if has_changes:
        md = render_markdown(result, cfg.window_days)
        cfg.report_dir.mkdir(parents=True, exist_ok=True)
        out = cfg.report_dir / f"okx-{now.strftime('%Y%m%d-%H%M')}.md"
        out.write_text(md, encoding="utf-8")
        print(f"\n报告已写入: {out}\n")
    else:
        print("\n本次无变化，未写报告\n")
    for line in summary_lines(result):
        print("  " + line)
    if cfg.slack_webhook_url:
        try:
            with Fetcher(cfg) as fetcher:
                send_report(fetcher, cfg.slack_webhook_url, result, cfg.window_days)
            print("  已发送到 Slack")
        except Exception as e:  # noqa: BLE001 — 发送失败需可见
            print(f"Slack 发送失败: {e}", file=sys.stderr)
            return 1
    else:
        print("  未配置 SLACK_WEBHOOK_URL，跳过 Slack 发送")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
