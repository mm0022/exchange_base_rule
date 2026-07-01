import json
import pathlib

from exchange_monitor import monitor, snapshot
from exchange_monitor.config import Config

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeFetcher:
    """按 URL 子串返回 fixture。"""

    def __init__(self):
        self.article_body = "第一行\n第二行\n"

    def get_json(self, url, params=None):
        if "search/articles" in url:
            return json.loads((FIX / "doc_list.json").read_text(encoding="utf-8"))
        if "unified/category" in url:
            return json.loads((FIX / "category.json").read_text(encoding="utf-8"))
        if "support/announcements" in url:
            name = "ann_new.json" if params["annType"].endswith("new-listings") else "ann_del.json"
            return json.loads((FIX / name).read_text(encoding="utf-8"))
        raise AssertionError(url)

    def get_text(self, url, params=None):
        if "/fees" in url:
            return (FIX / "fees.html").read_text(encoding="utf-8")
        if "/help/" in url:
            return (FIX / "article.html").read_text(encoding="utf-8")
        raise AssertionError(url)


def test_first_run_is_baseline(tmp_path):
    cfg = Config(snapshot_dir=tmp_path)
    res = monitor.run(cfg, FakeFetcher(), now_ts=1_782_900_000)
    assert res.is_baseline is True
    assert len(res.doc_inventory) == 21
    assert res.doc_changes == []
    assert res.fee_changed is False
    # 公告窗口内仍应列出（近3天）
    cfg_default = Config(snapshot_dir=tmp_path)
    now_ts = 1_782_900_000
    cutoff = now_ts - cfg_default.window_days * 86400
    assert len(res.anns_new) > 0, "窗口内应有新上线公告"
    for ann in res.anns_new:
        assert ann.ptime >= cutoff, f"anns_new 含窗口外条目: {ann.ptime} < {cutoff}"
    for ann in res.anns_del:
        assert ann.ptime >= cutoff, f"anns_del 含窗口外条目: {ann.ptime} < {cutoff}"
    # 基线已落盘
    assert (tmp_path / "okx.json").exists()


def test_second_run_detects_doc_update(tmp_path):
    cfg = Config(snapshot_dir=tmp_path)
    # 先建基线
    monitor.run(cfg, FakeFetcher(), now_ts=1_782_900_000)
    # 篡改基线：把某文档 update_time 调小、body 改旧，制造"已更新"
    snap = snapshot.load_snapshot(tmp_path / "okx.json")
    any_slug = next(iter(snap["docs"]))
    snap["docs"][any_slug]["update_time"] = 1
    snap["docs"][any_slug]["body"] = "旧内容\n"
    snapshot.save_snapshot(tmp_path / "okx.json", snap)
    # 第二次运行
    res = monitor.run(cfg, FakeFetcher(), now_ts=1_782_900_000)
    assert res.is_baseline is False
    assert any(c.slug == any_slug and c.kind == "updated" for c in res.doc_changes)
    changed = next(c for c in res.doc_changes if c.slug == any_slug)
    assert changed.diff  # 有 diff 文本
