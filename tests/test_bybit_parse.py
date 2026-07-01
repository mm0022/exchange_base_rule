import json
import pathlib

from exchange_monitor.exchanges import bybit as by

FIX = pathlib.Path(__file__).parent / "fixtures"


def _txt(name):
    return (FIX / name).read_text(encoding="utf-8")


def _json(name):
    return json.loads(_txt(name))


def test_parse_announcements_seconds_absolute_chinese():
    anns = by.parse_announcements(_json("bybit_ann_new.json"), "bybit-new-listings")
    assert anns
    a = anns[0]
    assert a.ann_type == "bybit-new-listings"
    assert a.url.startswith("http")
    assert a.ptime > 1_700_000_000  # 秒
    assert any("一" <= ch <= "鿿" for ch in a.title)


def test_announcements_total_positive():
    assert by.announcements_total(_json("bybit_ann_new.json")) > 100


def test_parse_last_updated_utc_seconds():
    ts = by.parse_last_updated("2026-01-23 09:57:02")
    # 2026-01-23 09:57:02 UTC
    assert ts == 1769162222


def test_collect_articles_from_topic():
    data = by.extract_next_data(_txt("bybit_topic.html"))["props"]["pageProps"]["data"]
    arts = by.collect_articles(data)
    assert len(arts) >= 10
    assert all(x.get("url") and x.get("title") for x in arts)


def test_parse_article_body_seconds_title():
    body, upd, title = by.parse_article(_txt("bybit_article.html"))
    assert len(body) > 200
    assert upd > 1_700_000_000
    assert isinstance(title, str) and title
