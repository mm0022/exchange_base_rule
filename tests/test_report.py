from exchange_monitor import report
from exchange_monitor.models import Announcement, DocChange, DocMeta, ExchangeResult, RunResult


def _baseline_run():
    return RunResult(
        generated_at="2026-07-01 03:00 UTC",
        exchanges=[ExchangeResult(
            name="OKX", is_baseline=True, fee_supported=True,
            doc_inventory=[DocMeta("s1", "基础委托类型", "https://www.okx.com/help/s1", 1_782_000_000, 1_700_000_000)],
            anns_new=[Announcement("某币上线", "https://www.okx.com/help/1", 1_782_800_000, "announcements-new-listings")],
        )],
    )


def test_markdown_marks_baseline_and_exchange_name():
    md = report.render_markdown(_baseline_run(), 3)
    assert "OKX" in md and "基线建立" in md
    assert "基础委托类型" in md and "某币上线" in md


def test_markdown_shows_doc_diff_with_absolute_url():
    res = RunResult(generated_at="2026-07-01 03:00 UTC", exchanges=[ExchangeResult(
        name="OKX", is_baseline=False, fee_supported=True,
        doc_changes=[DocChange("s1", "基础委托类型", "https://www.okx.com/help/s1", "2026-06-29", "updated", "@@ -1 +1 @@\n-旧\n+新\n")],
    )])
    md = report.render_markdown(res, 3)
    assert "更新" in md and "+新" in md and "https://www.okx.com/help/s1" in md


def test_summary_lines_per_exchange():
    lines = report.summary_lines(_baseline_run())
    assert lines and any("OKX" in ln for ln in lines)


def test_render_exchange_error_section():
    """error 非空时，_render_exchange 输出 ⚠️ 行后 return，不输出后续章节。"""
    res = RunResult(
        generated_at="2026-07-01 03:00 UTC",
        exchanges=[ExchangeResult(name="BoomExchange", is_baseline=False, error="连接超时")],
    )
    md = report.render_markdown(res, 3)
    assert "BoomExchange" in md
    assert "⚠️" in md and "连接超时" in md
    # 出错时不渲染常规章节
    assert "交易规则" not in md
    assert "费率规则" not in md


def test_summary_lines_includes_error():
    """summary_lines 对 error 非空的交易所显示抓取失败行。"""
    res = RunResult(
        generated_at="2026-07-01 03:00 UTC",
        exchanges=[ExchangeResult(name="BoomExchange", is_baseline=False, error="DNS 解析失败")],
    )
    lines = report.summary_lines(res)
    assert any("BoomExchange" in ln and "抓取失败" in ln and "DNS 解析失败" in ln for ln in lines)
