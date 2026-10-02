"""התראות מהממשק: זרימת ההגדרה, התראה על כתבה חדשה, ותדריך בשעה קבועה."""

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, async_mock_service
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.news_card.config_flow import notify_target_options
from custom_components.news_card.const import DOMAIN

from .conftest import FEED_URL, rss

PHONE = "notify.mobile_app_galaxy"
D1 = "Thu, 01 Oct 2026 05:00:00 +0000"
D2 = "Thu, 01 Oct 2026 06:00:00 +0000"


@pytest.fixture
async def feed(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, freezer: FrozenDateTimeFactory) -> MockConfigEntry:
    freezer.move_to("2026-10-01 09:30:00+03:00")  # יום חמישי
    await hass.config.async_set_time_zone("Asia/Jerusalem")
    entry.add_to_hass(hass)
    aioclient_mock.get(FEED_URL, content=rss([("a", D1)]))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def calls(hass: HomeAssistant) -> dict[str, list]:
    return {"phone": async_mock_service(hass, "notify", "mobile_app_galaxy"), "speak": async_mock_service(hass, "tts", "speak")}


async def _add_alert(hass: HomeAssistant, entry: MockConfigEntry, main: dict, step: dict) -> None:
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "alert"), context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], main)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], step)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()  # הוספת התראה טוענת מחדש את הפיד


async def _publish(hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker, guid: str = "b") -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=rss([(guid, D2), ("a", D1)]))
    await hass.config_entries.async_get_entry(entry.entry_id).runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_flow_defaults_and_errors(hass: HomeAssistant, feed: MockConfigEntry, calls: dict) -> None:
    result = await hass.config_entries.subentries.async_init((feed.entry_id, "alert"), context={"source": SOURCE_USER})
    schema = {str(k): k for k in result["data_schema"].schema}
    # הטלפון מסומן מראש, והשם הוא שם הפיד
    assert schema["notify"].description["suggested_value"] == [PHONE]
    assert schema["name"].description["suggested_value"] == "JDN"

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "x", "mode": "new_article", "notify": []})
    assert result["errors"] == {"base": "no_target"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "x", "mode": "new_article", "speakers": ["media_player.kitchen"]}
    )
    assert result["errors"] == {"tts_engine": "tts_required"}


async def test_new_article_alert(
    hass: HomeAssistant, feed: MockConfigEntry, calls: dict, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    main = {"name": "חדשות", "mode": "new_article", "notify": [PHONE], "speakers": ["media_player.kitchen"], "tts_engine": "tts.google", "include_summary": False, "include_image": True}
    await _add_alert(hass, feed, main, {"speak_from": "08:00:00", "speak_until": "22:00:00"})
    await _publish(hass, feed, aioclient_mock)

    assert [(c.data["title"], c.data["message"]) for c in calls["phone"]] == [("Test feed", "Item b")]
    assert calls["phone"][0].data["data"]["url"] == "https://example.com/b"
    assert [(c.data["message"], c.data["media_player_entity_id"], c.data["entity_id"]) for c in calls["speak"]] == [
        ("JDN. Item b", ["media_player.kitchen"], "tts.google")
    ]

    # בלילה: רק לטלפון
    freezer.move_to("2026-10-01 23:30:00+03:00")
    await _publish(hass, feed, aioclient_mock, "c")
    assert len(calls["phone"]) == 2
    assert len(calls["speak"]) == 1


@pytest.mark.parametrize("expected_lingering_timers", [True])  # אחרי העריכה מתוזמנת שעה קבועה
async def test_keywords_and_reconfigure(
    hass: HomeAssistant, feed: MockConfigEntry, calls: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    await _add_alert(hass, feed, {"name": "x", "mode": "new_article", "notify": [PHONE]}, {"keywords": ["nothing"], "speak_from": "08:00:00", "speak_until": "22:00:00"})
    await _publish(hass, feed, aioclient_mock)
    assert calls["phone"] == []

    # עריכה: מעבר לתדריך יומי
    subentry_id = next(iter(feed.subentries))
    result = await hass.config_entries.subentries.async_init(
        (feed.entry_id, "alert"), context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry_id}
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "בוקר", "mode": "daily", "notify": [PHONE], "include_summary": True})
    assert result["step_id"] == "daily"
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"time": "10:00:00", "weekdays": [], "count": 1})
    assert result["errors"] == {"weekdays": "no_weekdays"}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"time": "10:00:00", "weekdays": ["thu"], "count": 1})
    assert result["type"] is FlowResultType.ABORT
    subentry = feed.subentries[subentry_id]
    assert subentry.title == "בוקר"
    assert "keywords" not in subentry.data
    assert subentry.data["time"] == "10:00:00"


@pytest.mark.parametrize("expected_lingering_timers", [True])  # השעה הקבועה מתוזמנת ליום הבא
async def test_daily_alert(
    hass: HomeAssistant, feed: MockConfigEntry, calls: dict, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    main = {"name": "תחזית", "mode": "daily", "notify": [PHONE], "speakers": ["media_player.kitchen"], "tts_engine": "tts.google", "include_summary": True}
    await _add_alert(hass, feed, main, {"time": "10:00:00", "weekdays": ["sun", "mon", "tue", "wed", "thu", "fri"], "count": 1})
    await _publish(hass, feed, aioclient_mock)
    assert calls["phone"] == []  # בתדריך יומי לא מתריעים על כל כתבה

    freezer.move_to("2026-10-01 10:00:00+03:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert [(c.data["title"], c.data["message"]) for c in calls["phone"]] == [("Test feed", "Item b\n\nAbout b")]
    assert [c.data["message"] for c in calls["speak"]] == ["JDN. Item b. About b"]

    freezer.move_to("2026-10-03 10:00:00+03:00")  # שבת
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls["phone"]) == 1


async def test_failed_target_does_not_stop_others(
    hass: HomeAssistant, feed: MockConfigEntry, calls: dict, aioclient_mock: AiohttpClientMocker, caplog: pytest.LogCaptureFixture
) -> None:
    async_mock_service(hass, "notify", "mobile_app_gone")
    await _add_alert(hass, feed, {"name": "x", "mode": "new_article", "notify": ["notify.mobile_app_gone", PHONE]}, {"speak_from": "08:00:00", "speak_until": "22:00:00"})
    hass.services.async_remove("notify", "mobile_app_gone")  # הטלפון הוסר אחרי שההתראה הוגדרה
    await _publish(hass, feed, aioclient_mock)
    assert len(calls["phone"]) == 1
    assert "notify.mobile_app_gone failed" in caplog.text


async def test_notify_targets_without_duplicates(hass: HomeAssistant, calls: dict) -> None:
    """הטלפון מופיע פעם אחת (כשירות, שתומך בתמונה ובקישור); ישויות notify אחרות נשארות."""
    registry = er.async_get(hass)
    phone = registry.async_get_or_create("notify", "mobile_app", "phone", suggested_object_id="galaxy")
    chat = registry.async_get_or_create("notify", "telegram_bot", "chat", suggested_object_id="family")
    hass.states.async_set(phone.entity_id, "unknown")
    hass.states.async_set(chat.entity_id, "unknown", {"friendly_name": "Family"})
    MockConfigEntry(domain="mobile_app", title="Galaxy", data={"device_name": "Galaxy"}).add_to_hass(hass)
    assert notify_target_options(hass) == [
        {"value": PHONE, "label": "Galaxy"},
        {"value": chat.entity_id, "label": "Family"},
    ]


async def test_send_to_phone_and_announce(
    hass: HomeAssistant, feed: MockConfigEntry, calls: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    await _publish(hass, feed, aioclient_mock)
    app = MockConfigEntry(domain="mobile_app", title="Galaxy", data={"device_name": "Galaxy"})
    app.add_to_hass(hass)
    phone = dr.async_get(hass).async_get_or_create(config_entry_id=app.entry_id, identifiers={("mobile_app", "g")}, name="Galaxy")
    sensor = "sensor.jdn_latest_article"

    await hass.services.async_call(DOMAIN, "send_to_phone", {"entity_id": sensor, "phones": [phone.id]}, blocking=True)
    assert [(c.data["title"], c.data["message"], c.data["data"]["url"]) for c in calls["phone"]] == [
        ("Test feed", "Item b", "https://example.com/b")
    ]
    # כמה כתבות: הודעה אחת מרוכזת; מילת מפתח מסננת
    await hass.services.async_call(DOMAIN, "send_to_phone", {"entity_id": sensor, "phones": [phone.id], "count": 2}, blocking=True)
    assert calls["phone"][-1].data["message"] == "• Item b\n• Item a"
    await hass.services.async_call(DOMAIN, "send_to_phone", {"entity_id": sensor, "phones": [phone.id], "keyword": "zzz"}, blocking=True)
    assert len(calls["phone"]) == 2

    await hass.services.async_call(
        DOMAIN, "announce", {"entity_id": sensor, "speakers": "media_player.kitchen", "tts_engine": "tts.google", "include_summary": True}, blocking=True
    )
    assert [(c.data["message"], c.data["media_player_entity_id"]) for c in calls["speak"]] == [("JDN. Item b. About b", ["media_player.kitchen"])]


async def test_action_errors(hass: HomeAssistant, feed: MockConfigEntry, calls: dict) -> None:
    other = dr.async_get(hass).async_get_or_create(config_entry_id=feed.entry_id, identifiers={("x", "y")}, name="Lamp")
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "send_to_phone", {"entity_id": "sensor.jdn_latest_article", "phones": [other.id]}, blocking=True)
    assert err.value.translation_key == "phone_not_found"
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "announce", {"entity_id": "sensor.jdn_latest_article", "speakers": "media_player.kitchen"}, blocking=True)
    assert err.value.translation_key == "tts_required"
    # שגיאה בשליחה מוצגת למי שהריץ את הפעולה
    hass.services.async_remove("tts", "speak")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "announce", {"entity_id": "sensor.jdn_latest_article", "speakers": "media_player.kitchen", "tts_engine": "tts.google"}, blocking=True
        )


async def test_phone_without_app_service_uses_notify_entity(hass: HomeAssistant, feed: MockConfigEntry) -> None:
    """טלפון שיש לו רק ישות notify (בלי שירות האפליקציה) מקבל דרך send_message."""
    send = async_mock_service(hass, "notify", "send_message")
    app = MockConfigEntry(domain="mobile_app", title="Pixel", data={"device_name": "Pixel"})
    app.add_to_hass(hass)
    phone = dr.async_get(hass).async_get_or_create(config_entry_id=app.entry_id, identifiers={("mobile_app", "p")}, name="Pixel")
    notify = er.async_get(hass).async_get_or_create("notify", "mobile_app", "p", device_id=phone.id, suggested_object_id="pixel")
    hass.states.async_set(notify.entity_id, "unknown")
    await hass.services.async_call(DOMAIN, "send_to_phone", {"entity_id": "sensor.jdn_latest_article", "phones": [phone.id]}, blocking=True)
    assert [(c.data["entity_id"], c.data["message"]) for c in send] == [(notify.entity_id, "Item a")]
