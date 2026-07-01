from dataclasses import dataclass
from pathlib import Path

BASE = "https://www.okx.com"
SEARCH_ARTICLES = f"{BASE}/priapi/v1/assistant/service-center/search/articles"
CATEGORY = f"{BASE}/priapi/v1/assistant/service-center/kb/unified/category"
ANNOUNCEMENTS = f"{BASE}/api/v5/support/announcements"
FEES_URL = f"{BASE}/zh-hans/fees"
ARTICLE_URL = f"{BASE}/zh-hans/help"  # + /{slug}
CATEGORY_SLUG = "product-documentation"
SECTION_SLUG = "product-documentation-introduction-to-basic-trading-rules"


@dataclass
class Config:
    proxy: str = "http://127.0.0.1:7890"
    accept_language: str = "zh-CN,zh"
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    section_slug: str = SECTION_SLUG
    category_slug: str = CATEGORY_SLUG
    window_days: int = 3
    snapshot_dir: Path = Path("snapshots")
    report_dir: Path = Path("reports")
    timeout: float = 20.0
    retries: int = 3
    request_delay: float = 0.5  # 每次请求后小延时，避免限频
    slack_webhook_url: str | None = None
