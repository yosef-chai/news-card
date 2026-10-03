"""חיישנים: הכתבה האחרונה, כתבות שלא נקראו, מספר כתבות, זמן עדכון אחרון."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import NewsCardConfigEntry, NewsCardCoordinator, NewsFeedData
from .entity import NewsCardEntity

PARALLEL_UPDATES = 0
STATE_MAX = 255


@dataclass(frozen=True, kw_only=True)
class NewsSensorDescription(SensorEntityDescription):
    """תיאור חיישן."""

    value_fn: Callable[[NewsCardCoordinator], Any]


def _latest_title(data: NewsFeedData) -> str | None:
    if not data.entries:
        return None
    title = data.entries[0]["title"]
    return title if len(title) <= STATE_MAX else f"{title[: STATE_MAX - 1]}…"


def _last_update(data: NewsFeedData) -> datetime | None:
    return dt_util.parse_datetime(data.last_success) if data.last_success else None


SENSORS = (
    NewsSensorDescription(key="latest_article", value_fn=lambda c: _latest_title(c.data)),
    NewsSensorDescription(
        key="unread",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.unread_count,
    ),
    NewsSensorDescription(
        key="article_count",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: len(c.data.entries),
    ),
    NewsSensorDescription(
        key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _last_update(c.data),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NewsCardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(NewsSensor(coordinator, d) for d in SENSORS)


class NewsSensor(NewsCardEntity, SensorEntity):
    """חיישן פיד."""

    entity_description: NewsSensorDescription
    # התקציר והקישור משתנים כל הזמן ואין בהם ערך היסטורי
    _unrecorded_attributes = frozenset({"link", "image", "summary", "source", "published", "entry_id"})

    def __init__(self, coordinator: NewsCardCoordinator, description: NewsSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "latest_article" or not self.coordinator.data.entries:
            return None
        latest = self.coordinator.data.entries[0]
        return {
            "entry_id": latest["id"],
            "link": latest["link"],
            "summary": latest["summary"],
            "published": latest["published"],
            "source": latest["source"],
            "image": latest["image"],
        }

    @property
    @override
    def entity_picture(self) -> str | None:
        if self.entity_description.key != "latest_article" or not self.coordinator.data.entries:
            return None
        return self.coordinator.data.entries[0]["image"]
