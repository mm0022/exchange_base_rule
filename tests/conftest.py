"""Shared test fixtures and helpers."""
import json
import pathlib

FIX = pathlib.Path(__file__).parent / "fixtures"

# slug → section id mapping (matches verified facts) — OKX test helpers
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
