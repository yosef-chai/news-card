"""תיקון: פיד שלא זמין לאורך זמן או שנמחק (404/410) — הזנת כתובת חדשה."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .config_flow import FeedValidationError, async_validate_feed, normalize_url
from .const import CONF_URL, CONF_VERIFY_SSL


class FeedUnreachableRepairFlow(RepairsFlow):
    """בקשת כתובת חלופית ואימותה."""

    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        # צעד הפתיחה מקבל את נתוני התקלה, לא קלט משתמש
        return await self.async_step_url()

    async def async_step_url(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry is None:
            return self.async_abort(reason="entry_removed")
        errors: dict[str, str] = {}
        placeholders = {"title": entry.title, "url": entry.data[CONF_URL], "status": ""}
        if user_input is not None:
            try:
                final_url, _ = await async_validate_feed(
                    self.hass, user_input[CONF_URL], entry.options.get(CONF_VERIFY_SSL, True)
                )
            except FeedValidationError as err:
                errors["base"] = "not_a_feed" if err.discovered else err.reason
                placeholders["status"] = str(err.status or "")
            else:
                self.hass.config_entries.async_update_entry(
                    entry, unique_id=normalize_url(final_url), data={**entry.data, CONF_URL: final_url}
                )
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="url",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=entry.data[CONF_URL]): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    )
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    return FeedUnreachableRepairFlow(str((data or {})["entry_id"]))
