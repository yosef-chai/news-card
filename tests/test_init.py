"""בדיקות הקמה, ישויות, אירועים, פעולות, WebSocket, פרוקסי, תיקונים ואבחון."""

from datetime import timedelta
from http import HTTPStatus

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.setup import async_setup_component

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.news_card.client import BROWSER_USER_AGENT, USER_AGENT
from custom_components.news_card.const import DEFAULT_OPTIONS, DOMAIN, EVENT_NEW_ARTICLE
from custom_components.news_card.diagnostics import redact_url
from custom_components.news_card.feed import make_id

from .conftest import FEED_URL, RSS, fixture, refuse_default_user_agent, rss, user_agents

SENSOR = "sensor.jdn_latest_article"
EVENT = "event.jdn_new_article"
D1 = "Thu, 01 Oct 2026 08:00:00 +0000"
D2 = "Thu, 01 Oct 2026 09:00:00 +0000"
D3 = "Thu, 01 Oct 2026 10:00:00 +0000"


async def _refresh(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """מקדם את השעון ומריץ ריענון ישירות.

    לא מסתמכים על התזמון של המתאם: הוא משתנה בין גרסאות HA (ריצוד, השהיה אחרי כשל)
    ובמחשב עמוס הריענון המתוזמן לא תמיד נופל בתוך הקפיצה.
    """
    freezer.tick(timedelta(minutes=16))
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_setup_and_entities(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert loaded.state is ConfigEntryState.LOADED
    state = hass.states.get(SENSOR)
    assert state.state.startswith("מאחורי הקלעים")
    assert state.attributes["link"].startswith("https://www.jdn.co.il/")
    assert state.attributes["summary"]  # לשימוש ישיר בתבניות של אוטומציות
    assert state.attributes["entity_picture"].startswith("https://")
    assert hass.states.get("sensor.jdn_articles").state == "8"
    assert hass.states.get("sensor.jdn_last_update").state != "unknown"
    assert hass.states.get(EVENT).state == "unknown"  # אין אירועים בריענון הראשון


async def test_unload_and_remove(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(loaded.entry_id)
    assert loaded.state is ConfigEntryState.NOT_LOADED
    await hass.config_entries.async_remove(loaded.entry_id)


async def test_setup_retry_on_failure(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry) -> None:
    aioclient_mock.get(FEED_URL, status=503)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_new_articles_fire_events_once(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={**entry.options, "keywords": "Item b"})
    aioclient_mock.get(FEED_URL, content=rss([("a", D1)]))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bus = async_capture_events(hass, EVENT_NEW_ARTICLE)
    states: list = []
    hass.bus.async_listen("state_changed", lambda e: e.data["entity_id"] == EVENT and states.append(e.data["new_state"]))

    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=rss([("b", D2), ("a", D1)]))
    await _refresh(hass, freezer)
    assert [e.data["title"] for e in bus] == ["Item b"]
    assert bus[0].data["entity_id"] == EVENT
    assert bus[0].data["matched_keywords"] == ["item b"]
    # state trigger: הנתונים בתכונות ישות האירוע
    types = [s.attributes["event_type"] for s in states]
    assert types == ["new_article", "keyword_match"]
    assert states[0].attributes["title"] == "Item b"

    await _refresh(hass, freezer)  # אותו תוכן — בלי אירועים נוספים
    assert len(bus) == 1


async def test_new_article_trigger(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(FEED_URL, content=rss([("a", D1)]))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    calls = async_mock_service(hass, "test", "automation")

    def auto(alias: str, target: dict, options: dict) -> dict:
        return {
            "alias": alias,
            "triggers": {"trigger": "news_card.new_article", "target": target, "options": options},
            "actions": {"action": "test.automation", "data": {"alias": alias, "title": "{{ trigger.to_state.attributes.title }}"}},
        }

    assert await async_setup_component(hass, "automation", {"automation": [
        auto("all", {"entity_id": EVENT}, {}),
        auto("word", {"device_id": device.id}, {"keywords": ["  ITEM C ", ""]}),
        auto("none", {"entity_id": EVENT}, {"keywords": "nothing"}),
    ]})
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=rss([("c", D3), ("b", D2), ("a", D1)]))
    await _refresh(hass, freezer)
    assert sorted((c.data["alias"], c.data["title"]) for c in calls) == [
        ("all", "Item b"), ("all", "Item c"), ("word", "Item c")
    ]


async def test_no_events_after_restart(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry
) -> None:
    aioclient_mock.get(FEED_URL, content=rss([("a", D1)]))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bus = async_capture_events(hass, EVENT_NEW_ARTICLE)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert bus == []


async def test_old_entries_from_bigger_cap_not_announced(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    aioclient_mock.get(FEED_URL, content=rss([("c", D3)]))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bus = async_capture_events(hass, EVENT_NEW_ARTICLE)
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=rss([("c", D3), ("old", "Mon, 01 Jan 2024 00:00:00 +0000")]))
    await _refresh(hass, freezer)
    assert bus == []


async def test_not_modified_keeps_data(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=304)
    await _refresh(hass, freezer)
    assert loaded.runtime_data.last_update_success
    assert hass.states.get("sensor.jdn_articles").state == "8"


async def test_failure_marks_unavailable_and_serves_stale(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=500)
    await _refresh(hass, freezer)
    assert hass.states.get(SENSOR).state == "unavailable"
    response = await hass.services.async_call(DOMAIN, "get_entries", {"entity_id": SENSOR}, blocking=True, return_response=True)
    assert response[SENSOR]["stale"] is True
    assert len(response[SENSOR]["entries"]) == 8
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, f"feed_unreachable_{loaded.entry_id}") is None


async def test_repair_issue_on_404_and_cleared(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    issue_id = f"feed_unreachable_{loaded.entry_id}"
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=404)
    await _refresh(hass, freezer)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=fixture("jdn.xml"), headers={"Content-Type": RSS})
    await _refresh(hass, freezer)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_blocked_site_backs_off(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """חסימת בוטים מוצגת מיד כתקלה מוסברת, וכל כשל רצוף מאט את הניסיונות."""
    coordinator = loaded.runtime_data
    issue_id = f"feed_unreachable_{loaded.entry_id}"
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=403, headers={"cf-mitigated": "challenge"})
    await _refresh(hass, freezer)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue.translation_key == "feed_blocked"
    assert issue.translation_placeholders["status"] == "403"
    assert coordinator.last_error == "blocked"
    assert coordinator.update_interval == timedelta(minutes=15)
    await _refresh(hass, freezer)
    await _refresh(hass, freezer)
    assert coordinator.update_interval == timedelta(minutes=60)
    await _refresh(hass, freezer)
    assert coordinator.update_interval == timedelta(hours=1)  # תקרה

    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=429, headers={"Retry-After": "7200"})
    await _refresh(hass, freezer)
    assert coordinator.last_error == "rate_limited"
    assert coordinator.update_interval == timedelta(hours=2)

    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=fixture("jdn.xml"), headers={"Content-Type": RSS})
    await _refresh(hass, freezer)
    assert coordinator.update_interval == timedelta(minutes=15)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def _use_user_agent(hass: HomeAssistant, entry: MockConfigEntry, user_agent: str) -> None:
    hass.config_entries.async_update_entry(entry, options={**entry.options, "user_agent": user_agent})
    await hass.async_block_till_done()  # מאזין העדכון טוען את הרשומה מחדש


async def test_user_agent_fallback(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """ה-User-Agent מההגדרות נשלח רק אחרי סירוב, נשאר ליממה, ואז בודקים שוב את הרגיל."""
    await _use_user_agent(hass, loaded, "browser")
    coordinator = loaded.runtime_data
    aioclient_mock.clear_requests()
    refuse_default_user_agent(aioclient_mock, FEED_URL, fixture("jdn.xml"))
    await _refresh(hass, freezer)
    assert coordinator.last_update_success
    assert user_agents(aioclient_mock) == [USER_AGENT, BROWSER_USER_AGENT]
    assert coordinator.fallback_active

    await _refresh(hass, freezer)  # ישר עם החלופי, בלי בקשה כפולה
    assert user_agents(aioclient_mock) == [USER_AGENT, BROWSER_USER_AGENT, BROWSER_USER_AGENT]

    freezer.tick(timedelta(hours=24))
    await _refresh(hass, freezer)  # אחרי יממה מנסים שוב את הרגיל
    assert user_agents(aioclient_mock)[-2:] == [USER_AGENT, BROWSER_USER_AGENT]

    # גם החלופי נדחה: תקלה שמציעה User-Agent אחר, ובפעם הבאה מתחילים מהרגיל
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=403)
    await _refresh(hass, freezer)
    assert coordinator.last_error == "refused"
    assert not coordinator.fallback_active
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"feed_unreachable_{loaded.entry_id}")
    assert issue.translation_key == "feed_refused"
    assert issue.data["reason"] == "refused"
    await _refresh(hass, freezer)
    assert user_agents(aioclient_mock) == [BROWSER_USER_AGENT, USER_AGENT, BROWSER_USER_AGENT]


async def test_no_fallback_without_user_agent_or_for_challenge(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=403)
    await _refresh(hass, freezer)
    assert user_agents(aioclient_mock) == [USER_AGENT]
    await _use_user_agent(hass, loaded, "MyReader/1.0")
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=403, headers={"cf-mitigated": "challenge"})
    await _refresh(hass, freezer)
    assert user_agents(aioclient_mock) == [USER_AGENT]  # אתגר JavaScript: User-Agent אחר לא יעזור


async def test_refused_repair_flow_sets_user_agent(
    hass: HomeAssistant, hass_client, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    assert await async_setup_component(hass, "repairs", {})
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=406)
    await _refresh(hass, freezer)
    client = await hass_client()
    resp = await client.post("/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": f"feed_unreachable_{loaded.entry_id}"})
    flow = await resp.json()
    assert [f["name"] for f in flow["data_schema"]] == ["url", "user_agent"]
    url = f"/api/repairs/issues/fix/{flow['flow_id']}"
    resp = await client.post(url, json={"url": FEED_URL, "user_agent": "a\tb"})
    assert (await resp.json())["errors"] == {"user_agent": "invalid_user_agent"}
    resp = await client.post(url, json={"url": FEED_URL, "user_agent": "MyReader/1.0"})
    assert (await resp.json())["errors"] == {"base": "still_refused"}
    aioclient_mock.clear_requests()
    refuse_default_user_agent(aioclient_mock, FEED_URL, fixture("jdn.xml"))
    resp = await client.post(url, json={"url": FEED_URL, "user_agent": "browser"})
    assert (await resp.json())["type"] == "create_entry"
    assert loaded.options["user_agent"] == "browser"


async def test_repair_issue_after_long_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=b"garbage")
    await _refresh(hass, freezer)
    freezer.tick(timedelta(hours=25))
    await _refresh(hass, freezer)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"feed_unreachable_{loaded.entry_id}")


async def test_repair_flow(
    hass: HomeAssistant, hass_client, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    assert await async_setup_component(hass, "repairs", {})
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=410)
    await _refresh(hass, freezer)
    new = "https://www.emess.co.il/feed"
    aioclient_mock.get(new, content=fixture("emess.xml"), headers={"Content-Type": RSS})
    client = await hass_client()
    resp = await client.post("/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": f"feed_unreachable_{loaded.entry_id}"})
    flow = await resp.json()
    assert flow["step_id"] == "url"
    aioclient_mock.get("https://www.jdn.co.il/", status=404)
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={"url": FEED_URL})
    assert (await resp.json())["errors"] == {"base": "not_found"}
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={"url": new})
    assert (await resp.json())["type"] == "create_entry"
    assert loaded.data["url"] == new


async def test_get_entries_filters(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    call = lambda data: hass.services.async_call(DOMAIN, "get_entries", {"entity_id": SENSOR, **data}, blocking=True, return_response=True)  # noqa: E731
    assert len((await call({"limit": 2}))[SENSOR]["entries"]) == 2
    assert len((await call({"keyword": "zzzz-none"}))[SENSOR]["entries"]) == 0
    assert (await call({"since": "2030-01-01 00:00:00"}))[SENSOR]["entries"] == []
    full = (await call({}))[SENSOR]
    assert full["feed"]["title"] == "JDN"
    assert full["entries"][0]["image_proxy"] is None


async def test_service_errors(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "get_entries", {"entity_id": "sensor.nope"}, blocking=True, return_response=True)
    await hass.config_entries.async_unload(loaded.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "refresh", {"entity_id": SENSOR}, blocking=True)


async def test_refresh_service(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry) -> None:
    calls = aioclient_mock.call_count
    await hass.services.async_call(DOMAIN, "refresh", {"entity_id": SENSOR}, blocking=True)
    assert aioclient_mock.call_count == calls + 1
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, status=500)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "refresh", {"entity_id": SENSOR}, blocking=True)


async def test_websocket_subscribe(hass: HomeAssistant, hass_ws_client, loaded: MockConfigEntry) -> None:
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "news_card/subscribe", "entity_ids": [SENSOR, "sensor.missing"]})
    assert (await client.receive_json())["success"]
    event = (await client.receive_json())["event"]
    feed = event["feeds"][SENSOR]
    assert feed["title"] == "JDN"
    assert feed["entries"][0]["image_proxy"].startswith(f"/api/news_card/image/{loaded.entry_id}/")
    assert "authSig=" in feed["entries"][0]["image_proxy"]
    assert event["feeds"]["sensor.missing"] == {"error": "entity_not_found"}

    # עדכון נדחף לאחר ריענון, וחתימה זהה (מטמון דפדפן)
    await hass.services.async_call(DOMAIN, "refresh", {"entity_id": SENSOR}, blocking=True)
    again = (await client.receive_json())["event"]["feeds"][SENSOR]
    assert again["entries"][0]["image_proxy"] == feed["entries"][0]["image_proxy"]


async def test_image_proxy(hass: HomeAssistant, hass_client, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry) -> None:
    image = loaded.runtime_data.data.entries[0]["image"]
    aioclient_mock.get(image, content=b"\x89PNGdata", headers={"Content-Type": "image/png"})
    client = await hass_client()
    url = f"/api/news_card/image/{loaded.entry_id}/{make_id(image)}"
    resp = await client.get(url)
    assert resp.status == HTTPStatus.OK
    assert await resp.read() == b"\x89PNGdata"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    resp = await client.get(url)  # מהמטמון
    assert resp.status == HTTPStatus.OK
    assert aioclient_mock.call_count == 2  # פיד + תמונה אחת בלבד

    assert (await client.get(f"/api/news_card/image/{loaded.entry_id}/{make_id('https://evil/x')}")).status == HTTPStatus.NOT_FOUND
    assert (await client.get(f"/api/news_card/image/missing/{make_id(image)}")).status == HTTPStatus.NOT_FOUND


async def test_image_proxy_rejects_svg_and_errors(
    hass: HomeAssistant, hass_client, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry
) -> None:
    entries = loaded.runtime_data.data.entries
    aioclient_mock.get(entries[0]["image"], content=b"<svg/>", headers={"Content-Type": "image/svg+xml"})
    aioclient_mock.get(entries[1]["image"], status=500)
    aioclient_mock.get(entries[2]["image"], content=b"x", headers={"Content-Length": str(20 * 1024 * 1024)})
    client = await hass_client()
    base = f"/api/news_card/image/{loaded.entry_id}/"
    assert (await client.get(base + make_id(entries[0]["image"]))).status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    assert (await client.get(base + make_id(entries[1]["image"]))).status == HTTPStatus.BAD_GATEWAY
    assert (await client.get(base + make_id(entries[2]["image"]))).status == HTTPStatus.BAD_GATEWAY


async def test_image_proxy_requires_auth(hass: HomeAssistant, hass_client_no_auth, loaded: MockConfigEntry) -> None:
    client = await hass_client_no_auth()
    image = loaded.runtime_data.data.entries[0]["image"]
    resp = await client.get(f"/api/news_card/image/{loaded.entry_id}/{make_id(image)}")
    assert resp.status == HTTPStatus.UNAUTHORIZED


async def test_page_images(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="T", data={"url": FEED_URL}, options=DEFAULT_OPTIONS)
    aioclient_mock.get(FEED_URL, content=rss([("a", D1), ("b", D2)]))
    aioclient_mock.get("https://example.com/a", text='<meta property="og:image" content="/og-a.jpg">')
    aioclient_mock.get("https://example.com/b", status=404)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    images = {e["link"]: e["image"] for e in entry.runtime_data.data.entries}
    assert images == {"https://example.com/a": "https://example.com/og-a.jpg", "https://example.com/b": None}
    # דף שנכשל נבדק שוב בריענונים הבאים, עד 3 ניסיונות; דף עם תמונה לא נבדק שוב
    for expected in (2, 2, 1):
        calls = aioclient_mock.call_count
        await hass.services.async_call(DOMAIN, "refresh", {"entity_id": "sensor.t_latest_article"}, blocking=True)
        assert aioclient_mock.call_count == calls + expected


async def test_cached_data_on_startup_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry
) -> None:
    await hass.config_entries.async_unload(loaded.entry_id)
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, exc=TimeoutError())
    assert await hass.config_entries.async_setup(loaded.entry_id)
    assert loaded.state is ConfigEntryState.LOADED
    assert len(loaded.runtime_data.data.entries) == 8
    assert not loaded.runtime_data.last_update_success


async def test_diagnostics(hass: HomeAssistant, hass_client, loaded: MockConfigEntry) -> None:
    diag = await get_diagnostics_for_config_entry(hass, hass_client, loaded)
    assert diag["url"] == FEED_URL
    assert diag["entry_count"] == 8
    assert diag["entries_with_image"] == 8
    assert len(diag["sample"]) == 3
    # טוקן של פיד פרטי לא יוצא בקובץ האבחון
    assert redact_url("https://user:secret@example.com:8443/feed?token=abc#x") == "https://example.com:8443/feed?**REDACTED**"


async def test_card_served(hass: HomeAssistant, hass_client, loaded: MockConfigEntry) -> None:
    client = await hass_client()
    resp = await client.get("/news_card/frontend/news-card.js")
    assert resp.status == HTTPStatus.OK
    assert "customElements.define" in await resp.text()
    assert (await client.get("/news_card/frontend/../__init__.py")).status == HTTPStatus.NOT_FOUND


def test_versions_match() -> None:
    import json
    import re
    from pathlib import Path

    root = Path(__file__).parent.parent / "custom_components" / "news_card"
    manifest = json.loads((root / "manifest.json").read_text())["version"]
    card = re.search(r'CARD_VERSION = "([^"]+)"', (root / "frontend" / "news-card.js").read_text()).group(1)
    assert manifest == card


def test_translations_match() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).parent.parent / "custom_components" / "news_card"

    def keys(d: dict, prefix: str = "") -> set[str]:
        out = set()
        for k, v in d.items():
            out |= keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {prefix + k}
        return out

    strings = keys(json.loads((root / "strings.json").read_text("utf-8")))
    for lang in ("en", "he"):
        assert keys(json.loads((root / "translations" / f"{lang}.json").read_text("utf-8"))) == strings




async def test_image_proxy_sniffs_octet_stream(
    hass: HomeAssistant, hass_client, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry
) -> None:
    image = loaded.runtime_data.data.entries[2]["image"]
    aioclient_mock.get(image, content=b"\xff\xd8\xffjpegdata", headers={"Content-Type": "application/octet-stream"})
    client = await hass_client()
    resp = await client.get(f"/api/news_card/image/{loaded.entry_id}/{make_id(image)}")
    assert resp.status == HTTPStatus.OK
    assert resp.headers["Content-Type"] == "image/jpeg"


async def _setup_feed(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, items: list) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(FEED_URL, content=rss(items))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_mark_read(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, hass_ws_client
) -> None:
    await _setup_feed(hass, aioclient_mock, entry, [("b", D2), ("a", D1)])
    unread = "sensor.jdn_unread_articles"
    assert hass.states.get(unread).state == "2"
    bus = async_capture_events(hass, EVENT_NEW_ARTICLE)

    entries = (await hass.services.async_call(DOMAIN, "get_entries", {"entity_id": SENSOR}, blocking=True, return_response=True))[SENSOR]["entries"]
    assert [e["read"] for e in entries] == [False, False]
    await hass.services.async_call(DOMAIN, "mark_read", {"entity_id": EVENT, "article_id": entries[0]["id"]}, blocking=True)
    assert hass.states.get(unread).state == "1"

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "news_card/subscribe", "entity_ids": [SENSOR]})
    assert (await client.receive_json())["success"]
    feed = (await client.receive_json())["event"]["feeds"][SENSOR]
    assert [e["read"] for e in feed["entries"]] == [True, False]

    await hass.services.async_call(DOMAIN, "mark_read", {"entity_id": [SENSOR, unread]}, blocking=True)
    assert hass.states.get(unread).state == "0"
    assert bus == []  # סימון לא מכריז שוב על כתבות

    # נשמר אחרי טעינה מחדש
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(unread).state == "0"


async def test_recent_article_condition(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-10-01 10:30:00+00:00")
    await _setup_feed(hass, aioclient_mock, entry, [("c", D3), ("b", D2), ("a", D1)])
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    calls = async_mock_service(hass, "test", "automation")

    def auto(alias: str, target: dict, options: dict) -> dict:
        return {
            "alias": alias,
            "triggers": {"trigger": "event", "event_type": "test_event"},
            "conditions": {"condition": "news_card.recent_article", "target": target, "options": options},
            "actions": {"action": "test.automation", "data": {"alias": alias}},
        }

    assert await async_setup_component(hass, "automation", {"automation": [
        auto("hour", {"entity_id": SENSOR}, {"within": {"hours": 1}}),
        auto("10min", {"entity_id": SENSOR}, {"within": {"minutes": 10}}),
        auto("b_hour", {"device_id": device.id}, {"within": {"hours": 1}, "keywords": ["ITEM B"]}),
        auto("b_2h", {"device_id": device.id}, {"within": "02:00:00", "keywords": ["item b"]}),
        auto("default", {"entity_id": EVENT}, {}),
    ]})
    hass.bus.async_fire("test_event")
    await hass.async_block_till_done()
    assert sorted(c.data["alias"] for c in calls) == ["b_2h", "default", "hour"]


async def test_no_new_articles_trigger(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-10-01 10:30:00+00:00")
    await _setup_feed(hass, aioclient_mock, entry, [("c", D3), ("b", D2)])
    calls = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(hass, "automation", {"automation": [
        {
            "alias": alias,
            "triggers": {"trigger": "news_card.no_new_articles", "target": {"entity_id": EVENT}, "options": options},
            "actions": {"action": "test.automation", "data": {"alias": alias, "feed": "{{ trigger.feed }}", "entity": "{{ trigger.entity_id }}"}},
        }
        for alias, options in (("1h", {"for": {"hours": 1}}), ("default", {}), ("past", {"for": {"minutes": 10}}))
    ]})

    async def at(when: str) -> None:
        freezer.move_to(when)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    await at("2026-10-01 10:59:00+00:00")
    assert calls == []
    await at("2026-10-01 11:00:01+00:00")
    assert [(c.data["alias"], c.data["feed"], c.data["entity"]) for c in calls] == [("1h", "JDN", EVENT)]
    await at("2026-10-01 13:00:00+00:00")
    assert len(calls) == 1  # פעם אחת לכל שתיקה

    # כתבה חדשה מאפסת את הספירה
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=rss([("d", "Thu, 01 Oct 2026 13:00:00 +0000"), ("c", D3)]))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    await at("2026-10-01 14:00:01+00:00")
    assert [c.data["alias"] for c in calls] == ["1h", "past", "1h"]
    await at("2026-10-02 01:00:01+00:00")
    assert [c.data["alias"] for c in calls] == ["1h", "past", "1h", "default"]
