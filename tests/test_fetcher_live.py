import pytest

from exchange_monitor.config import Config, ANNOUNCEMENTS
from exchange_monitor.fetcher import Fetcher


@pytest.mark.live
def test_live_announcements_reachable():
    with Fetcher(Config()) as f:
        data = f.get_json(ANNOUNCEMENTS, {"annType": "announcements-new-listings", "page": 1})
    assert data["code"] == "0"
    assert data["data"][0]["details"]
