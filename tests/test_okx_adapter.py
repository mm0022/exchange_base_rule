import json
import pathlib

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

# section id → fixture file
_ID_TO_FIXTURE = {
    "3HsUPMtNszv47YPMMMx8Dw": "doc_list.json",
    "7DvsH1pG7hjFKaGZ3ueWrZ": "okx_docs_risk.json",
    "3PfY4vSgD5mPa1Iww4b9fn": "okx_docs_spot.json",
    "4kHVrztBXA1RumrYkfdm8T": "okx_docs_perp.json",
}


def _expected_total() -> int:
    """Dynamically compute expected doc count from fixture totals."""
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


def test_okx_adapter_identity():
    a = OkxAdapter()
    assert a.name == "OKX" and a.snapshot_name == "okx"


def test_fetch_docs_absolute_url_and_count():
    docs = OkxAdapter().fetch_docs(FakeFetcher(), Config())
    assert len(docs) == _expected_total()
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
