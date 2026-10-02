"""אבחון: מצב הפיד והורדה אחרונה, בלי מידע אישי."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import NewsCardConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NewsCardConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "url": entry.data.get("url"),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "last_error": coordinator.last_error,
        "last_http_status": coordinator.last_status,
        "feed": data.info if data else None,
        "entry_count": len(data.entries) if data else 0,
        "entries_with_image": sum(1 for e in data.entries if e["image"]) if data else 0,
        "entries_with_estimated_date": sum(1 for e in data.entries if e["published_estimated"]) if data else 0,
        "last_success": data.last_success if data else None,
        "sample": data.entries[:3] if data else [],
    }
