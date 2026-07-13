import json

from exchange_monitor import monitor, snapshot
from exchange_monitor.config import Config
from exchange_monitor.exchanges.okx import OkxAdapter
from conftest import FIX, _ID_TO_FIXTURE, _SLUG_TO_ID, _expected_total


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
    """在 fetch_docs 时抛异常的假适配器：单块（文档）失败 → warning，不影响其它交易所。"""

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
    """一家交易所文档块抛异常 → warning（非 error）；其他交易所正常；首次+文档失败不建空基线。"""
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

    # BoomExchange 仅文档块失败：记 warning、error 为空、快照未写、不抛出
    assert boom_ex.error == ""
    assert any("文档抓取失败" in w and "boom: 模拟抓取失败" in w for w in boom_ex.warnings)
    assert not (tmp_path / "boom.json").exists()


class _FeeBrokenFetcher(FakeFetcher):
    """费率页始终返回不含 feeDataInfo 的精简版，模拟 OKX 服务端偶发精简变体。"""

    def get_text(self, url, params=None, headers=None):
        if "/fees" in url:
            return "<html><body>no fee data</body></html>"
        return super().get_text(url, params, headers)


def test_fees_failure_isolated(tmp_path):
    """费率块失败（重试仍精简版）→ 记 warning；文档/公告照常；快照仍落盘（不含费率）。"""
    cfg = Config(snapshot_dir=tmp_path)
    res = monitor.run(cfg, _FeeBrokenFetcher(), 1_782_900_000, [OkxAdapter()])
    ex = res.exchanges[0]

    assert ex.error == ""
    assert any("费率抓取失败" in w for w in ex.warnings)
    assert ex.fee_supported is False
    # 文档与公告不受费率失败影响
    assert len(ex.doc_inventory) == _expected_total()
    assert isinstance(ex.anns_new, list) and isinstance(ex.anns_del, list)
    # 快照落盘：有文档、无费率键
    assert (tmp_path / "okx.json").exists()
    snap = snapshot.load_snapshot(tmp_path / "okx.json")
    assert snap["docs"] and "fees_text" not in snap


class _AllBoomAdapter:
    """三块全部抛异常的假适配器：整体失败 → error 非空（供全交易所失败退出码判断）。"""

    name = "AllBoom"
    snapshot_name = "allboom"

    def fetch_docs(self, fetcher, config):
        raise RuntimeError("docs boom")

    def fetch_doc_body(self, fetcher, config, doc):
        return ""

    def fetch_fees(self, fetcher, config):
        raise RuntimeError("fees boom")

    def fetch_announcements(self, fetcher, config, now_ts):
        raise RuntimeError("anns boom")


def test_all_blocks_fail_sets_error(tmp_path):
    """三块全失败 → error 汇总三条；快照不写（首次+文档失败不建空基线）。"""
    cfg = Config(snapshot_dir=tmp_path)
    res = monitor.run(cfg, FakeFetcher(), 1_782_900_000, [_AllBoomAdapter()])
    ex = res.exchanges[0]

    assert ex.error
    assert "docs boom" in ex.error and "fees boom" in ex.error and "anns boom" in ex.error
    assert not (tmp_path / "allboom.json").exists()
