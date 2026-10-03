"""זרימת הגדרה: הוספה, גילוי פידים בדף HTML, הגדרה מחדש ואפשרויות."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, override
from urllib.parse import urljoin, urlparse, urlunparse

import probatio as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)
from homeassistant.util import slugify

from .alerts import default_tts_engine
from .client import (
    FALLBACK_REASONS,
    USER_AGENT_BROWSER,
    FetchError,
    FetchResult,
    async_fetch,
    resolve_user_agent,
    valid_user_agent,
)
from .const import (
    ALERT_MODE_DAILY,
    ALERT_MODE_NEW,
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
    CONF_MAX_ENTRIES,
    CONF_PAGE_IMAGES,
    CONF_PROXY_IMAGES,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_USER_AGENT,
    CONF_VERIFY_SSL,
    DEFAULT_OPTIONS,
    DOMAIN,
    FEED_MAX_BYTES,
    FETCH_TIMEOUT,
    MAX_ENTRIES_LIMIT,
    SUBENTRY_ALERT,
)
from .feed import FeedError, parse_feed

FEEDREADER_DOMAIN = "feedreader"
COMMON_FEED_PATHS = ("feed", "rss", "feed.xml", "rss.xml", "atom.xml", "index.xml", "feed.json")
PROBE_TIMEOUT = 10


class FeedValidationError(Exception):
    """שגיאת אימות עם מפתח תרגום ופידים שהתגלו."""

    def __init__(self, reason: str, discovered: list[tuple[str, str]] | None = None, status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.discovered = discovered or []
        self.status = status


def normalize_url(url: str) -> str:
    """כתובת קנונית ל-unique_id: סכמה ומארח באותיות קטנות, בלי '/' בסוף."""
    url = url.strip()
    if "://" not in url:
        url = f"https://{url}"
    parts = urlparse(url)
    path = parts.path.rstrip("/") or ""
    return urlunparse((parts.scheme.lower(), parts.netloc.lower(), path, parts.params, parts.query, ""))


type Fetch = Callable[..., Awaitable[FetchResult]]


def _fetcher(session: Any, user_agent: str | None) -> Fetch:
    """הורדה כמו במתאם: קודם רגילה, ורק אם האתר מסרב, שוב עם ה-User-Agent מההגדרות."""
    fallback = resolve_user_agent(user_agent)

    async def fetch(url: str, **kwargs: Any) -> FetchResult:
        try:
            return await async_fetch(session, url, **kwargs)
        except FetchError as err:
            if not fallback or err.reason not in FALLBACK_REASONS:
                raise
        return await async_fetch(session, url, user_agent=fallback, **kwargs)

    return fetch


async def _async_check_feed(hass: HomeAssistant, fetch: Fetch, url: str, timeout: float = FETCH_TIMEOUT) -> tuple[str, str]:
    """מוריד ומנתח. מחזיר (כתובת סופית, כותרת). זורק FetchError / FeedError."""
    result = await fetch(url, max_bytes=FEED_MAX_BYTES, timeout=timeout, truncate=True)
    parsed = await hass.async_add_executor_job(
        parse_feed, result.content or b"", result.url, result.content_type, 1, result.charset
    )
    return result.url, parsed.info["title"]


async def _async_probe_paths(hass: HomeAssistant, fetch: Fetch, page_url: str) -> list[tuple[str, str]]:
    """פידים בנתיבים המקובלים (WordPress, Ghost, Hugo, Jekyll), לאתר שלא מצהיר על פיד בדף."""
    parts = urlparse(page_url)
    bases = dict.fromkeys((urljoin(page_url, "."), f"{parts.scheme}://{parts.netloc}/"))
    candidates = dict.fromkeys(urljoin(base, path) for base in bases for path in COMMON_FEED_PATHS)

    async def check(url: str) -> tuple[str, str] | None:
        try:
            return await _async_check_feed(hass, fetch, url, PROBE_TIMEOUT)
        except (FetchError, FeedError):
            return None

    hits: dict[str, str] = {}
    for hit in await asyncio.gather(*(check(url) for url in candidates)):
        if hit:
            hits.setdefault(*hit)
    return list(hits.items())


async def async_validate_feed(
    hass: HomeAssistant, url: str, verify_ssl: bool = True, probe: bool = True, user_agent: str | None = None
) -> tuple[str, str]:
    """מוריד ומנתח. מחזיר (כתובת סופית, כותרת הפיד).

    דף אתר בלי פיד מוצהר: הקישורים בדף שנראים כמו פיד, ועם probe גם פידים בנתיבים מקובלים באתר.
    """
    parts = urlparse(url if "://" in url else f"https://{url}")
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise FeedValidationError("invalid_url")
    url = parts.geturl()
    fetch = _fetcher(async_get_clientsession(hass, verify_ssl=verify_ssl), user_agent)
    try:
        return await _async_check_feed(hass, fetch, url)
    except FetchError as err:
        found = []
        if probe and err.reason == "not_found":
            # פיד שעבר כתובת: מחפשים את הפידים הנוכחיים בדף הבית של האתר
            home = f"{parts.scheme}://{parts.netloc}/"
            try:
                found = [await _async_check_feed(hass, fetch, home)]
            except FetchError:
                pass
            except FeedError as page:
                # האתר עוד מצהיר לפעמים על הכתובת השבורה
                found = [f for f in await _async_found(hass, fetch, home, page, probe) if f[0] != url]
        raise FeedValidationError(err.reason, found, err.status) from err
    except FeedError as err:
        raise FeedValidationError(err.reason, await _async_found(hass, fetch, url, err, probe)) from err


async def _async_found(hass: HomeAssistant, fetch: Fetch, url: str, err: FeedError, probe: bool) -> list[tuple[str, str]]:
    """הפידים שמוצעים לדף שאינו פיד: המוצהרים, ואם אין, נתיבים מקובלים וקישורים בדף."""
    if not probe or err.reason != "not_a_feed" or err.discovered:
        return err.discovered or err.links
    probed = await _async_probe_paths(hass, fetch, url)
    return probed + [link for link in err.links if link[0] not in dict(probed)]


def _feedreader_urls(hass: HomeAssistant) -> list[str]:
    return sorted(
        {
            e.data[CONF_URL]
            for e in hass.config_entries.async_entries(FEEDREADER_DOMAIN)
            if e.data.get(CONF_URL)
        }
    )


def _url_selector(hass: HomeAssistant) -> Any:
    """בורר כתובת. אם יש פידים ב-Feedreader, הם מוצעים לבחירה (ואפשר להקליד כתובת אחרת)."""
    if urls := _feedreader_urls(hass):
        return SelectSelector(
            SelectSelectorConfig(options=urls, custom_value=True, mode=SelectSelectorMode.DROPDOWN)
        )
    return TextSelector(TextSelectorConfig(type=TextSelectorType.URL))


def user_agent_selector() -> SelectSelector:
    """דפדפן מהרשימה, או כל טקסט אחר. נשלח רק כשהבקשה הרגילה נדחית."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[USER_AGENT_BROWSER], custom_value=True, mode=SelectSelectorMode.DROPDOWN, translation_key=CONF_USER_AGENT
        )
    )


def _error_placeholders(err: FeedValidationError) -> dict[str, str]:
    return {"status": str(err.status or "")}


class NewsCardConfigFlow(ConfigFlow, domain=DOMAIN):
    """הוספת פיד."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: list[tuple[str, str]] = []
        self._verify_ssl = True
        self._user_agent = ""
        self._url = ""
        self._status = ""

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"status": ""}
        example = {"example": "https://www.example.com/feed"}
        if user_input is not None:
            self._verify_ssl = user_input.get(CONF_VERIFY_SSL, True)
            self._user_agent = ""
            try:
                return await self._async_create(user_input[CONF_URL])
            except FeedValidationError as err:
                if err.discovered:
                    return await self._async_show_found(err)
                if err.reason in FALLBACK_REASONS:
                    # האתר מסרב לקורא פידים; מציעים לנסות עם User-Agent אחר
                    self._url, self._status = user_input[CONF_URL], str(err.status or "")
                    return await self.async_step_user_agent()
                errors["base"] = err.reason
                placeholders = _error_placeholders(err)
        placeholders |= example

        schema = vol.Schema(
            {
                vol.Required(CONF_URL): _url_selector(self.hass),
                vol.Optional(CONF_VERIFY_SSL, default=True): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _async_show_found(self, err: FeedValidationError) -> ConfigFlowResult:
        self._discovered = err.discovered
        return await (self.async_step_moved() if err.reason == "not_found" else self.async_step_select_feed())

    async def async_step_user_agent(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """האתר סירב: ניסיון חוזר עם User-Agent של דפדפן או אחר, שיישמר בהגדרות הפיד."""
        errors: dict[str, str] = {}
        placeholders = {"host": urlparse(normalize_url(self._url)).netloc, "status": self._status}
        if user_input is not None:
            option = (user_input.get(CONF_USER_AGENT) or "").strip()
            if not option or not valid_user_agent(option):
                errors[CONF_USER_AGENT] = "invalid_user_agent"
            else:
                self._user_agent = option
                try:
                    return await self._async_create(self._url)
                except FeedValidationError as err:
                    if err.discovered:
                        return await self._async_show_found(err)
                    errors["base"] = "still_refused" if err.reason in (*FALLBACK_REASONS, "blocked") else err.reason
                    placeholders["status"] = str(err.status or "")
        return self.async_show_form(
            step_id="user_agent",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_USER_AGENT): user_agent_selector()}),
                user_input or {CONF_USER_AGENT: self._user_agent or USER_AGENT_BROWSER},
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_moved(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """הפיד לא קיים יותר בכתובת: בחירה מתוך הפידים שנמצאו בדף הבית."""
        return await self.async_step_select_feed(user_input, "moved")

    async def async_step_select_feed(
        self, user_input: dict[str, Any] | None = None, step_id: str = "select_feed"
    ) -> ConfigFlowResult:
        """הכתובת היא דף אתר: בחירה מתוך הפידים שנמצאו בו ובאתר."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"status": ""}
        if user_input is not None:
            try:
                return await self._async_create(user_input[CONF_URL], probe=False)
            except FeedValidationError as err:
                if err.discovered:
                    # נבחר דף אינדקס של פידים (למשל "RSS" באתר חדשות): מציגים את הפידים שבו
                    self._discovered = err.discovered
                else:
                    errors["base"] = err.reason
                    placeholders = _error_placeholders(err)
        options = [SelectOptionDict(value=url, label=f"{title} — {url}" if title != url else url) for url, title in self._discovered]
        mode = SelectSelectorMode.LIST if len(options) <= 10 else SelectSelectorMode.DROPDOWN
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=self._discovered[0][0]): SelectSelector(
                        SelectSelectorConfig(options=options, mode=mode)
                    )
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _async_create(self, url: str, probe: bool = True) -> ConfigFlowResult:
        await self.async_set_unique_id(normalize_url(url))
        self._abort_if_unique_id_configured()
        final_url, title = await async_validate_feed(self.hass, url, self._verify_ssl, probe, self._user_agent)
        if normalize_url(final_url) != self.unique_id:
            await self.async_set_unique_id(normalize_url(final_url))
            self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=title,
            data={CONF_URL: final_url},
            options={**DEFAULT_OPTIONS, CONF_VERIFY_SSL: self._verify_ssl, CONF_USER_AGENT: self._user_agent},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """החלפת כתובת הפיד."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"status": ""}
        if user_input is not None:
            verify = entry.options.get(CONF_VERIFY_SSL, True)
            try:
                final_url, _ = await async_validate_feed(
                    self.hass, user_input[CONF_URL], verify, probe=False, user_agent=entry.options.get(CONF_USER_AGENT)
                )
            except FeedValidationError as err:
                errors["base"] = err.reason
                placeholders = _error_placeholders(err)
            else:
                unique_id = normalize_url(final_url)
                if any(
                    e.unique_id == unique_id and e.entry_id != entry.entry_id
                    for e in self._async_current_entries(include_ignore=False)
                ):
                    return self.async_abort(reason="already_configured")
                # מאזין העדכונים של הרשומה טוען אותה מחדש
                return self.async_update_and_abort(entry, unique_id=unique_id, data_updates={CONF_URL: final_url})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_URL, default=entry.data[CONF_URL]): _url_selector(self.hass)}
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    @override
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NewsCardOptionsFlow:
        return NewsCardOptionsFlow()

    @override
    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_ALERT: AlertSubentryFlow}


class NewsCardOptionsFlow(OptionsFlow):
    """אפשרויות פיד."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            # שדה שנוקה לא מגיע בכלל
            user_agent = (user_input.get(CONF_USER_AGENT) or "").strip()
            if valid_user_agent(user_agent):
                return self.async_create_entry(
                    data={
                        **user_input,
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_MAX_ENTRIES: int(user_input[CONF_MAX_ENTRIES]),
                        CONF_KEYWORDS: user_input.get(CONF_KEYWORDS, ""),
                        CONF_USER_AGENT: user_agent,
                    }
                )
            errors[CONF_USER_AGENT] = "invalid_user_agent"
        current = {**DEFAULT_OPTIONS, **self.config_entry.options, **(user_input or {})}
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(min=5, max=1440, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="min")
                ),
                vol.Required(CONF_MAX_ENTRIES): NumberSelector(
                    NumberSelectorConfig(min=1, max=MAX_ENTRIES_LIMIT, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_KEYWORDS): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Required(CONF_PROXY_IMAGES): BooleanSelector(),
                vol.Required(CONF_PAGE_IMAGES): BooleanSelector(),
                vol.Required(CONF_VERIFY_SSL): BooleanSelector(),
                vol.Optional(CONF_USER_AGENT): user_agent_selector(),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=self.add_suggested_values_to_schema(schema, current), errors=errors
        )


WEEKDAY_OPTIONS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
NOTIFY_SKIP = ("notify", "send_message")
_MAIN_FIELDS = ("mode", "notify", "speakers", "tts_engine", "include_summary", "include_image")
_STEP_FIELDS = ("keywords", "speak_from", "speak_until", "time", "weekdays", "count")


def notify_target_options(hass: HomeAssistant) -> list[SelectOptionDict]:
    """יעדי התראה: אפליקציות טלפון ושירותי notify אחרים, וישויות notify."""
    phones = {
        f"mobile_app_{slugify(name)}": name
        for e in hass.config_entries.async_entries("mobile_app")
        if (name := e.data.get("device_name") or e.title)
    }
    options = [
        SelectOptionDict(value=f"notify.{service}", label=phones.get(service, service.replace("_", " ")))
        for service in sorted(hass.services.async_services_for_domain("notify"))
        if service not in NOTIFY_SKIP
    ]
    # טלפון של האפליקציה מופיע גם כישות notify; משאירים את השירות, שתומך בתמונה ובקישור
    registry = er.async_get(hass)
    options += [
        SelectOptionDict(value=s.entity_id, label=s.name)
        for s in hass.states.async_all("notify")
        if not ((reg := registry.async_get(s.entity_id)) and reg.platform == "mobile_app")
    ]
    return options


class AlertSubentryFlow(ConfigSubentryFlow):
    """התראה לפיד: למי (טלפון, רמקולים), מתי (כל כתבה חדשה או בשעה קבועה) ומה."""

    def __init__(self) -> None:
        self._title = ""
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        phones = [o["value"] for o in notify_target_options(self.hass) if o["value"].startswith("notify.mobile_app_")]
        engine = default_tts_engine(self.hass)
        defaults = {
            CONF_NAME: self._get_entry().title,
            CONF_MODE: ALERT_MODE_NEW,
            CONF_NOTIFY: phones,  # מסומנים מראש: כל הטלפונים עם אפליקציית Home Assistant
            CONF_TTS_ENGINE: engine,
            CONF_INCLUDE_SUMMARY: False,
            CONF_INCLUDE_IMAGE: True,
        }
        return await self._async_step_main("user", user_input, defaults)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        return await self._async_step_main("reconfigure", user_input, {CONF_NAME: subentry.title, **subentry.data})

    async def _async_step_main(
        self, step_id: str, user_input: dict[str, Any] | None, current: dict[str, Any]
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_NOTIFY) and not user_input.get(CONF_SPEAKERS):
                errors["base"] = "no_target"
            elif user_input.get(CONF_SPEAKERS) and not user_input.get(CONF_TTS_ENGINE):
                errors[CONF_TTS_ENGINE] = "tts_required"
            else:
                self._title = user_input[CONF_NAME]
                # שדה שנוקה לא מגיע בכלל, ולכן בונים מחדש ולא ממזגים עם הקיים
                self._data = {
                    **{k: v for k, v in current.items() if k not in (*_MAIN_FIELDS, CONF_NAME)},
                    CONF_MODE: user_input[CONF_MODE],
                    CONF_NOTIFY: user_input.get(CONF_NOTIFY, []),
                    CONF_SPEAKERS: user_input.get(CONF_SPEAKERS, []),
                    CONF_TTS_ENGINE: user_input.get(CONF_TTS_ENGINE),
                    CONF_INCLUDE_SUMMARY: user_input.get(CONF_INCLUDE_SUMMARY, False),
                    CONF_INCLUDE_IMAGE: user_input.get(CONF_INCLUDE_IMAGE, True),
                }
                if self._data[CONF_MODE] == ALERT_MODE_DAILY:
                    return await self.async_step_daily()
                return await self.async_step_new_article()
            current = {**current, **user_input}
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TextSelector(),
                vol.Required(CONF_MODE): SelectSelector(
                    SelectSelectorConfig(
                        options=[ALERT_MODE_NEW, ALERT_MODE_DAILY], translation_key="alert_mode", mode=SelectSelectorMode.LIST
                    )
                ),
                vol.Optional(CONF_NOTIFY): SelectSelector(
                    SelectSelectorConfig(options=notify_target_options(self.hass), multiple=True, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(CONF_SPEAKERS): EntitySelector(EntitySelectorConfig(domain="media_player", multiple=True)),
                vol.Optional(CONF_TTS_ENGINE): EntitySelector(EntitySelectorConfig(domain="tts")),
                vol.Optional(CONF_INCLUDE_SUMMARY): BooleanSelector(),
                vol.Optional(CONF_INCLUDE_IMAGE): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, current),
            errors=errors,
            description_placeholders={"feed": self._get_entry().title},
        )

    async def async_step_new_article(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            return self._async_finish(
                {
                    CONF_KEYWORDS: user_input.get(CONF_KEYWORDS, []),
                    CONF_QUIET_START: user_input[CONF_QUIET_START],
                    CONF_QUIET_END: user_input[CONF_QUIET_END],
                }
            )
        schema = vol.Schema(
            {
                vol.Optional(CONF_KEYWORDS): TextSelector(TextSelectorConfig(multiple=True)),
                vol.Required(CONF_QUIET_START): TimeSelector(),
                vol.Required(CONF_QUIET_END): TimeSelector(),
            }
        )
        defaults = {CONF_QUIET_START: "08:00:00", CONF_QUIET_END: "22:00:00", **self._data}
        return self.async_show_form(step_id="new_article", data_schema=self.add_suggested_values_to_schema(schema, defaults))

    async def async_step_daily(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_WEEKDAYS):
                errors[CONF_WEEKDAYS] = "no_weekdays"
            else:
                return self._async_finish(
                    {
                        CONF_TIME: user_input[CONF_TIME],
                        CONF_WEEKDAYS: user_input[CONF_WEEKDAYS],
                        CONF_COUNT: int(user_input[CONF_COUNT]),
                    }
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_TIME): TimeSelector(),
                vol.Optional(CONF_WEEKDAYS): SelectSelector(
                    SelectSelectorConfig(
                        options=WEEKDAY_OPTIONS, multiple=True, translation_key="weekday", mode=SelectSelectorMode.LIST
                    )
                ),
                vol.Required(CONF_COUNT): NumberSelector(NumberSelectorConfig(min=1, max=10, step=1, mode=NumberSelectorMode.BOX)),
            }
        )
        defaults = {CONF_TIME: "09:00:00", CONF_WEEKDAYS: WEEKDAY_OPTIONS, CONF_COUNT: 1, **self._data, **(user_input or {})}
        return self.async_show_form(
            step_id="daily", data_schema=self.add_suggested_values_to_schema(schema, defaults), errors=errors
        )

    @callback
    def _async_finish(self, step_data: dict[str, Any]) -> SubentryFlowResult:
        data = {k: v for k, v in self._data.items() if k not in _STEP_FIELDS} | step_data
        if self.source == SOURCE_RECONFIGURE:
            return self.async_update_and_abort(
                self._get_entry(), self._get_reconfigure_subentry(), title=self._title, data=data
            )
        return self.async_create_entry(title=self._title, data=data)
