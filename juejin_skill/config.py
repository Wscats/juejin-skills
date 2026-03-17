"""Configuration constants for Juejin API."""

# Juejin base URLs
JUEJIN_WEB_URL = "https://juejin.cn"
JUEJIN_API_BASE = "https://api.juejin.cn"

# API endpoints
CATEGORY_BRIEFS_URL = f"{JUEJIN_API_BASE}/tag_api/v1/query_category_briefs"
CATEGORY_TAGS_URL = f"{JUEJIN_API_BASE}/recommend_api/v1/tag/recommend_tag_list"
RECOMMEND_ALL_FEED_URL = f"{JUEJIN_API_BASE}/recommend_api/v1/article/recommend_all_feed"
RECOMMEND_CATE_FEED_URL = f"{JUEJIN_API_BASE}/recommend_api/v1/article/recommend_cate_feed"
ARTICLE_DETAIL_URL = f"{JUEJIN_API_BASE}/content_api/v1/article/detail"
ARTICLE_QUERY_LIST_URL = f"{JUEJIN_API_BASE}/content_api/v1/article/query_list"
DRAFT_CREATE_URL = f"{JUEJIN_API_BASE}/content_api/v1/article_draft/create"
ARTICLE_PUBLISH_URL = f"{JUEJIN_API_BASE}/content_api/v1/article/publish"

# Cookie storage path
import os

COOKIE_FILE_PATH = os.path.expanduser("~/.juejin_cookie.json")

# Default request headers
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Origin": JUEJIN_WEB_URL,
    "Referer": f"{JUEJIN_WEB_URL}/",
}

# Sort types for article feeds
SORT_TYPE_HOT = 200        # Hot / recommended
SORT_TYPE_NEW = 300        # Newest
SORT_TYPE_THREE_DAY = 3    # 3-day hot
SORT_TYPE_WEEKLY = 7       # 7-day hot
SORT_TYPE_MONTHLY = 30     # 30-day hot
SORT_TYPE_HISTORY = 0      # All-time hot

# Default pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Common category IDs (for quick reference)
CATEGORY_MAP = {
    "backend": "6809637769959178254",
    "frontend": "6809637767543259144",
    "android": "6809635626879549454",
    "ios": "6809635626661445640",
    "ai": "6809637773935378440",
    "freebie": "6809637769764864014",
    "career": "6809637776263217160",
    "article": "6809637771511070734",
}
