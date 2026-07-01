import json
import pathlib

from exchange_monitor import monitor, snapshot
from exchange_monitor.config import Config
from exchange_monitor.exchanges.okx import OkxAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"

# slug → section id mapping (matches verified facts)
_SLUG_TO_ID = {
    "product-documentation-introduction-to-basic-trading-rules": "3HsUPMtNszv47YPMMMx8Dw",
    "product-documentation-risk-management": "7DvsH1pG7hjFKaGZ3ueWrZ",
    "product-documentation-spot-margin-trading": "3PfY4vSgD5mPa1Iww4b9fn",
    "product-documentation-perpetual-contracts": "4kHVrztBXA1RumrYkfdm8T",
}

_ID_TO_FIXTURE = {
    "3HsUPMtNszv47YPMMMx8Dw": "doc_list.json",
    "7DvsH1pG7hjFKaGZ3ueWrZ": "okx_docs_risk.json",
    "3PfY4vSgD5mPa1Iww4b9fn": "okx_docs_spot.json",
    "4kHVrztBXA1RumrYkfdm8T": "okx_docs_perp.json",
}


def _expected_total() -> int:
    return sum(
        json.loads((FIX / fname).read_text(encoding="utf-8"))["data"]["total"]
        for fname in _ID_TO_FIXTURE.values()
    )


class FakeFetcher:
    def get_json(self, url, params=None, headers=None):
        if "unified/section" in url:
            slug = params["slug"]
            sid = _SLUG_TO_ID[slug]
            return {"data": {"section": {"id": sid, "slug": slug}}}
        if "search/articles" in url:
            sid = params["sectionIds"]
            fname = _ID_TO_FIXTURE[sid]
            return json.loads((FIX / fname).read_text(encoding="utf-8"))
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
    assert len(ex.doc_inventory) == _expected_total()
    assert ex.doc_changes == []
    assert ex.fee_changed is False and ex.fee_supported is True
    # 基线时公告字段也应被填充为列表，且都在近 N 天窗口内
    cutoff = 1_782_900_000 - cfg.window_days * 86400
    assert isinstance(ex.anns_new, list) and isinstance(ex.anns_del, list)
    assert all(a.ptime >= cutoff for a in ex.anns_new + ex.anns_del)
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


class _BoomAdapter:
    """总是在 fetch_docs 时抛异常的假适配器，用于测试每交易所隔离。"""

    name = "BoomExchange"
    snapshot_name = "boom"

    def fetch_docs(self, fetcher, config):
        raise RuntimeError("boom: 模拟抓取失败")

    def fetch_doc_body(self, fetcher, config, doc):
        return ""

    def fetch_fees(self, fetcher, config):
        return None

    def fetch_announcements(self, fetcher, config, now_ts):
        return [], []


def test_boom_adapter_isolation(tmp_path):
    """一家交易所抛异常 → error 非空；其他交易所正常运行；失败交易所快照未写。"""
    cfg = Config(snapshot_dir=tmp_path)
    adapters = [OkxAdapter(), _BoomAdapter()]
    res = monitor.run(cfg, FakeFetcher(), 1_782_900_000, adapters)

    assert len(res.exchanges) == 2
    okx_ex = next(e for e in res.exchanges if e.name == "OKX")
    boom_ex = next(e for e in res.exchanges if e.name == "BoomExchange")

    # OKX 正常完成（基线建立）
    assert okx_ex.error == ""
    assert okx_ex.is_baseline is True
    assert (tmp_path / "okx.json").exists()

    # BoomExchange 记录错误，快照未写，不抛出
    assert "boom: 模拟抓取失败" in boom_ex.error
    assert not (tmp_path / "boom.json").exists()
