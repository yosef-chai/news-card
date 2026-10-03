"""מתאם עדכונים: הורדה, ניתוח, העשרת תמונות, זיהוי פריטים חדשים ושמירה מתמשכת."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any, override
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.target import TargetSelection, async_extract_referenced_entity_ids
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import FALLBACK_REASONS, FetchError, FetchResult, async_fetch, find_page_image, resolve_user_agent
from .const import (
    CONF_KEYWORDS,
    CONF_MAX_ENTRIES,
    CONF_PAGE_IMAGES,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_USER_AGENT,
    CONF_VERIFY_SSL,
    DEFAULT_OPTIONS,
    DOMAIN,
    EVENT_NEW_ARTICLE,
    FAILURE_ISSUE_AFTER,
    FALLBACK_STICKY,
    FEED_MAX_BYTES,
    MAX_EVENTS_PER_REFRESH,
    PAGE_IMAGE_ATTEMPTS,
    PAGE_IMAGE_LOOKUPS_PER_REFRESH,
    PAGE_MAX_BYTES,
    SIGNAL_UPDATED,
    STORAGE_VERSION,
    STORE_ID_LIMIT,
)
from .feed import FeedError, FeedInfo, NewsEntry, abs_url, apply_first_seen, parse_feed

_LOGGER = logging.getLogger(__name__)

# אתרים שהקישור אצלם הוא דף הפניה, ולכן אין בו תמונת כתבה
NO_PAGE_IMAGE_HOSTS = ("news.google.com",)

# שגיאות שלא עוברות מעצמן: תקלה בהגדרות מוצגת מיד ולא אחרי יממה
PERMANENT_ERRORS = ("not_found", "blocked", "refused", "auth_required")
BACKOFF_MAX = timedelta(hours=1)

type NewsCardConfigEntry = ConfigEntry[NewsCardCoordinator]


@dataclass
class NewsFeedData:
    """הנתונים של פיד אחד."""

    info: FeedInfo
    entries: list[NewsEntry]
    last_success: str | None = None
    new_entries: list[NewsEntry] = field(default_factory=list)


def parse_keywords(raw: str) -> list[str]:
    """מילות מפתח מופרדות בפסיק או בשורה חדשה."""
    return [k.strip().casefold() for k in raw.replace("\n", ",").split(",") if k.strip()]


def match_keywords(entry: Mapping[str, Any], keywords: list[str]) -> list[str]:
    """מילות המפתח שמופיעות בכותרת או בתקציר."""
    text = f"{entry['title']} {entry['summary']}".casefold()
    return [k for k in keywords if k in text]


class NewsCardCoordinator(DataUpdateCoordinator[NewsFeedData]):
    """מנהל פיד אחד."""

    config_entry: NewsCardConfigEntry

    def __init__(self, hass: HomeAssistant, entry: NewsCardConfigEntry) -> None:
        options = {**DEFAULT_OPTIONS, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=options[CONF_SCAN_INTERVAL]),
        )
        self.url: str = entry.data[CONF_URL]
        self.options = options
        self.keywords = parse_keywords(options[CONF_KEYWORDS])
        self.session = async_get_clientsession(hass, verify_ssl=options[CONF_VERIFY_SSL])
        self.last_error: str | None = None
        self.last_status: int | None = None
        self._first_failure: datetime | None = None
        self._failures = 0
        self.user_agent = resolve_user_agent(options[CONF_USER_AGENT])
        self._fallback_until: datetime | None = None
        self._base_interval = timedelta(minutes=options[CONF_SCAN_INTERVAL])
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._etag: str | None = None
        self._modified: str | None = None
        self._first_seen: dict[str, str] = {}
        self._announced: dict[str, None] = {}  # dict לשמירת סדר הכנסה
        self._page_images: dict[str, str] = {}
        self._page_attempts: dict[str, int] = {}
        self._read: dict[str, None] = {}
        self._seeded = False

    @property
    def issue_id(self) -> str:
        return f"feed_unreachable_{self.config_entry.entry_id}"

    async def async_load(self) -> bool:
        """טעינת מצב שמור. מחזיר True אם יש עותק אחרון של הנתונים."""
        stored = await self._store.async_load() or {}
        self._first_seen = stored.get("first_seen", {})
        self._announced = dict.fromkeys(stored.get("announced", []))
        self._page_images = stored.get("page_images", {})
        self._read = dict.fromkeys(stored.get("read", []))
        self._seeded = bool(stored.get("seeded"))
        cached = stored.get("cache")
        if cached and cached.get("url") == self.url:
            self._etag = stored.get("etag")
            self._modified = stored.get("modified")
            self.data = NewsFeedData(cached["info"], cached["entries"], cached.get("last_success"))
            return True
        return False

    @callback
    def _store_payload(self) -> dict[str, Any]:
        data = self.data
        return {
            "first_seen": dict(list(self._first_seen.items())[-STORE_ID_LIMIT:]),
            "announced": list(self._announced)[-STORE_ID_LIMIT:],
            "page_images": dict(list(self._page_images.items())[-STORE_ID_LIMIT:]),
            "read": list(self._read)[-STORE_ID_LIMIT:],
            "seeded": self._seeded,
            "etag": self._etag,
            "modified": self._modified,
            "cache": {
                "url": self.url,
                "info": data.info,
                "entries": data.entries,
                "last_success": data.last_success,
            }
            if data
            else None,
        }

    @override
    async def _async_update_data(self) -> NewsFeedData:
        try:
            # ponytail: פיד מעל התקרה (פודקאסט של 20MB) נחתך, ו-feedparser קורא את הפריטים השלמים.
            # פיד ענק שמסודר מהישן לחדש יציג פריטים ישנים; אם זה קורה, לקרוא את סוף הקובץ (Range)
            result = await self._async_fetch_feed(
                max_bytes=FEED_MAX_BYTES,
                etag=self._etag if self.data else None,
                modified=self._modified if self.data else None,
                truncate=True,
            )
        except FetchError as err:
            self._handle_failure(err.reason, err.status, err.retry_after)
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"url": self.url, "error": str(err)},
            ) from err

        now = dt_util.utcnow()
        self.last_status = result.status
        if result.content is None and self.data:  # 304: לא השתנה
            self._handle_success()
            data = NewsFeedData(self.data.info, self.data.entries, now.isoformat())
            self._schedule_save()
            return data

        try:
            parsed = await self.hass.async_add_executor_job(
                parse_feed,
                result.content or b"",
                result.url,
                result.content_type,
                self.options[CONF_MAX_ENTRIES],
                result.charset,
            )
        except FeedError as err:
            self._handle_failure(err.reason, None)
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"url": self.url, "error": err.reason},
            ) from err

        self._etag, self._modified = result.etag, result.modified
        apply_first_seen(parsed.entries, self._first_seen, now)
        if self.options[CONF_PAGE_IMAGES]:
            await self._enrich_images(parsed.entries, parsed.info)
        new_entries = self._detect_new(parsed.entries)
        self._handle_success()
        data = NewsFeedData(parsed.info, parsed.entries, now.isoformat(), new_entries)
        self._schedule_save()
        return data

    @property
    def fallback_active(self) -> bool:
        """האתר סירב ל-User-Agent הרגיל, ועכשיו משתמשים בזה שבהגדרות."""
        return bool(self.user_agent and self._fallback_until and dt_util.utcnow() < self._fallback_until)

    async def _async_fetch_feed(self, **kwargs: Any) -> FetchResult:
        """הורדה רגילה. רק אם האתר מסרב לה, ניסיון חוזר עם ה-User-Agent מההגדרות."""
        if self.fallback_active:
            try:
                return await async_fetch(self.session, self.url, user_agent=self.user_agent, **kwargs)
            except FetchError as err:
                if err.reason in FALLBACK_REASONS:
                    self._fallback_until = None  # גם החלופי נדחה; בפעם הבאה מתחילים שוב מהרגיל
                raise
        try:
            return await async_fetch(self.session, self.url, **kwargs)
        except FetchError as err:
            if not self.user_agent or err.reason not in FALLBACK_REASONS:
                raise
            _LOGGER.debug("%s refused the default User-Agent (%s), retrying with the configured one", self.url, err)
        result = await async_fetch(self.session, self.url, user_agent=self.user_agent, **kwargs)
        if not self._fallback_until:
            _LOGGER.info("%s accepts only the configured User-Agent; using it for the next %s", self.url, FALLBACK_STICKY)
        self._fallback_until = dt_util.utcnow() + FALLBACK_STICKY
        return result

    def _detect_new(self, entries: list[NewsEntry]) -> list[NewsEntry]:
        """פריטים שלא הוכרזו. בריענון הראשון אי פעם רק מסמנים, בלי אירועים."""
        fresh = [e for e in entries if e["id"] not in self._announced]
        if self.data and fresh:
            # הגדלת max_entries חושפת פריטים ישנים; לא מכריזים על מה שישן מהחדש שהכרנו
            # ponytail: סף 6 שעות לפני הפריט החדש ביותר הקודם, מספיק לפידים שמתעדכנים באיחור
            known = [e["published"] for e in self.data.entries if e["published"]]
            if known:
                floor = (dt_util.parse_datetime(max(known)) or dt_util.utcnow()) - timedelta(hours=6)
                fresh = [
                    e
                    for e in fresh
                    if e["published_estimated"]
                    or (dt_util.parse_datetime(e["published"] or "") or floor) >= floor
                ]
        for entry in entries:
            self._announced[entry["id"]] = None
        if not self._seeded:
            self._seeded = True
            return []
        return list(reversed(fresh[:MAX_EVENTS_PER_REFRESH]))  # מהישן לחדש

    async def _enrich_images(self, entries: list[NewsEntry], info: FeedInfo) -> None:
        """תמונה מדף הכתבה (og:image) לפריטים בלי תמונה.

        כשל רשת או דף בלי תמונה (כתבה טרייה שהתמונה שלה עוד לא עלתה) נבדקים שוב
        בריענונים הבאים, עד PAGE_IMAGE_ATTEMPTS פעמים, ורק אז נשמרים כ"אין תמונה".
        """
        for entry in entries:
            if not entry["image"] and self._page_images.get(entry["id"]):
                entry["image"] = self._page_images[entry["id"]]
        todo = [
            e
            for e in entries
            if not e["image"]
            and e["id"] not in self._page_images
            and e["link"]
            and e["link"] != info["link"]
            and not urlparse(e["link"]).netloc.endswith(NO_PAGE_IMAGE_HOSTS)
        ][:PAGE_IMAGE_LOOKUPS_PER_REFRESH]
        if not todo:
            return
        sem = asyncio.Semaphore(4)

        async def lookup(entry: NewsEntry) -> None:
            async with sem:
                try:
                    page = await async_fetch(
                        self.session,
                        entry["link"] or "",
                        max_bytes=PAGE_MAX_BYTES,
                        accept="text/html,application/xhtml+xml",
                        truncate=True,
                        timeout=10,
                        # דפי הכתבות באותו אתר: רק כשכבר ידוע שהרגיל נדחה, בלי בקשה כפולה לכל דף
                        user_agent=self.user_agent if self.fallback_active else None,
                    )
                except FetchError as err:
                    _LOGGER.debug("Page image lookup failed for %s: %s", entry["link"], err)
                    self._give_up_page_image(entry["id"])
                    return
                html = (page.content or b"").decode("utf-8", "replace")
                found = find_page_image(html)
                image = abs_url(found, page.url) if found else None
                if image and image != info["icon"]:
                    entry["image"] = image
                    self._page_images[entry["id"]] = image
                    self._page_attempts.pop(entry["id"], None)
                else:
                    self._give_up_page_image(entry["id"])

        await asyncio.gather(*(lookup(e) for e in todo))

    def _give_up_page_image(self, entry_id: str) -> None:
        """סופר ניסיון כושל; אחרי PAGE_IMAGE_ATTEMPTS מפסיקים לחפש."""
        attempts = self._page_attempts.get(entry_id, 0) + 1
        self._page_attempts[entry_id] = attempts
        if attempts >= PAGE_IMAGE_ATTEMPTS:
            self._page_images[entry_id] = ""
            self._page_attempts.pop(entry_id, None)

    @callback
    def _handle_success(self) -> None:
        self.last_error = None
        self._first_failure = None
        self._failures = 0
        self.update_interval = self._base_interval
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)

    @callback
    def _handle_failure(self, reason: str, status: int | None, retry_after: int | None = None) -> None:
        """רושם כשל ומאט: כל כשל רצוף מכפיל את ההמתנה (עד שעה), ו-Retry-After של השרת גובר."""
        self.last_error = reason
        self.last_status = status
        self._failures += 1
        backoff = min(self._base_interval * 2 ** (self._failures - 1), max(self._base_interval, BACKOFF_MAX))
        self.update_interval = max(backoff, timedelta(seconds=retry_after or 0))
        now = dt_util.utcnow()
        self._first_failure = self._first_failure or now
        # כתובת שנמחקה או אתר שחוסם לא יסתדרו לבד, אז מודיעים מיד
        if reason in PERMANENT_ERRORS or now - self._first_failure >= FAILURE_ISSUE_AFTER:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self.issue_id,
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key={"blocked": "feed_blocked", "refused": "feed_refused", "auth_required": "feed_blocked"}.get(
                    reason, "feed_unreachable"
                ),
                translation_placeholders={"title": self.config_entry.title, "url": self.url, "status": str(status or "")},
                data={"entry_id": self.config_entry.entry_id, "reason": reason},
            )

    def is_read(self, entry_id: str) -> bool:
        return entry_id in self._read

    @property
    def unread_count(self) -> int:
        return sum(e["id"] not in self._read for e in self.data.entries) if self.data else 0

    @property
    def newest_published(self) -> datetime | None:
        """זמן הפרסום של הכתבה החדשה ביותר בפיד."""
        times = [t for e in (self.data.entries if self.data else []) if (t := dt_util.parse_datetime(e["published"] or ""))]
        return max(times, default=None)

    @callback
    def async_mark_read(self, entry_ids: list[str] | None, read: bool = True) -> None:
        """סימון כתבות כנקראו (או לא). None = כל הכתבות בפיד."""
        ids = entry_ids if entry_ids is not None else [e["id"] for e in self.data.entries] if self.data else []
        for entry_id in ids:
            if read:
                self._read.pop(entry_id, None)  # הזזה לסוף, כדי שהחיתוך ישמור את האחרונים
                self._read[entry_id] = None
            else:
                self._read.pop(entry_id, None)
        if self.data:
            # הכתבות החדשות כבר הוכרזו; בלי זה המאזינים היו מכריזים עליהן שוב
            self.data.new_entries = []
        self._schedule_save()
        self.async_update_listeners()

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._store_payload, 30)

    @override
    async def async_shutdown(self) -> None:
        """שמירה מיידית בפריקה."""
        await super().async_shutdown()
        if self.data:
            await self._store.async_save(self._store_payload())

    @callback
    def async_notify(self) -> None:
        """הודעה למנויי WebSocket ושליחת אירועי bus לפריטים חדשים."""
        async_dispatcher_send(self.hass, SIGNAL_UPDATED.format(self.config_entry.entry_id))

    @callback
    def fire_bus_events(self, event_entity_id: str | None) -> None:
        """אירוע news_card_new_article לכל פריט חדש."""
        if not self.data:
            return
        for entry in self.data.new_entries:
            self.hass.bus.async_fire(
                EVENT_NEW_ARTICLE,
                {
                    **entry,
                    "entity_id": event_entity_id,
                    "config_entry_id": self.config_entry.entry_id,
                    "feed_title": self.data.info["title"],
                    "feed_url": self.url,
                    "matched_keywords": match_keywords(entry, self.keywords),
                },
            )


@callback
def coordinators_for(hass: HomeAssistant, entity_ids: list[str]) -> dict[str, NewsCardCoordinator]:
    """ממפה ישויות news_card למתאם שלהן. זורק שגיאה מתורגמת על ישות לא תקינה."""
    registry = er.async_get(hass)
    result: dict[str, NewsCardCoordinator] = {}
    for entity_id in entity_ids:
        reg = registry.async_get(entity_id)
        if reg is None or reg.platform != DOMAIN or not reg.config_entry_id:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entity_not_found",
                translation_placeholders={"entity_id": entity_id},
            )
        entry = hass.config_entries.async_get_entry(reg.config_entry_id)
        coordinator = getattr(entry, "runtime_data", None) if entry else None
        if not isinstance(coordinator, NewsCardCoordinator) or coordinator.data is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"entity_id": entity_id},
            )
        result[entity_id] = coordinator
    return result


@callback
def entry_ids_for_target(hass: HomeAssistant, target: dict[str, Any]) -> list[str]:
    """הפידים (config entries) שיעד של טריגר או תנאי מצביע עליהם: ישויות, מכשירים, אזורים או תוויות."""
    selected = async_extract_referenced_entity_ids(hass, TargetSelection(target))
    registry = er.async_get(hass)
    ids: dict[str, None] = {}
    for entity_id in sorted(selected.referenced | selected.indirectly_referenced):
        if (reg := registry.async_get(entity_id)) and reg.platform == DOMAIN and reg.config_entry_id:
            ids[reg.config_entry_id] = None
    return list(ids)


@callback
def loaded_coordinator(hass: HomeAssistant, entry_id: str) -> NewsCardCoordinator | None:
    """המתאם של פיד טעון שיש לו נתונים, או None."""
    entry = hass.config_entries.async_get_entry(entry_id)
    coordinator = getattr(entry, "runtime_data", None) if entry else None
    return coordinator if isinstance(coordinator, NewsCardCoordinator) and coordinator.data else None
