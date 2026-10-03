"""בדיקות זרימת ההגדרה, ההגדרה מחדש והאפשרויות."""

import asyncio
import re
from unittest.mock import patch

import aiohttp
import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.news_card.config_flow import normalize_url
from custom_components.news_card.const import DOMAIN

from custom_components.news_card.client import BROWSER_USER_AGENT, USER_AGENT

from .conftest import FEED_URL, RSS, fixture, refuse_default_user_agent, user_agents

SETUP = "custom_components.news_card.async_setup_entry"


async def _start(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_user_flow_creates_entry(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(FEED_URL, content=fixture("jdn.xml"), headers={"Content-Type": RSS})
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "JDN"
    assert result["data"] == {"url": FEED_URL}
    assert result["options"]["verify_ssl"] is True
    assert result["result"].unique_id == "https://www.jdn.co.il/feed"


async def test_discovery_step(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get("https://www.jdn.co.il/", content=fixture("page.html"), headers={"Content-Type": "text/html"})
    aioclient_mock.get(FEED_URL, content=fixture("jdn.xml"), headers={"Content-Type": RSS})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "www.jdn.co.il/"})
    assert result["step_id"] == "select_feed"
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["type"] is FlowResultType.CREATE_ENTRY


def _options(result: dict) -> list[str]:
    return [o["value"] for o in result["data_schema"].schema["url"].config["options"]]


async def test_discovery_without_declared_feeds(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """אתר בלי <link> לפיד: נתיב מקובל שעובד, קישור "RSS" לדף אינדקס, ומשם לפיד עצמו."""
    home = "https://news.example/"
    page = b'<html><body><a href="/rss">RSS</a><a href="/music-feed/a.htm">clip</a></body></html>'
    index = b'<html><body><a href="/rss/feed/news">News</a><a href="/rss/feed/sport">Sport</a></body></html>'
    aioclient_mock.get(home, content=page, headers={"Content-Type": "text/html"})
    aioclient_mock.get(f"{home}feed", content=fixture("jdn.xml"), headers={"Content-Type": RSS})
    aioclient_mock.get(f"{home}rss", content=index, headers={"Content-Type": "text/html"})
    aioclient_mock.get(f"{home}rss/feed/news", content=fixture("emess.xml"), headers={"Content-Type": RSS})
    aioclient_mock.get(re.compile(r"^https://news\.example/"), status=404)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": home})
    assert result["step_id"] == "select_feed"
    assert _options(result) == [f"{home}feed", f"{home}rss"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": f"{home}rss"})
    assert result["step_id"] == "select_feed"
    assert not result["errors"]
    assert _options(result) == [f"{home}rss/feed/news", f"{home}rss/feed/sport"]
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": f"{home}rss/feed/news"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"url": f"{home}rss/feed/news"}


async def test_discovery_step_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get("https://www.jdn.co.il/", content=fixture("page.html"), headers={"Content-Type": "text/html"})
    aioclient_mock.get(FEED_URL, status=500)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "https://www.jdn.co.il/"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["errors"] == {"base": "server_error"}
    assert result["description_placeholders"]["status"] == "500"


@pytest.mark.parametrize(
    ("mock", "error"),
    [
        ({"exc": asyncio.TimeoutError()}, "timeout"),
        ({"exc": aiohttp.ClientError()}, "cannot_connect"),
        ({"status": 404}, "not_found"),
        ({"status": 403, "headers": {"cf-mitigated": "challenge"}}, "blocked"),
        ({"status": 401, "headers": {"x-datadome": "protected"}}, "blocked"),
        ({"status": 429, "headers": {"x-iinfo": "1", "Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}}, "blocked"),
        ({"status": 503, "headers": {"cf-mitigated": "challenge", "Retry-After": "soon"}}, "blocked"),
        ({"status": 401}, "auth_required"),
        ({"status": 503}, "server_error"),
        ({"status": 418}, "http_error"),
        ({"content": b"plain text"}, "invalid_feed"),
        ({"content": b"<html><body>no feeds</body></html>", "headers": {"Content-Type": "text/html"}}, "not_a_feed"),
    ],
)
async def test_user_flow_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock: dict, error: str) -> None:
    aioclient_mock.get(FEED_URL, **mock)
    aioclient_mock.get(re.compile(r"^https://www\.jdn\.co\.il/"), status=404)  # נתיבי פיד מקובלים
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_refused_site_offers_user_agent(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """אתר שמסרב לקורא פידים: מציעים User-Agent, והוא נשמר בהגדרות ונשלח רק אחרי סירוב."""
    refuse_default_user_agent(aioclient_mock, FEED_URL, fixture("jdn.xml"))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "www.jdn.co.il/feed/"})
    assert result["step_id"] == "user_agent"
    assert result["description_placeholders"] == {"host": "www.jdn.co.il", "status": "406"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"user_agent": "two\nlines"})
    assert result["errors"] == {"user_agent": "invalid_user_agent"}
    aioclient_mock.clear_requests()
    refuse_default_user_agent(aioclient_mock, FEED_URL, fixture("jdn.xml"))
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"user_agent": "browser"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["user_agent"] == "browser"
    assert user_agents(aioclient_mock) == [USER_AGENT, BROWSER_USER_AGENT]


async def test_user_agent_still_refused(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(FEED_URL, status=429)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["step_id"] == "user_agent"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"user_agent": "MyReader/1.0"})
    assert result["errors"] == {"base": "still_refused"}
    assert user_agents(aioclient_mock)[-1] == "MyReader/1.0"


async def test_user_agent_then_discovery(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """אתר שמסרב, ואחרי ה-User-Agent מתגלה שזה דף: בחירת פיד, וה-User-Agent נשמר לפיד שנבחר."""
    home = "https://www.jdn.co.il/"
    refuse_default_user_agent(aioclient_mock, home, fixture("page.html"), "text/html", status=403)
    refuse_default_user_agent(aioclient_mock, FEED_URL, fixture("jdn.xml"), status=403)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": home})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"user_agent": "browser"})
    assert result["step_id"] == "select_feed"
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["user_agent"] == "browser"


async def test_moved_feed_offers_homepage_feeds(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """פיד ישן שמחזיר 404: מוצעים הפידים שבדף הבית של האתר."""
    aioclient_mock.get(FEED_URL, status=404)
    aioclient_mock.get("https://www.jdn.co.il/", content=fixture("page.html"), headers={"Content-Type": "text/html"})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["step_id"] == "moved"
    assert _options(result) == ["https://www.jdn.co.il/comments/feed/"]  # בלי הכתובת השבורה עצמה
    aioclient_mock.get("https://www.jdn.co.il/comments/feed/", content=fixture("emess.xml"), headers={"Content-Type": RSS})
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": _options(result)[0]})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_moved_feed_homepage_is_feed(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(FEED_URL, status=410)
    aioclient_mock.get("https://www.jdn.co.il/", content=fixture("jdn.xml"), headers={"Content-Type": RSS})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["step_id"] == "moved"
    assert _options(result) == ["https://www.jdn.co.il/"]


async def test_huge_feed_is_truncated(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """פיד מעל התקרה (פודקאסט של 20MB) נקרא עד התקרה במקום להיכשל."""
    aioclient_mock.get(FEED_URL, content=fixture("jdn.xml"), headers={"Content-Type": RSS})
    result = await _start(hass)
    with patch("custom_components.news_card.config_flow.FEED_MAX_BYTES", 20_000), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "JDN"


async def test_invalid_url(hass: HomeAssistant) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "ftp://x"})
    assert result["errors"] == {"base": "invalid_url"}


async def test_already_configured(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "https://WWW.jdn.co.il/feed"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_redirect_to_configured_feed(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry) -> None:
    """כתובת שמפנה לפיד שכבר קיים נחסמת לפי הכתובת הסופית."""
    entry.add_to_hass(hass)

    async def redirect(method, url, data):  # noqa: ARG001
        from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse
        from yarl import URL

        return AiohttpClientMockResponse("get", URL(FEED_URL), response=fixture("jdn.xml"), headers={"Content-Type": RSS})

    aioclient_mock.get("https://short.example/f", side_effect=redirect)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "https://short.example/f"})
    assert result["reason"] == "already_configured"


async def test_feedreader_urls_offered(hass: HomeAssistant) -> None:
    MockConfigEntry(domain="feedreader", data={"url": "https://fr.example/rss"}).add_to_hass(hass)
    result = await _start(hass)
    selector = result["data_schema"].schema["url"]
    assert "https://fr.example/rss" in selector.config["options"]


async def test_reconfigure(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry) -> None:
    new = "https://www.emess.co.il/feed"
    aioclient_mock.get(new, content=fixture("emess.xml"), headers={"Content-Type": RSS})
    result = await loaded.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "ftp://bad"})
    assert result["errors"] == {"base": "invalid_url"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": new})
    assert result["reason"] == "reconfigure_successful"
    assert loaded.data["url"] == new
    assert loaded.unique_id == normalize_url(new)


async def test_reconfigure_duplicate(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry) -> None:
    other = MockConfigEntry(domain=DOMAIN, unique_id="https://other.example/rss", data={"url": "https://other.example/rss"})
    other.add_to_hass(hass)
    aioclient_mock.get("https://other.example/rss", content=fixture("bozo.xml"))
    result = await loaded.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "https://other.example/rss"})
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(loaded.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "scan_interval": 30.0,
            "max_entries": 5.0,
            "proxy_images": False,
            "fetch_page_images": False,
            "verify_ssl": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded.options["scan_interval"] == 30
    assert loaded.options["max_entries"] == 5
    assert loaded.options["keywords"] == ""
    assert loaded.options["user_agent"] == ""
    await hass.async_block_till_done()
    assert len(loaded.runtime_data.data.entries) == 5


async def test_options_user_agent(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    base = {"scan_interval": 15, "max_entries": 30, "proxy_images": True, "fetch_page_images": False, "verify_ssl": True}
    result = await hass.config_entries.options.async_init(loaded.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {**base, "user_agent": "x" * 513})
    assert result["errors"] == {"user_agent": "invalid_user_agent"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {**base, "user_agent": " MyReader/1.0 "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded.options["user_agent"] == "MyReader/1.0"
    await hass.async_block_till_done()
    assert loaded.runtime_data.user_agent == "MyReader/1.0"
