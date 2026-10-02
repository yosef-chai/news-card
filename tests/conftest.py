"""כלים משותפים לבדיקות."""

from pathlib import Path

import pytest

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.news_card.const import DEFAULT_OPTIONS, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://www.jdn.co.il/feed/"
RSS = "application/rss+xml; charset=UTF-8"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def rss(items: list[tuple[str, str]], title: str = "Test feed") -> bytes:
    """פיד קטן לבדיקות: [(guid, pubDate)]."""
    body = "".join(
        f"<item><title>Item {guid}</title><link>https://example.com/{guid}</link>"
        f"<guid>{guid}</guid><pubDate>{date}</pubDate>"
        f"<description>About {guid}</description></item>"
        for guid, date in items
    )
    return (
        f'<?xml version="1.0"?><rss version="2.0"><channel><title>{title}</title>'
        f"<link>https://example.com/</link>{body}</channel></rss>"
    ).encode()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """מאפשר טעינת custom_components."""


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="JDN",
        unique_id="https://www.jdn.co.il/feed",
        data={"url": FEED_URL},
        options={**DEFAULT_OPTIONS, "fetch_page_images": False, "keywords": "תורה"},
    )


@pytest.fixture
async def loaded(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry) -> MockConfigEntry:
    """רשומה טעונה עם פיד JDN."""
    aioclient_mock.get(FEED_URL, content=fixture("jdn.xml"), headers={"Content-Type": RSS})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
