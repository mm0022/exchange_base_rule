import logging
import os
from datetime import UTC, datetime

from exchange_monitor.config import Config
from exchange_monitor.exchanges.binance import BinanceAdapter
from exchange_monitor.exchanges.bybit import BybitAdapter
from exchange_monitor.exchanges.okx import OkxAdapter
from exchange_monitor.fetcher import Fetcher
from exchange_monitor.logsetup import setup_logging
from exchange_monitor.monitor import run
from exchange_monitor.report import render_markdown, summary_lines
from exchange_monitor.slack import send_report

ADAPTERS = [OkxAdapter(), BinanceAdapter(), BybitAdapter()]

log = logging.getLogger(__name__)


def main() -> int:
    cfg = Config(slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL"))
    setup_logging(cfg.log_dir)
    now = datetime.now(tz=UTC)
    now_ts = int(now.timestamp())
    log.info("=== 运行开始 %s UTC ===", now.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        with Fetcher(cfg) as fetcher:
            result = run(cfg, fetcher, now_ts, ADAPTERS)
    except Exception as e:  # noqa: BLE001 — 顶层兜底，明确报错不静默
        log.exception("运行失败: %s", e)
        log.info("=== 运行结束 (exit 1) ===")
        return 1

    has_changes = any(
        ex.is_baseline or ex.doc_changes or ex.fee_changed or ex.error for ex in result.exchanges
    )
    if has_changes:
        md = render_markdown(result, cfg.window_days)
        cfg.report_dir.mkdir(parents=True, exist_ok=True)
        out = cfg.report_dir / f"exchanges-{now.strftime('%Y%m%d-%H%M')}.md"
        out.write_text(md, encoding="utf-8")
        log.info("报告已写入: %s", out)
    else:
        log.info("本次无变化，未写报告")
    for line in summary_lines(result):
        log.info("  %s", line)

    if cfg.slack_webhook_url:
        try:
            with Fetcher(cfg) as fetcher:
                send_report(fetcher, cfg.slack_webhook_url, result, cfg.window_days)
            log.info("已发送到 Slack")
        except Exception as e:  # noqa: BLE001 — 发送失败需可见
            log.error("Slack 发送失败: %s", e)
            log.info("=== 运行结束 (exit 1) ===")
            return 1
    else:
        log.info("未配置 SLACK_WEBHOOK_URL，跳过 Slack 发送")

    # 全部交易所都抓取失败（如代理未启动）视为整体失败：退出码 1（供定时任务重试判断）。
    # 报告与 Slack 仍已发出，失败可见。
    if result.exchanges and all(ex.error for ex in result.exchanges):
        log.error("所有交易所均抓取失败")
        log.info("=== 运行结束 (exit 1) ===")
        return 1
    log.info("=== 运行结束 (exit 0) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
