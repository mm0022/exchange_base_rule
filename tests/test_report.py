from okx_monitor import report
from okx_monitor.models import Announcement, DocChange, DocMeta, RunResult


def _baseline_result():
    return RunResult(
        is_baseline=True,
        generated_at="2026-06-30 03:00 UTC",
        doc_inventory=[DocMeta("s1", "基础委托类型", "/help/s1", 1_782_000_000, 1_700_000_000)],
        anns_new=[Announcement("某币上线", "http://x/1", 1_782_800_000, "announcements-new-listings")],
    )


def test_markdown_marks_baseline():
    md = report.render_markdown(_baseline_result(), window_days=3)
    assert "基线建立" in md
    assert "基础委托类型" in md
    assert "某币上线" in md


def test_markdown_shows_doc_diff():
    res = RunResult(
        is_baseline=False,
        generated_at="2026-06-30 03:00 UTC",
        doc_changes=[DocChange("s1", "基础委托类型", "/help/s1", "2026-06-29", "updated", "@@ -1 +1 @@\n-旧\n+新\n")],
    )
    md = report.render_markdown(res, window_days=3)
    assert "基础委托类型" in md
    assert "+新" in md
    assert "更新" in md


def test_summary_lines_nonempty():
    assert report.summary_lines(_baseline_result())
