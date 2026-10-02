"""טריגרים: "כתבה חדשה" (עם מילות מפתח שמקלידים באוטומציה) ו"אין כתבות חדשות" (פיד שהפסיק להתעדכן)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, override

from homeassistant.components.event import ATTR_EVENT_TYPE, DOMAIN as EVENT_DOMAIN
from homeassistant.const import CONF_FOR, CONF_OPTIONS, CONF_TARGET
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.automation import DomainSpec
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.trigger import (
    NotTriggeredReasonReporter,
    StatelessEntityTriggerBase,
    Trigger,
    TriggerActionRunner,
    TriggerConfig,
    TriggerNotTriggeredReporter,
)
from homeassistant.helpers.typing import ConfigType

from homeassistant.util import dt as dt_util

from .const import CONF_KEYWORDS, DOMAIN, EVENT_TYPE_NEW, SIGNAL_UPDATED
from .coordinator import entry_ids_for_target, loaded_coordinator, match_keywords

try:  # ponytail: HA 2026.10 עבר ל-probatio; הסכמה חייבת להיות באותה ספרייה של cv.TARGET_FIELDS
    import probatio as vol
except ImportError:
    import voluptuous as vol  # type: ignore[no-redef]

OPTIONS_SCHEMA = vol.Schema({vol.Optional(CONF_KEYWORDS, default=[]): vol.All(cv.ensure_list, [cv.string])})


class NewArticleTrigger(StatelessEntityTriggerBase):
    """נורה לכל כתבה חדשה; אם הוקלדו מילים, רק לכתבה שמכילה אחת מהן."""

    _domain_specs = {EVENT_DOMAIN: DomainSpec()}

    @override
    @classmethod
    async def async_validate_config(cls, hass: HomeAssistant, config: ConfigType) -> ConfigType:
        # היעד נבדק בסכמה של HA, האפשרויות שלנו בנפרד
        options = OPTIONS_SCHEMA(config.get(CONF_OPTIONS) or {})
        config = await super().async_validate_config(hass, {**config, CONF_OPTIONS: {}})
        return {**config, CONF_OPTIONS: options}

    def __init__(self, hass: HomeAssistant, config: TriggerConfig) -> None:
        super().__init__(hass, config)
        self._keywords = [k.strip().casefold() for k in self._options.get(CONF_KEYWORDS, []) if k.strip()]

    @override
    def entity_filter(self, entities: set[str]) -> set[str]:
        """רק ישויות האירוע של News Card (אזור יכול להכיל גם אחרות)."""
        registry = er.async_get(self._hass)
        return {
            entity_id
            for entity_id in super().entity_filter(entities)
            if (entry := registry.async_get(entity_id)) and entry.platform == DOMAIN
        }

    @override
    def is_valid_state(self, state: State, report_not_triggered: NotTriggeredReasonReporter) -> bool:
        if state.attributes.get(ATTR_EVENT_TYPE) != EVENT_TYPE_NEW:
            return False
        if not self._keywords:
            return True
        attrs = state.attributes
        return bool(match_keywords({"title": attrs.get("title") or "", "summary": attrs.get("summary") or ""}, self._keywords))


NO_NEW_ARTICLES_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TARGET): cv.TARGET_FIELDS,
        vol.Optional(CONF_OPTIONS, default={}): {
            vol.Optional(CONF_FOR, default={"hours": 12}): cv.positive_time_period,
        },
    }
)


class NoNewArticlesTrigger(Trigger):
    """נורה כשבפיד לא התפרסמה כתבה חדשה במשך הזמן שנבחר (גם כשהאתר לא זמין).

    הזמן נמדד מהכתבה החדשה ביותר, כך שהוא שורד הפעלה מחדש. נורה פעם אחת במעבר הסף,
    ושוב רק אחרי שמגיעה כתבה חדשה והפיד שוב שותק.
    """

    @override
    @classmethod
    async def async_validate_config(cls, hass: HomeAssistant, config: dict[str, Any]) -> dict[str, Any]:
        return NO_NEW_ARTICLES_SCHEMA(config)

    def __init__(self, hass: HomeAssistant, config: TriggerConfig) -> None:
        super().__init__(hass, config)
        self._target: dict[str, Any] = config.target or {}
        self._for: timedelta = (config.options or {})[CONF_FOR]

    @override
    async def async_attach_runner(
        self, run_action: TriggerActionRunner, did_not_trigger: TriggerNotTriggeredReporter | None = None
    ) -> CALLBACK_TYPE:
        # לכל פיד: הכתבה החדשה ביותר שעליה הטיימר מחכה, וביטול הטיימר
        timers: dict[str, tuple[datetime, CALLBACK_TYPE]] = {}

        @callback
        def schedule(entry_id: str) -> None:
            coordinator = loaded_coordinator(self._hass, entry_id)
            newest = coordinator.newest_published if coordinator else None
            pending = timers.get(entry_id)
            if pending and pending[0] == newest:
                return  # אין כתבה חדשה; הטיימר הקיים בתוקף (גם אם הריענון נפל בדיוק בזמן היעד)
            if pending:
                timers.pop(entry_id)[1]()
            if not coordinator or not newest or newest + self._for <= dt_util.utcnow():
                return  # אין נתונים, או שהסף כבר עבר: מחכים לכתבה חדשה

            @callback
            def fire(now: datetime) -> None:
                timers.pop(entry_id, None)
                title = coordinator.config_entry.title
                run_action(
                    {
                        "entity_id": er.async_get(self._hass).async_get_entity_id(
                            "event", DOMAIN, f"{entry_id}_new_article"
                        ),
                        "feed": title,
                        "last_article": newest.isoformat(),
                        "for": self._for,
                    },
                    f"no new articles from {title} for {self._for}",
                )

            timers[entry_id] = (newest, async_track_point_in_utc_time(self._hass, fire, newest + self._for))

        # ponytail: היעד נפתר בהפעלת האוטומציה; פיד שנוסף למכשיר או לאזור אחר כך ייכנס בטעינה הבאה שלה
        entry_ids = entry_ids_for_target(self._hass, self._target)
        unsubs = [
            async_dispatcher_connect(
                self._hass, SIGNAL_UPDATED.format(entry_id), callback(lambda entry_id=entry_id: schedule(entry_id))
            )
            for entry_id in entry_ids
        ]
        for entry_id in entry_ids:
            schedule(entry_id)

        @callback
        def detach() -> None:
            for unsub in unsubs:
                unsub()
            for _, cancel in timers.values():
                cancel()
            timers.clear()

        return detach


TRIGGERS: dict[str, type[Trigger]] = {"new_article": NewArticleTrigger, "no_new_articles": NoNewArticlesTrigger}


async def async_get_triggers(hass: HomeAssistant) -> dict[str, type[Trigger]]:
    """הטריגרים של News Card."""
    return TRIGGERS
