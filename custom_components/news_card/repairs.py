"""תיקון: פיד שלא זמין לאורך זמן, שנמחק (404/410) או שהאתר מסרב לו — כתובת חדשה, ולסירוב גם User-Agent."""

from __future__ import annotations

from typing import Any

import probatio as vol

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .client import FALLBACK_REASONS, USER_AGENT_BROWSER, valid_user_agent
from .config_flow import FeedValidationError, async_validate_feed, normalize_url, user_agent_selector
from .const import CONF_URL, CONF_USER_AGENT, CONF_VERIFY_SSL


class FeedUnreachableRepairFlow(RepairsFlow):
    """בקשת כתובת חלופית ואימותה."""

    def __init__(self, entry_id: str, reason: str | None = None) -> None:
        self.entry_id = entry_id
        self.refused = reason == "refused"

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        # צעד הפתיחה מקבל את נתוני התקלה, לא קלט משתמש
        return await self.async_step_url()

    async def async_step_url(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry is None:
            return self.async_abort(reason="entry_removed")
        errors: dict[str, str] = {}
        placeholders = {"title": entry.title, "url": entry.data[CONF_URL], "status": ""}
        user_agent = entry.options.get(CONF_USER_AGENT, "")
        if user_input is not None:
            user_agent = (user_input.get(CONF_USER_AGENT) or "").strip() if self.refused else user_agent
            if not valid_user_agent(user_agent):
                errors[CONF_USER_AGENT] = "invalid_user_agent"
            else:
                try:
                    final_url, _ = await async_validate_feed(
                        self.hass, user_input[CONF_URL], entry.options.get(CONF_VERIFY_SSL, True), user_agent=user_agent
                    )
                except FeedValidationError as err:
                    errors["base"] = "still_refused" if user_agent and err.reason in (*FALLBACK_REASONS, "blocked") else err.reason
                    placeholders["status"] = str(err.status or "")
                else:
                    # שינוי ברשומה טוען אותה מחדש דרך מאזין העדכונים; בלי שינוי טוענים כאן
                    if not self.hass.config_entries.async_update_entry(
                        entry,
                        unique_id=normalize_url(final_url),
                        data={**entry.data, CONF_URL: final_url},
                        options={**entry.options, CONF_USER_AGENT: user_agent},
                    ):
                        self.hass.config_entries.async_schedule_reload(entry.entry_id)
                    return self.async_create_entry(data={})
        fields: dict[Any, Any] = {
            vol.Required(CONF_URL, default=entry.data[CONF_URL]): TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
        }
        if self.refused:
            fields[vol.Optional(CONF_USER_AGENT, description={"suggested_value": user_agent or USER_AGENT_BROWSER})] = (
                user_agent_selector()
            )
        return self.async_show_form(
            step_id="url", data_schema=vol.Schema(fields), errors=errors, description_placeholders=placeholders
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    data = data or {}
    return FeedUnreachableRepairFlow(str(data["entry_id"]), data.get("reason"))
