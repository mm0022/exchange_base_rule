from exchange_monitor import slack
from exchange_monitor.models import Announcement, DocChange, DocMeta, ExchangeResult, RunResult


def _run(exchanges):
    return RunResult(generated_at="2026-07-01 03:00 UTC", exchanges=exchanges)


def test_build_slack_message_baseline():
    r = _run([ExchangeResult(
        name="OKX", is_baseline=True,
        doc_inventory=[DocMeta("s1", "基础委托类型", "https://x/1", 1_782_000_000, 1_700_000_000)],
        anns_new=[Announcement("某币上线", "https://x/a", 1_782_800_000, "announcements-new-listings")],
    )])
    payload = slack.build_slack_message(r, 3)
    assert isinstance(payload, dict) and "text" in payload
    assert "OKX" in payload["text"] and "某币上线" in payload["text"] and "• " in payload["text"]


def test_build_slack_message_with_changes():
    r = _run([ExchangeResult(
        name="Binance", is_baseline=False,
        doc_changes=[DocChange("s1", "交易规则文档", "https://b/help/s1", "2026-06-30", "updated", "d")],
        anns_new=[Announcement("上新X", "https://b/a", 1_782_800_000, "48")],
    )])
    text = slack.build_slack_message(r, 3)["text"]
    assert "Binance" in text and "更新" in text
    assert "<https://b/help/s1|交易规则文档>" in text and "⬆️" in text


def test_build_slack_message_no_changes_has_summary():
    r = _run([ExchangeResult(name="OKX", is_baseline=False, fee_supported=True)])
    text = slack.build_slack_message(r, 3)["text"]
    assert "OKX" in text and "• " in text
