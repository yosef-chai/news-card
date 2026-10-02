"""קבועים של News Card."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "news_card"

CONF_URL: Final = "url"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_MAX_ENTRIES: Final = "max_entries"
CONF_KEYWORDS: Final = "keywords"
CONF_PROXY_IMAGES: Final = "proxy_images"
CONF_PAGE_IMAGES: Final = "fetch_page_images"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_WITHIN: Final = "within"

# התראות (תתי-רשומות של פיד)
SUBENTRY_ALERT: Final = "alert"
ALERT_MODE_NEW: Final = "new_article"
ALERT_MODE_DAILY: Final = "daily"
CONF_MODE: Final = "mode"
CONF_NOTIFY: Final = "notify"
CONF_SPEAKERS: Final = "speakers"
CONF_TTS_ENGINE: Final = "tts_engine"
CONF_INCLUDE_SUMMARY: Final = "include_summary"
CONF_INCLUDE_IMAGE: Final = "include_image"
CONF_QUIET_START: Final = "speak_from"
CONF_QUIET_END: Final = "speak_until"
CONF_TIME: Final = "time"
CONF_WEEKDAYS: Final = "weekdays"
CONF_COUNT: Final = "count"
SPEECH_SUMMARY_MAX: Final = 700

DEFAULT_SCAN_INTERVAL: Final = 15  # דקות
DEFAULT_MAX_ENTRIES: Final = 30
MAX_ENTRIES_LIMIT: Final = 100

DEFAULT_OPTIONS: Final = {
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_MAX_ENTRIES: DEFAULT_MAX_ENTRIES,
    CONF_KEYWORDS: "",
    CONF_PROXY_IMAGES: True,
    CONF_PAGE_IMAGES: True,
    CONF_VERIFY_SSL: True,
}

EVENT_NEW_ARTICLE: Final = "news_card_new_article"
EVENT_TYPE_NEW: Final = "new_article"
EVENT_TYPE_KEYWORD: Final = "keyword_match"

SIGNAL_UPDATED: Final = "news_card_updated_{}"

FEED_MAX_BYTES: Final = 10 * 1024 * 1024
PAGE_MAX_BYTES: Final = 512 * 1024
IMAGE_MAX_BYTES: Final = 5 * 1024 * 1024
FETCH_TIMEOUT: Final = 20
PAGE_IMAGE_LOOKUPS_PER_REFRESH: Final = 15
PAGE_IMAGE_ATTEMPTS: Final = 3
MAX_EVENTS_PER_REFRESH: Final = 20
FAILURE_ISSUE_AFTER: Final = timedelta(hours=24)
SIGNED_PATH_TTL: Final = timedelta(days=1)

STATIC_URL: Final = "/news_card/frontend"
CARD_FILE: Final = "news-card.js"
IMAGE_PROXY_URL: Final = "/api/news_card/image/{entry_id}/{image_id}"

STORAGE_VERSION: Final = 1
STORE_ID_LIMIT: Final = 1000
