"""测试 build_slack_message 纯函数（无网络）。"""
from exchange_monitor.models import Announcement, DocChange, DocMeta, RunResult
from exchange_monitor.slack import build_slack_message


def _doc_meta(slug: str = "test-doc") -> DocMeta:
    return DocMeta(slug=slug, title="测试文档", url=f"/zh-hans/help/{slug}", update_time=1700000000, publish_time=1700000000)


def _ann(title: str = "BTC上线公告") -> Announcement:
    return Announcement(title=title, url="http://www.okx.com/support/hc/article/123", ptime=1700000000, ann_type="announcements-new-listings")


def test_build_slack_message_baseline():
    """基线运行：payload 含 '基线'、公告标题、摘要行。"""
    result = RunResult(
        is_baseline=True,
        generated_at="2026-06-30T00:00:00Z",
        doc_inventory=[_doc_meta()],
        anns_new=[_ann("BTC上线公告")],
    )
    payload = build_slack_message(result, window_days=3)

    assert isinstance(payload, dict)
    assert "text" in payload
    text = payload["text"]
    assert "基线" in text
    assert "BTC上线公告" in text
    assert "• " in text  # 摘要行有 bullet


def test_build_slack_message_with_changes():
    """非基线，有 doc_changes 和 anns_new：text 含 '更新'、文档标题、Slack 链接格式、⬆️。"""
    change = DocChange(
        slug="trading-rules",
        title="交易规则文档",
        url="/zh-hans/help/trading-rules",
        update_date="2026-06-30",
        kind="updated",
        diff="",
    )
    result = RunResult(
        is_baseline=False,
        generated_at="2026-06-30T00:00:00Z",
        doc_changes=[change],
        anns_new=[_ann("ETH上线公告")],
    )
    payload = build_slack_message(result, window_days=3)
    text = payload["text"]

    assert "更新" in text
    assert "交易规则文档" in text
    assert "<https://www.okx.com/zh-hans/help/trading-rules|交易规则文档>" in text
    assert "⬆️" in text
    assert "ETH上线公告" in text


def test_build_slack_message_no_changes():
    """非基线、无变更、无公告：text 仍含摘要行关键词，不抛异常。"""
    result = RunResult(
        is_baseline=False,
        generated_at="2026-06-30T00:00:00Z",
    )
    payload = build_slack_message(result, window_days=3)
    text = payload["text"]

    # summary_lines 非基线输出包含"费率"
    assert "费率" in text
