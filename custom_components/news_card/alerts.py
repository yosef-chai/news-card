"""שליחת חדשות לטלפון ולרמקולים: התראות שמוגדרות בממשק (תתי-רשומות של פיד) והפעולות send_to_phone ו-announce."""

from __future__ import annotations

from datetime import datetime, time
import logging
from typing import Any

import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util, slugify
from homeassistant.util.language import matches

from .const import (
    ALERT_MODE_DAILY,
    CONF_COUNT,
    CONF_INCLUDE_IMAGE,
    CONF_INCLUDE_SUMMARY,
    CONF_KEYWORDS,
    CONF_MODE,
    CONF_NOTIFY,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_SPEAKERS,
    CONF_TIME,
    CONF_TTS_ENGINE,
    CONF_WEEKDAYS,
    DOMAIN,
    SPEECH_SUMMARY_MAX,
    SUBENTRY_ALERT,
)
from .coordinator import NewsCardConfigEntry, NewsCardCoordinator, coordinators_for, match_keywords
from .feed import NewsEntry, truncate

_LOGGER = logging.getLogger(__name__)

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# פעם אחת לכל כתבה עד הסף; מעליו הודעה מרוכזת אחת, כדי לא להציף את הטלפון
MAX_SEPARATE_NOTIFICATIONS = 3


@callback
def async_setup_alerts(hass: HomeAssistant, entry: NewsCardConfigEntry) -> list[CALLBACK_TYPE]:
    """מפעיל את כל ההתראות של הפיד. מחזיר פונקציות ביטול."""
    coordinator = entry.runtime_data
    unsubs: list[CALLBACK_TYPE] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_ALERT:
            continue
        alert = FeedAlert(hass, coordinator, subentry.title, dict(subentry.data))
        if subentry.data[CONF_MODE] == ALERT_MODE_DAILY:
            at: time = dt_util.parse_time(subentry.data[CONF_TIME]) or time(9)
            unsubs.append(async_track_time_change(hass, alert.async_daily, at.hour, at.minute, at.second))
        else:
            unsubs.append(coordinator.async_add_listener(alert.async_on_update))
    return unsubs


def tts_language(hass: HomeAssistant, engine: str) -> str | None:
    """השפה של Home Assistant בניב שהמנוע תומך בו (למשל he → iw ב-Google Translate). None = ברירת המחדל של המנוע."""
    try:
        # ponytail: אין API ציבורי לשפות של מנוע; אם המודול ישתנה נופלים לשפת ברירת המחדל של המנוע
        from homeassistant.components.tts.helper import get_engine_instance  # noqa: PLC0415

        engine_instance = get_engine_instance(hass, engine)
        supported = list(engine_instance.supported_languages or []) if engine_instance else []
    except Exception:  # noqa: BLE001
        return None
    found = matches(hass.config.language, supported, hass.config.country)
    return found[0] if found else None


class FeedAlert:
    """התראה אחת: למי, מה ומתי."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: NewsCardCoordinator,
        title: str,
        config: dict[str, Any],
        *,
        raise_errors: bool = False,
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.title = title
        self.config = config
        self.raise_errors = raise_errors  # בפעולה שהמשתמש הריץ השגיאה מוצגת לו; בהתראה אוטומטית רק נרשמת ביומן
        self.keywords = [k.strip().casefold() for k in self.config.get(CONF_KEYWORDS, []) if k.strip()]

    @property
    def feed_title(self) -> str:
        return self.coordinator.config_entry.title

    @callback
    def async_on_update(self) -> None:
        """כתבות חדשות מהריענון האחרון."""
        data = self.coordinator.data
        articles = [e for e in (data.new_entries if data else []) if not self.keywords or match_keywords(e, self.keywords)]
        if articles:
            self.hass.async_create_task(self._async_deliver(list(reversed(articles)), speak=self._speaker_hours()))

    async def async_daily(self, now: datetime) -> None:
        """סיכום בשעה קבועה, רק בימים שנבחרו."""
        if WEEKDAYS[dt_util.as_local(now).weekday()] not in self.config.get(CONF_WEEKDAYS, WEEKDAYS):
            return
        data = self.coordinator.data
        articles = data.entries[: int(self.config.get(CONF_COUNT, 1))] if data else []
        if articles:
            await self._async_deliver(articles, speak=True)

    def _speaker_hours(self) -> bool:
        """האם עכשיו בשעות שבהן מותר להשמיע (גם טווח שעובר את חצות)."""
        start = dt_util.parse_time(self.config.get(CONF_QUIET_START) or "") or time(0)
        end = dt_util.parse_time(self.config.get(CONF_QUIET_END) or "") or time(23, 59, 59)
        now = dt_util.now().time()
        return start <= now <= end if start <= end else now >= start or now <= end

    async def async_send(self, articles: list[NewsEntry]) -> None:
        await self._async_deliver(articles, speak=True)

    async def _async_deliver(self, articles: list[NewsEntry], speak: bool) -> None:
        """שולח לכל היעדים. כשל ביעד אחד נרשם ביומן ולא עוצר את האחרים."""
        for target in self.config.get(CONF_NOTIFY, []):
            for title, message, article in self._notifications(articles):
                await self._async_call(self._notify_call(target, title, message, article))
        speakers = self.config.get(CONF_SPEAKERS, [])
        engine = self.config.get(CONF_TTS_ENGINE)
        if speak and speakers and engine:
            await self._async_call(
                (
                    "tts",
                    "speak",
                    {
                        ATTR_ENTITY_ID: engine,
                        "media_player_entity_id": speakers,
                        "message": self._speech(articles),
                        "cache": False,
                        **({"language": lang} if (lang := tts_language(self.hass, engine)) else {}),
                    },
                )
            )

    def _summary(self, article: NewsEntry, limit: int | None = None) -> str:
        if not self.config.get(CONF_INCLUDE_SUMMARY) or not article["summary"]:
            return ""
        return truncate(article["summary"], limit) if limit else article["summary"]

    def _notifications(self, articles: list[NewsEntry]) -> list[tuple[str, str, NewsEntry | None]]:
        """(כותרת, הודעה, כתבה) לכל הודעה שנשלחת."""
        if len(articles) <= MAX_SEPARATE_NOTIFICATIONS and (
            len(articles) == 1 or self.config[CONF_MODE] != ALERT_MODE_DAILY
        ):
            return [
                (a["source"] or self.feed_title, "\n\n".join(filter(None, [a["title"], self._summary(a)])), a)
                for a in articles
            ]
        return [(self.title, "\n".join(f"• {a['title']}" for a in articles), None)]

    def _notify_call(self, target: str, title: str, message: str, article: NewsEntry | None) -> tuple[str, str, dict]:
        """ישות notify (התראות מודרניות) או שירות notify (כמו אפליקציית הטלפון)."""
        if self.hass.states.get(target):
            return ("notify", "send_message", {ATTR_ENTITY_ID: target, "title": title, "message": message})
        service = target.removeprefix("notify.")
        data: dict[str, Any] = {"title": title, "message": message}
        if service.startswith("mobile_app_"):
            extra: dict[str, Any] = {"group": f"news_card_{self.coordinator.config_entry.entry_id}"}
            if article and article["link"]:
                extra |= {"url": article["link"], "clickAction": article["link"], "tag": article["id"]}
            if article and article["image"] and self.config.get(CONF_INCLUDE_IMAGE, True):
                extra["image"] = article["image"]
            data["data"] = extra
        return ("notify", service, data)

    def _speech(self, articles: list[NewsEntry]) -> str:
        if len(articles) == 1:
            article = articles[0]
            # שם הפיד רק אם הכותרת לא מתחילה בו כבר (למשל "תחזית כללית לרחבי ישראל עודכן ב-…")
            intro = None if article["title"].startswith(self.feed_title) else self.feed_title
            return ". ".join(filter(None, [intro, article["title"], self._summary(article, SPEECH_SUMMARY_MAX)]))
        return ". ".join([self.feed_title, *(a["title"] for a in articles)])

    async def _async_call(self, call: tuple[str, str, dict]) -> None:
        domain, service, data = call
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True)
        except Exception as err:  # noqa: BLE001 - יעד שנכשל (שירות שנמחק, נתונים לא תקינים) לא עוצר את האחרים
            if self.raise_errors:
                raise
            _LOGGER.warning("Alert %s: %s.%s failed: %s", self.title, domain, service, err)


# ---------- פעולות ----------

SERVICE_SEND_TO_PHONE = "send_to_phone"
SERVICE_ANNOUNCE = "announce"

_COMMON = {
    vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Optional(CONF_COUNT, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    vol.Optional(CONF_INCLUDE_SUMMARY, default=False): cv.boolean,
    vol.Optional("keyword"): cv.string,
}
SEND_TO_PHONE_SCHEMA = vol.Schema(
    {
        **_COMMON,
        vol.Required("phones"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_INCLUDE_IMAGE, default=True): cv.boolean,
    }
)
ANNOUNCE_SCHEMA = vol.Schema(
    {**_COMMON, vol.Required(CONF_SPEAKERS): cv.entity_ids, vol.Optional(CONF_TTS_ENGINE): cv.entity_id}
)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, SERVICE_SEND_TO_PHONE, _async_send_to_phone, schema=SEND_TO_PHONE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ANNOUNCE, _async_announce, schema=ANNOUNCE_SCHEMA)


def phone_targets(hass: HomeAssistant, device_ids: list[str]) -> list[str]:
    """טלפון (מכשיר של אפליקציית Home Assistant) ← יעד notify.

    השירות של האפליקציה תומך בתמונה ובקישור; אם אין כזה, ישות ה-notify של אותו מכשיר.
    """
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    targets: list[str] = []
    for device_id in device_ids:
        device = devices.async_get(device_id)
        # ponytail: config_entry_id יחיד מ-2026.8; config_entries ישן נשאר לגרסאות קודמות
        entry_ids = [device.config_entry_id] if device and getattr(device, "config_entry_id", None) else list(getattr(device, "config_entries", []))
        app = next(
            (e for i in entry_ids if (e := hass.config_entries.async_get_entry(i)) and e.domain == "mobile_app"), None
        )
        if app is None or device is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="phone_not_found", translation_placeholders={"device": device_id}
            )
        service = f"mobile_app_{slugify(app.data.get('device_name') or app.title)}"
        if hass.services.has_service("notify", service):
            targets.append(f"notify.{service}")
        elif notify := next((e.entity_id for e in er.async_entries_for_device(entities, device.id) if e.domain == "notify"), None):
            targets.append(notify)
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="phone_not_found",
                translation_placeholders={"device": device.name_by_user or device.name or device_id},
            )
    return targets


async def _async_send(call: ServiceCall, config: dict[str, Any]) -> None:
    """הכתבות האחרונות מכל פיד (אפשר לסנן במילה), דרך אותו מנגנון של ההתראות."""
    keyword = call.data.get("keyword", "").strip().casefold()
    for coordinator in dict.fromkeys(coordinators_for(call.hass, call.data[ATTR_ENTITY_ID]).values()):
        articles = [e for e in coordinator.data.entries if not keyword or match_keywords(e, [keyword])]
        if articles := articles[: call.data[CONF_COUNT]]:
            title = coordinator.config_entry.title
            await FeedAlert(call.hass, coordinator, title, config, raise_errors=True).async_send(articles)


async def _async_send_to_phone(call: ServiceCall) -> None:
    config = {
        CONF_MODE: ALERT_MODE_DAILY,  # כמה כתבות = הודעה מרוכזת אחת
        CONF_NOTIFY: phone_targets(call.hass, call.data["phones"]),
        CONF_INCLUDE_SUMMARY: call.data[CONF_INCLUDE_SUMMARY],
        CONF_INCLUDE_IMAGE: call.data[CONF_INCLUDE_IMAGE],
    }
    await _async_send(call, config)


async def _async_announce(call: ServiceCall) -> None:
    engine = call.data.get(CONF_TTS_ENGINE) or default_tts_engine(call.hass)
    if not engine:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="tts_required")
    config = {
        CONF_MODE: ALERT_MODE_DAILY,
        CONF_SPEAKERS: call.data[CONF_SPEAKERS],
        CONF_TTS_ENGINE: engine,
        CONF_INCLUDE_SUMMARY: call.data[CONF_INCLUDE_SUMMARY],
    }
    await _async_send(call, config)


def default_tts_engine(hass: HomeAssistant) -> str | None:
    """מנוע ההקראה המועדף, אם רכיב ההקראה טעון (הוא לא תלות חובה)."""
    if "tts" not in hass.config.components:
        return None
    from homeassistant.components import tts  # noqa: PLC0415

    engine = tts.async_default_engine(hass)
    return engine if engine and engine.startswith("tts.") else None
