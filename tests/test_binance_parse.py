import json
import pathlib

from exchange_monitor.exchanges import binance as bn

FIX = pathlib.Path(__file__).parent / "fixtures"


def _j(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_parse_announcements_absolute_url_and_seconds():
    anns = bn.parse_announcements(_j("binance_ann_new.json"), "binance-new-listings")
    assert anns
    a = anns[0]
    assert a.ann_type == "binance-new-listings"
    assert a.url.startswith("https://www.binance.com/")
    assert a.ptime > 1_700_000_000  # 秒（不是毫秒）
    assert any("一" <= ch <= "鿿" for ch in a.title)  # 中文


def test_announcements_total_positive():
    assert bn.announcements_total(_j("binance_ann_new.json")) > 100


def test_collect_leaves_have_catalogid_and_total():
    leaves = bn.collect_leaves(_j("binance_faq_tree.json"))
    assert len(leaves) >= 10
    assert all("catalogId" in lf for lf in leaves)
    # 至少有叶子 total>20（需要翻页）
    assert any((lf.get("total") or 0) > 20 for lf in leaves)


def test_tree_p2_is_global_page():
    # p2 是全树第2页：只含有第2页内容的叶（叶36=5, 叶37=18）
    leaves = bn.collect_leaves(_j("binance_faq_tree_p2.json"))
    counts = {lf.get("catalogId"): len(lf.get("articles") or []) for lf in leaves}
    assert counts.get(36) == 5 and counts.get(37) == 18


def test_parse_detail_returns_body_seconds_title():
    body, upd, title = bn.parse_detail(_j("binance_detail.json"))
    assert isinstance(body, str) and len(body) > 50
    assert upd > 1_700_000_000  # 秒
    assert isinstance(title, str) and title
