"""News Card: פידי חדשות (RSS / Atom / JSON Feed) ללוח המחוונים ולאוטומציות."""

import asyncio
from datetime import datetime
import logging
from pathlib import Path
from typing import Any

import probatio

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    config_validation as cv,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .alerts import async_register_services, async_setup_alerts
from .const import CARD_FILE, DOMAIN, STATIC_URL, STORAGE_VERSION
from .coordinator import (
    NewsCardConfigEntry,
    NewsCardCoordinator,
    coordinators_for,
    issue_id_for,
    match_keywords,
)
from .image_proxy import NewsCardImageView
from .websocket import async_register_websocket, feed_payload

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.EVENT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_GET_ENTRIES = "get_entries"
SERVICE_REFRESH = "refresh"
SERVICE_MARK_READ = "mark_read"

GET_ENTRIES_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
        probatio.Optional("limit"): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1, max=100)
        ),
        probatio.Optional("keyword"): cv.string,
        probatio.Optional("since"): cv.datetime,
    }
)
REFRESH_SCHEMA = probatio.Schema({probatio.Required(ATTR_ENTITY_ID): cv.entity_ids})
MARK_READ_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
        probatio.Optional("article_id"): probatio.All(
            probatio.EnsureList(), [cv.string]
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """רישום פעולות, WebSocket, פרוקסי התמונות וקובץ הכרטיס (פעם אחת)."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_ENTRIES,
        _async_get_entries,
        schema=GET_ENTRIES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, _async_refresh, schema=REFRESH_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_MARK_READ, _async_mark_read, schema=MARK_READ_SCHEMA
    )
    async_register_services(hass)
    async_register_websocket(hass)
    hass.http.register_view(NewsCardImageView(hass))

    if not hass.data.get(f"{DOMAIN}_frontend"):
        hass.data[f"{DOMAIN}_frontend"] = True
        integration = await async_get_integration(hass, DOMAIN)
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL, str(Path(__file__).parent / "frontend"), True
                )
            ]
        )
        add_extra_js_url(hass, f"{STATIC_URL}/{CARD_FILE}?v={integration.version}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NewsCardConfigEntry) -> bool:
    """הקמת פיד."""
    coordinator = NewsCardCoordinator(hass, entry)
    cached = await coordinator.async_load()
    if not cached:
        await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _on_update() -> None:
        event_entity = er.async_get(hass).async_get_entity_id(
            "event", DOMAIN, f"{entry.entry_id}_new_article"
        )
        coordinator.fire_bus_events(event_entity)
        coordinator.async_notify()

    entry.async_on_unload(coordinator.async_add_listener(_on_update))
    for unsub in async_setup_alerts(hass, entry):
        entry.async_on_unload(unsub)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_notify()
    if cached:
        # יש עותק שמור: עולים מיד בלי לחכות לאתר. הריענון רץ אחרי שההתראות והישויות מחוברות,
        # כדי שכתבה שהתפרסמה בזמן טעינה מחדש לא תסומן כמוכרזת בלי שנשלחה
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), f"{DOMAIN} first refresh {entry.title}"
        )
    return True


async def _async_reload(hass: HomeAssistant, entry: NewsCardConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NewsCardConfigEntry) -> bool:
    """פריקה."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: NewsCardConfigEntry) -> None:
    """מחיקת המצב השמור והודעת התיקון כשהפיד נמחק."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
    ir.async_delete_issue(hass, DOMAIN, issue_id_for(entry.entry_id))


async def _async_get_entries(call: ServiceCall) -> ServiceResponse:
    """הפריטים השמורים, בלי פנייה לרשת."""
    limit: int | None = call.data.get("limit")
    keyword: str = call.data.get("keyword", "").strip().casefold()
    since: datetime | None = call.data.get("since")
    if since and since.tzinfo is None:
        since = since.replace(tzinfo=dt_util.get_default_time_zone())
    response: dict[str, Any] = {}
    for entity_id, coordinator in coordinators_for(
        call.hass, call.data[ATTR_ENTITY_ID]
    ).items():
        payload = feed_payload(coordinator)
        entries = payload["entries"]
        if keyword:
            entries = [e for e in entries if match_keywords(e, [keyword])]
        if since:
            entries = [
                e
                for e in entries
                if (parsed := dt_util.parse_datetime(e["published"] or ""))
                and parsed >= since
            ]
        payload["entries"] = entries[:limit] if limit else entries
        response[entity_id] = payload
    return response


async def _async_refresh(call: ServiceCall) -> None:
    """ריענון מיידי, כל פיד פעם אחת ובמקביל. שגיאה אחת בסוף עם כל הפידים שנכשלו."""
    coordinators = list(
        dict.fromkeys(coordinators_for(call.hass, call.data[ATTR_ENTITY_ID]).values())
    )
    await asyncio.gather(*(c.async_refresh() for c in coordinators))
    if failed := [c for c in coordinators if not c.last_update_success]:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="refresh_failed",
            translation_placeholders={
                "title": ", ".join(c.config_entry.title for c in failed),
                "error": ", ".join(
                    dict.fromkeys(c.last_error or "unknown" for c in failed)
                ),
            },
        )


async def _async_mark_read(call: ServiceCall) -> None:
    """סימון כתבות כנקראו. בלי article_id: כל הכתבות בפיד."""
    article_ids: list[str] | None = call.data.get("article_id")
    for coordinator in set(
        coordinators_for(call.hass, call.data[ATTR_ENTITY_ID]).values()
    ):
        coordinator.async_mark_read(article_ids)
