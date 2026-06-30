import os
import sys
from datetime import UTC, datetime

from okx_monitor.config import Config
from okx_monitor.fetcher import Fetcher
from okx_monitor.monitor import run
from okx_monitor.report import render_markdown, summary_lines
from okx_monitor.slack import send_report


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

    md = render_markdown(result, cfg.window_days)
    cfg.report_dir.mkdir(parents=True, exist_ok=True)
    out = cfg.report_dir / f"okx-{now.strftime('%Y%m%d-%H%M')}.md"
    out.write_text(md, encoding="utf-8")

    print(f"\n报告已写入: {out}\n")
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
