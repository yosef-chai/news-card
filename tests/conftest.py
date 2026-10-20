"""כלים משותפים לבדיקות."""

from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.news_card.client import USER_AGENT
from custom_components.news_card.const import DEFAULT_OPTIONS, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://www.jdn.co.il/feed/"
RSS = "application/rss+xml; charset=UTF-8"


def fixture(name: str) -> bytes:
    """קורא קובץ מתיקיית fixtures."""
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


def refuse_default_user_agent(
    aioclient_mock: AiohttpClientMocker,
    url: str,
    content: bytes,
    content_type: str = RSS,
    status: int = 406,
) -> None:
    """אתר שמסרב ל-User-Agent של News Card ועונה לכל אחר. mock_calls נרשם לפני side_effect."""

    async def respond(method, request_url, data):
        if aioclient_mock.mock_calls[-1][3]["User-Agent"] == USER_AGENT:
            return AiohttpClientMockResponse(method, request_url, status=status)
        return AiohttpClientMockResponse(
            method,
            request_url,
            response=content,
            headers={"Content-Type": content_type},
        )

    aioclient_mock.get(url, side_effect=respond)


def user_agents(aioclient_mock: AiohttpClientMocker) -> list[str]:
    """ה-User-Agent של כל בקשה שנשלחה, לפי הסדר."""
    return [call[3]["User-Agent"] for call in aioclient_mock.mock_calls]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest) -> None:
    """מאפשר טעינת custom_components. ה-recorder חייב לקום לפני hass, ולכן הוא קודם."""
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_mock")
    request.getfixturevalue("enable_custom_integrations")


@pytest.fixture(autouse=True)
async def finish_background_tasks(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[None]:
    """בסוף כל בדיקה מחכים לריענון שרץ ברקע אחרי טעינה מחדש, כדי שלא יישאר טיימר פתוח."""
    yield
    if "hass" in request.fixturenames:
        hass: HomeAssistant = request.getfixturevalue("hass")
        await hass.async_block_till_done(wait_background_tasks=True)


@pytest.fixture(autouse=True)
def public_dns() -> Generator[None]:
    """בבדיקות אין DNS: כל שם מארח נחשב ציבורי. כתובות IP מפורשות נבדקות כרגיל."""

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    with patch("custom_components.news_card.client._async_resolve", resolve):
        yield


@pytest.fixture
def entry() -> MockConfigEntry:
    """רשומת פיד JDN שעוד לא נוספה ל-hass."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="JDN",
        unique_id="https://www.jdn.co.il/feed",
        data={"url": FEED_URL},
        options={**DEFAULT_OPTIONS, "fetch_page_images": False, "keywords": "תורה"},
    )


@pytest.fixture
async def loaded(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry
) -> MockConfigEntry:
    """רשומה טעונה עם פיד JDN."""
    aioclient_mock.get(
        FEED_URL, content=fixture("jdn.xml"), headers={"Content-Type": RSS}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
