"""אבחון: מצב הפיד והורדה אחרונה, בלי מידע אישי."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from homeassistant.core import HomeAssistant

from .const import CONF_URL
from .coordinator import NewsCardConfigEntry

REDACTED = "**REDACTED**"


def redact_url(url: str) -> str:
    """פיד פרטי שם טוקן בפרמטרים או בפרטי הכניסה; הכתובת עצמה נשארת לאבחון."""
    parts = urlsplit(url)
    host = f"{parts.hostname or ''}{f':{parts.port}' if parts.port else ''}"
    return urlunsplit((parts.scheme, host, parts.path, REDACTED if parts.query else "", ""))


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NewsCardConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "url": redact_url(entry.data[CONF_URL]),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "last_error": coordinator.last_error,
        "last_http_status": coordinator.last_status,
        "user_agent_fallback_active": coordinator.fallback_active,
        "feed": data.info if data else None,
        "entry_count": len(data.entries) if data else 0,
        "entries_with_image": sum(1 for e in data.entries if e["image"]) if data else 0,
        "entries_with_estimated_date": sum(1 for e in data.entries if e["published_estimated"]) if data else 0,
        "last_success": data.last_success if data else None,
        "sample": data.entries[:3] if data else [],
    }
