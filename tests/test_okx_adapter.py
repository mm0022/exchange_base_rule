import json
import pathlib

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


def test_okx_adapter_identity():
    a = OkxAdapter()
    assert a.name == "OKX" and a.snapshot_name == "okx"


def test_fetch_docs_absolute_url_and_count():
    docs = OkxAdapter().fetch_docs(FakeFetcher(), Config())
    assert len(docs) == 21
    assert all(d.url.startswith("https://www.okx.com") for d in docs)
    assert all(d.update_time > 1_700_000_000 for d in docs)


def test_fetch_fees_and_body_nonempty():
    a = OkxAdapter()
    fees = a.fetch_fees(FakeFetcher(), Config())
    assert fees and "feeTables" in fees
    docs = a.fetch_docs(FakeFetcher(), Config())
    body = a.fetch_doc_body(FakeFetcher(), Config(), docs[0])
    assert "委托" in body


def test_fetch_announcements_split_and_window():
    a = OkxAdapter()
    new, delist = a.fetch_announcements(FakeFetcher(), Config(), now_ts=1_782_900_000)
    assert isinstance(new, list) and isinstance(delist, list)
    cutoff = 1_782_900_000 - 3 * 86400
    assert all(x.ptime >= cutoff for x in new + delist)
