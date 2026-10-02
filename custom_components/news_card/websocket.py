"""WebSocket API לכרטיס: מנוי שדוחף נתונים בכל עדכון, עם נתיבי תמונה חתומים."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .const import CONF_PROXY_IMAGES, IMAGE_PROXY_URL, SIGNAL_UPDATED, SIGNED_PATH_TTL
from .coordinator import NewsCardCoordinator, coordinators_for
from .feed import make_id

type Signer = Callable[[str], str]


def feed_payload(coordinator: NewsCardCoordinator, signer: Signer | None = None) -> dict[str, Any]:
    """המבנה האחיד של פיד אחד (משותף לפעולה ול-WebSocket)."""
    data = coordinator.data
    entries = [{**e, "read": coordinator.is_read(e["id"])} for e in data.entries]
    if signer and coordinator.options[CONF_PROXY_IMAGES]:
        entry_id = coordinator.config_entry.entry_id
        for entry in entries:
            if entry["image"]:
                entry["image_proxy"] = signer(
                    IMAGE_PROXY_URL.format(entry_id=entry_id, image_id=make_id(entry["image"]))
                )
    return {
        "title": coordinator.config_entry.title,
        "feed": data.info,
        "entries": entries,
        "stale": not coordinator.last_update_success,
        "last_success": data.last_success,
        "error": coordinator.last_error,
    }


def _make_signer(hass: HomeAssistant, refresh_token_id: str | None) -> Signer:
    """חתימה עם מטמון: אותה כתובת חתומה חוזרת כדי שהדפדפן ישמור את התמונה במטמון."""
    cache: dict[str, tuple[str, Any]] = {}

    def sign(path: str) -> str:
        now = dt_util.utcnow()
        hit = cache.get(path)
        if hit and hit[1] - now > SIGNED_PATH_TTL / 2:
            return hit[0]
        signed = async_sign_path(hass, path, SIGNED_PATH_TTL, refresh_token_id=refresh_token_id)
        cache[path] = (signed, now + SIGNED_PATH_TTL)
        return signed

    return sign


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_subscribe)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "news_card/subscribe",
        vol.Required("entity_ids"): vol.All(cv.ensure_list, [cv.entity_id]),
    }
)
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """מנוי לפידים. כל הודעה: {"feeds": {entity_id: payload | {"error": key}}}."""
    entity_ids: list[str] = msg["entity_ids"]
    signer = _make_signer(hass, connection.refresh_token_id)
    registry = er.async_get(hass)

    @callback
    def send(targets: list[str]) -> None:
        feeds: dict[str, Any] = {}
        for entity_id in targets:
            try:
                coordinator = coordinators_for(hass, [entity_id])[entity_id]
            except ServiceValidationError as err:
                feeds[entity_id] = {"error": err.translation_key}
                continue
            feeds[entity_id] = feed_payload(coordinator, signer)
        connection.send_message(websocket_api.event_message(msg["id"], {"feeds": feeds}))

    by_entry: dict[str, list[str]] = {}
    for entity_id in entity_ids:
        reg = registry.async_get(entity_id)
        if reg and reg.config_entry_id:
            by_entry.setdefault(reg.config_entry_id, []).append(entity_id)

    # האות לפי config entry שורד טעינה מחדש של הרשומה
    unsubs = [
        async_dispatcher_connect(
            hass, SIGNAL_UPDATED.format(entry_id), callback(lambda ids=ids: send(ids))
        )
        for entry_id, ids in by_entry.items()
    ]

    @callback
    def unsubscribe() -> None:
        for unsub in unsubs:
            unsub()

    connection.subscriptions[msg["id"]] = unsubscribe
    connection.send_result(msg["id"])
    send(entity_ids)
