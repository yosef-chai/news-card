"""תנאי "כתבה אחרונה": האם התפרסמה בפיד כתבה בזמן האחרון, אפשר עם מילות מפתח."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Unpack, cast, override

import probatio as vol

from homeassistant.const import CONF_OPTIONS, CONF_TARGET
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.condition import (
    Condition,
    ConditionCheckParams,
    ConditionConfig,
    condition_trace_update_result,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import CONF_KEYWORDS, CONF_WITHIN
from .coordinator import entry_ids_for_target, loaded_coordinator, match_keywords

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TARGET): cv.TARGET_FIELDS,
        vol.Optional(CONF_OPTIONS, default={}): {
            vol.Optional(CONF_KEYWORDS, default=[]): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(CONF_WITHIN, default={"hours": 1}): cv.positive_time_period,
        },
    }
)


class RecentArticleCondition(Condition):
    """נכון אם באחד הפידים יש כתבה שפורסמה בפרק הזמן, ואם הוקלדו מילים — שמכילה אחת מהן."""

    @override
    @classmethod
    async def async_validate_config(cls, hass: HomeAssistant, config: ConfigType) -> ConfigType:
        return cast(ConfigType, SCHEMA(config))

    def __init__(self, hass: HomeAssistant, config: ConditionConfig) -> None:
        super().__init__(hass, config)
        options: dict[str, Any] = config.options or {}
        self._target: dict[str, Any] = config.target or {}
        self._within: timedelta = options[CONF_WITHIN]
        self._keywords = [k.strip().casefold() for k in options[CONF_KEYWORDS] if k.strip()]

    @override
    def _async_check(self, **kwargs: Unpack[ConditionCheckParams]) -> bool:
        since = dt_util.utcnow() - self._within
        for entry_id in entry_ids_for_target(self._hass, self._target):
            if not (coordinator := loaded_coordinator(self._hass, entry_id)):
                continue
            for entry in coordinator.data.entries:
                published = dt_util.parse_datetime(entry["published"] or "")
                if published and published >= since and (not self._keywords or match_keywords(entry, self._keywords)):
                    condition_trace_update_result(title=entry["title"], feed=coordinator.config_entry.title)
                    return True
        return False


CONDITIONS: dict[str, type[Condition]] = {"recent_article": RecentArticleCondition}


async def async_get_conditions(hass: HomeAssistant) -> dict[str, type[Condition]]:
    """התנאים של News Card."""
    return CONDITIONS
