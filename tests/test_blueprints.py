"""ה-Blueprints נטענים, האוטומציות שנוצרות מהם תקינות, והן עושות את מה שהן מבטיחות."""

from pathlib import Path
import shutil
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
    mock_platform,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import FEED_URL, rss

BLUEPRINTS = Path(__file__).parents[1] / "blueprints"
EVENT = "event.jdn_new_article"
SENSOR = "sensor.jdn_latest_article"


class FakePhone:
    """פעולת המכשיר של mobile_app (הטעינה האמיתית דורשת את כל תלויות הענן). שומרת את ההתראות שנשלחו."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def async_validate_action_config(self, hass: HomeAssistant, config: dict) -> dict:
        return config

    async def async_call_action_from_config(self, hass: HomeAssistant, config: dict, variables: dict, context: Any) -> None:
        self.sent.append({k: Template(config[k], hass).async_render(variables) for k in ("message", "title", "data") if k in config})


@pytest.fixture
def phone(hass: HomeAssistant) -> FakePhone:
    fake = FakePhone()
    mock_platform(hass, "mobile_app.device_action", fake)
    return fake


@pytest.fixture
async def setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, tmp_path: Path, freezer: FrozenDateTimeFactory) -> str:
    """פיד טעון, ה-Blueprints בתיקיית ההגדרות, וטלפון לבחירה. מחזיר את מזהה הטלפון."""
    freezer.move_to("2026-10-01 10:30:00+03:00")
    hass.config.config_dir = str(tmp_path)
    shutil.copytree(BLUEPRINTS, tmp_path / "blueprints")
    await hass.config.async_set_time_zone("Asia/Jerusalem")
    entry.add_to_hass(hass)
    aioclient_mock.get(FEED_URL, content=rss([("a", "Thu, 01 Oct 2026 07:00:00 +0000")]))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    phone = dr.async_get(hass).async_get_or_create(config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "phone")}, name="Phone")
    return phone.id


async def _automations(hass: HomeAssistant, autos: list[dict]) -> None:
    assert await async_setup_component(hass, "automation", {"automation": autos})
    await hass.async_block_till_done()
    for auto in autos:
        state = hass.states.get(f"automation.{auto['alias']}")
        assert state and state.state == "on", f"{auto['alias']} is not valid"


def _bp(name: str, inputs: dict, alias: str) -> dict:
    return {"alias": alias, "use_blueprint": {"path": f"news_card/{name}.yaml", "input": inputs}}


async def _new_article(hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker, title_guid: str) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=rss([(title_guid, "Thu, 01 Oct 2026 07:20:00 +0000"), ("a", "Thu, 01 Oct 2026 07:00:00 +0000")]))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_notify_blueprint(
    hass: HomeAssistant, phone: FakePhone, setup: str, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    feeds = {"entity_id": EVENT}
    await _automations(hass, [
        _bp("notify_new_article", {"feeds": feeds, "notify_device": setup}, "notify"),
        _bp("notify_new_article", {"feeds": feeds, "notify_device": setup, "keywords": ["ITEM B"], "include_image": False}, "notify_b"),
        _bp("notify_new_article", {"feeds": feeds, "notify_device": setup, "keywords": ["nothing"]}, "notify_none"),
    ])
    await _new_article(hass, entry, aioclient_mock, "b")
    assert len(phone.sent) == 2
    data = {"url": "https://example.com/b", "clickAction": "https://example.com/b", "group": "news_card"}
    for sent in phone.sent:
        assert sent["title"] == "Test feed"
        assert sent["message"] == "Item b"
        assert {k: sent["data"][k] for k in data} == data
        assert "image" not in sent["data"]  # בפיד הבדיקה אין תמונות


async def test_speak_blueprint(
    hass: HomeAssistant, phone: FakePhone, setup: str, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    speak = async_mock_service(hass, "tts", "speak")
    inputs = {"feeds": {"entity_id": EVENT}, "tts_entity": "tts.google", "speakers": ["media_player.kitchen"], "prefix": "מבזק"}
    await _automations(hass, [
        _bp("speak_new_article", inputs, "speak"),
        _bp("speak_new_article", {**inputs, "keywords": ["nothing"]}, "speak_keywords"),
        _bp("speak_new_article", {**inputs, "start_time": "11:00:00"}, "speak_later"),
    ])
    await _new_article(hass, entry, aioclient_mock, "b")
    assert [(c.data["message"], c.data["media_player_entity_id"], c.data["entity_id"]) for c in speak] == [
        ("מבזק. Item b", ["media_player.kitchen"], ["tts.google"])
    ]


@pytest.mark.parametrize("expected_lingering_timers", [True])  # טריגר השעה מתזמן את היום הבא
async def test_briefing_blueprint(
    hass: HomeAssistant, phone: FakePhone, setup: str, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    speak = async_mock_service(hass, "tts", "speak")
    notify = async_mock_service(hass, "notify", "mobile_app_phone")
    await _new_article(hass, entry, aioclient_mock, "b")
    inputs = {"feeds": [SENSOR], "tts_entity": "tts.google", "speakers": ["media_player.kitchen"], "time": "10:45:00", "mark_read": True}
    await _automations(hass, [
        _bp("news_briefing", inputs, "briefing"),
        _bp("news_briefing", {"feeds": [SENSOR], "notify_device": setup, "time": "23:00:00", "hours": 24}, "briefing_phone"),
    ])
    assert hass.states.get("sensor.jdn_unread_articles").state == "2"
    freezer.move_to("2026-10-01 10:45:00+03:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert [c.data["message"] for c in speak] == ["News briefing. Item b. Item a"]
    assert hass.states.get("sensor.jdn_unread_articles").state == "0"

    # לטלפון: שירות ההתראות של האפליקציה לפי שם המכשיר
    freezer.move_to("2026-10-01 23:00:00+03:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert [(c.data["title"], c.data["message"]) for c in notify] == [("News briefing", "• Item b (Test feed)\n• Item a (Test feed)")]
    assert len(speak) == 1
