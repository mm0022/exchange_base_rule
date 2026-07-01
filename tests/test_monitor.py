import json
import pathlib

from exchange_monitor import monitor, snapshot
from exchange_monitor.config import Config
from exchange_monitor.exchanges.okx import OkxAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeFetcher:
    def get_json(self, url, params=None, headers=None):
        if "search/articles" in url:
            return json.loads((FIX / "doc_list.json").read_text(encoding="utf-8"))
        if "unified/category" in url:
            return json.loads((FIX / "category.json").read_text(encoding="utf-8"))
        if "support/announcements" in url:
            name = "ann_new.json" if params["annType"].endswith("new-listings") else "ann_del.json"
            return json.loads((FIX / name).read_text(encoding="utf-8"))
        raise AssertionError(url)

    def get_text(self, url, params=None, headers=None):
        if "/fees" in url:
            return (FIX / "fees.html").read_text(encoding="utf-8")
        if "/help/" in url:
            return (FIX / "article.html").read_text(encoding="utf-8")
        raise AssertionError(url)


def test_first_run_is_baseline(tmp_path):
    cfg = Config(snapshot_dir=tmp_path)
    res = monitor.run(cfg, FakeFetcher(), 1_782_900_000, [OkxAdapter()])
    ex = res.exchanges[0]
    assert ex.name == "OKX"
    assert ex.is_baseline is True
    assert len(ex.doc_inventory) == 21
    assert ex.doc_changes == []
    assert ex.fee_changed is False and ex.fee_supported is True
    assert (tmp_path / "okx.json").exists()


def test_second_run_detects_doc_update(tmp_path):
    cfg = Config(snapshot_dir=tmp_path)
    monitor.run(cfg, FakeFetcher(), 1_782_900_000, [OkxAdapter()])
    snap = snapshot.load_snapshot(tmp_path / "okx.json")
    any_slug = next(iter(snap["docs"]))
    snap["docs"][any_slug]["update_time"] = 1
    snap["docs"][any_slug]["body"] = "旧内容\n"
    snapshot.save_snapshot(tmp_path / "okx.json", snap)
    res = monitor.run(cfg, FakeFetcher(), 1_782_900_000, [OkxAdapter()])
    ex = res.exchanges[0]
    assert ex.is_baseline is False
    changed = next(c for c in ex.doc_changes if c.slug == any_slug)
    assert changed.kind == "updated" and changed.diff
