from dataclasses import dataclass, field
from pathlib import Path

BASE = "https://www.okx.com"
SEARCH_ARTICLES = f"{BASE}/priapi/v1/assistant/service-center/search/articles"
CATEGORY = f"{BASE}/priapi/v1/assistant/service-center/kb/unified/category"
SECTION = f"{BASE}/priapi/v1/assistant/service-center/kb/unified/section"
ANNOUNCEMENTS = f"{BASE}/api/v5/support/announcements"
FEES_URL = f"{BASE}/en/fees"
ARTICLE_URL = f"{BASE}/en/help"  # + /{slug}
CATEGORY_SLUG = "product-documentation"
SECTION_SLUGS = [
    "product-documentation-introduction-to-basic-trading-rules",
    "product-documentation-risk-management",
    "product-documentation-spot-margin-trading",
    "product-documentation-perpetual-contracts",
]


@dataclass
class Config:
    proxy: str = "http://127.0.0.1:7890"
    accept_language: str = "en-US,en"
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    section_slugs: list[str] = field(default_factory=lambda: SECTION_SLUGS)
    category_slug: str = CATEGORY_SLUG
    window_days: int = 3
    snapshot_dir: Path = Path("snapshots")
    report_dir: Path = Path("reports")
    timeout: float = 20.0
    retries: int = 3
    request_delay: float = 0.5  # 每次请求后小延时，避免限频
    slack_webhook_url: str | None = None
    binance_detail_delay: float = 3.0  # Binance detail 接口额外节流(限频较严)
    rate_limit_backoff: float = 30.0  # HTTP 429 退避基数（秒），实际等待 = backoff*(attempt+1)


# --- Binance ---
BINANCE_BASE = "https://www.binance.com"
BINANCE_CMS_LIST = f"{BINANCE_BASE}/bapi/composite/v1/public/cms/article/list/query"
BINANCE_CMS_DETAIL = f"{BINANCE_BASE}/bapi/composite/v1/public/cms/article/detail/query"
BINANCE_ANN_NEW_CATALOG = 48   # 新币上线
BINANCE_ANN_DEL_CATALOG = 161  # 下架讯息
BINANCE_FAQ_ROOT_CATALOG = 4     # 抓这棵树
BINANCE_FAQ_BRANCH = 18          # 只监控「合约交易」分支
BINANCE_BODY_DIFF_LEAVES = frozenset({214, 63})  # 统一账户 + U本位合约：存正文做 diff；其余叶只对比 lastUpdateTime
BINANCE_LANG = {"lang": "en"}
BINANCE_WEB_LOCALE = "en"

# --- Bybit ---
BYBIT_ANN_API = "https://api.bybit.com/v5/announcements/index"
BYBIT_LOCALE = "en"                        # 英文版；英文内容更完整（~25 篇）
BYBIT_HELP_BASE = "https://www.bybit.com"  # + /{locale}/help-center/topic-list|article/{...}
BYBIT_TOPIC = "unified-trading-account"    # 统一交易账户主题（含子主题）
