"""ישות אירוע: כתבה חדשה / התאמת מילת מפתח."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EVENT_TYPE_KEYWORD, EVENT_TYPE_NEW
from .coordinator import NewsCardConfigEntry, NewsCardCoordinator, match_keywords
from .entity import NewsCardEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: NewsCardConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([NewsEvent(entry.runtime_data)])


class NewsEvent(NewsCardEntity, EventEntity):
    """נורה פעם אחת לכל כתבה חדשה. נתוני הכתבה זמינים ב-trigger.to_state.attributes."""

    _attr_event_types = [EVENT_TYPE_NEW, EVENT_TYPE_KEYWORD]

    def __init__(self, coordinator: NewsCardCoordinator) -> None:
        super().__init__(coordinator, "new_article")

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        for entry in data.new_entries if data else []:
            attrs = {**entry, "feed_title": data.info["title"]}
            self._trigger_event(EVENT_TYPE_NEW, attrs)
            self.async_write_ha_state()
            if matched := match_keywords(entry, self.coordinator.keywords):
                self._trigger_event(EVENT_TYPE_KEYWORD, {**attrs, "matched_keywords": matched})
                self.async_write_ha_state()
        super()._handle_coordinator_update()
