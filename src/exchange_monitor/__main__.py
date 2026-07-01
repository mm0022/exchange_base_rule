import os
import sys
from datetime import UTC, datetime

from exchange_monitor.config import Config
from exchange_monitor.exchanges.binance import BinanceAdapter
from exchange_monitor.exchanges.okx import OkxAdapter
from exchange_monitor.fetcher import Fetcher
from exchange_monitor.monitor import run
from exchange_monitor.report import render_markdown, summary_lines
from exchange_monitor.slack import send_report

ADAPTERS = [OkxAdapter(), BinanceAdapter()]


def main() -> int:
    cfg = Config(slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL"))
    now = datetime.now(tz=UTC)
    now_ts = int(now.timestamp())
    try:
        with Fetcher(cfg) as fetcher:
            result = run(cfg, fetcher, now_ts, ADAPTERS)
    except Exception as e:  # noqa: BLE001 — 顶层兜底，明确报错不静默
        print(f"运行失败: {e}", file=sys.stderr)
        return 1

    has_changes = any(
        ex.is_baseline or ex.doc_changes or ex.fee_changed or ex.error for ex in result.exchanges
    )
    if has_changes:
        md = render_markdown(result, cfg.window_days)
        cfg.report_dir.mkdir(parents=True, exist_ok=True)
        out = cfg.report_dir / f"exchanges-{now.strftime('%Y%m%d-%H%M')}.md"
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
