"""ישות בסיס: מכשיר שירות אחד לכל פיד."""

from __future__ import annotations

from urllib.parse import urlparse

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NewsCardCoordinator


class NewsCardEntity(CoordinatorEntity[NewsCardCoordinator]):
    """בסיס לכל הישויות."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NewsCardCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        info = coordinator.data.info if coordinator.data else None
        link = info["link"] if info else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=urlparse(link or coordinator.url).netloc or None,
            model="News feed",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=link,
        )
