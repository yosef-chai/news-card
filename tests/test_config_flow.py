"""בדיקות זרימת ההגדרה, ההגדרה מחדש והאפשרויות."""

import asyncio
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

from .conftest import FEED_URL, RSS, fixture

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
    assert result["step_id"] == "discovery"
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_discovery_step_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get("https://www.jdn.co.il/", content=fixture("page.html"), headers={"Content-Type": "text/html"})
    aioclient_mock.get(FEED_URL, status=500)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "https://www.jdn.co.il/"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["errors"] == {"base": "http_error"}
    assert result["description_placeholders"]["status"] == "500"


@pytest.mark.parametrize(
    ("mock", "error"),
    [
        ({"exc": asyncio.TimeoutError()}, "timeout"),
        ({"exc": aiohttp.ClientError()}, "cannot_connect"),
        ({"status": 404}, "http_error"),
        ({"content": b"plain text"}, "invalid_feed"),
        ({"content": b"<html><body>no feeds</body></html>", "headers": {"Content-Type": "text/html"}}, "not_a_feed"),
        ({"content": b"x", "headers": {"Content-Length": str(20 * 1024 * 1024)}}, "too_large"),
    ],
)
async def test_user_flow_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock: dict, error: str) -> None:
    aioclient_mock.get(FEED_URL, **mock)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": FEED_URL})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


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
    await hass.async_block_till_done()
    assert len(loaded.runtime_data.data.entries) == 5
