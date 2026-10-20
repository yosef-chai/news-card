"""פרוקסי תמונות: מגיש רק תמונות שמופיעות בנתוני הפיד, עם מטמון ותקרת גודל.

פותר תמונות http בלוח https וחסימות hotlink (לא נשלח Referer).
"""

import asyncio
from collections import OrderedDict
from http import HTTPStatus
import logging
import time
from urllib.parse import urlparse

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .client import FetchError, async_fetch
from .const import DOMAIN, IMAGE_MAX_BYTES, IMAGE_PROXY_URL
from .coordinator import NewsCardCoordinator
from .feed import make_id

_LOGGER = logging.getLogger(__name__)

CACHE_MAX_ITEMS = 200
# הדפדפן שומר כל תמונה ליום (immutable); המטמון כאן רק חוסך הורדה כשכמה מסכים פותחים את אותו לוח
CACHE_MAX_BYTES = 16 * 1024 * 1024
# תמונה שנכשלה לא מורדת שוב בכל פתיחה של הלוח
FAILURE_TTL = 600.0
FAILURE_MAX_ITEMS = 500
ACCEPT_IMAGE = "image/avif,image/webp,image/apng,image/*;q=0.8"
# SVG יכול להכיל סקריפט שירוץ במקור של HA, ולכן לא מוגש דרך הפרוקסי
BLOCKED_TYPES = ("image/svg+xml",)


def sniff_image(body: bytes) -> str | None:
    """זיהוי סוג תמונה לפי החתימה בתחילת הקובץ."""
    if body.startswith(bytes.fromhex("ffd8ff")):
        return "image/jpeg"
    if body.startswith(bytes.fromhex("89504e47")):
        return "image/png"
    if body.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    if body[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    return None


class NewsCardImageView(HomeAssistantView):
    """GET /api/news_card/image/{entry_id}/{image_id}."""

    url = IMAGE_PROXY_URL
    name = f"api:{DOMAIN}:image"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """מטמון תמונות, הורדות שבדרך וכישלונות אחרונים."""
        self.hass = hass
        self._cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
        self._cache_bytes = 0
        self._inflight: dict[str, asyncio.Future[tuple[bytes, str]]] = {}
        # כתובת → (עד מתי, האם סוג קובץ לא נתמך)
        self._failed: dict[str, tuple[float, bool]] = {}

    async def get(
        self, request: web.Request, entry_id: str, image_id: str
    ) -> web.Response:
        """מגיש תמונה של כתבה שמופיעה בפיד."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        coordinator = getattr(entry, "runtime_data", None) if entry else None
        if not isinstance(coordinator, NewsCardCoordinator) or not coordinator.data:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        url = next(
            (
                e["image"]
                for e in coordinator.data.entries
                if e["image"] and make_id(e["image"]) == image_id
            ),
            None,
        )
        if url is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)

        try:
            body, content_type = await self._get_image(coordinator, url)
        except FetchError as err:
            _LOGGER.debug("Image proxy failed for %s: %s", url, err)
            return web.Response(status=HTTPStatus.BAD_GATEWAY)
        except ValueError:
            return web.Response(status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        return web.Response(
            body=body,
            content_type=content_type,
            headers={
                "Cache-Control": "private, max-age=86400, immutable",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'",
            },
        )

    async def _get_image(
        self, coordinator: NewsCardCoordinator, url: str
    ) -> tuple[bytes, str]:
        if url in self._cache:
            self._cache.move_to_end(url)
            return self._cache[url]
        if failed := self._failed.get(url):
            if failed[0] > time.monotonic():
                raise ValueError(url) if failed[1] else FetchError("recent_failure")
            del self._failed[url]
        if url in self._inflight:
            return await asyncio.shield(self._inflight[url])
        future: asyncio.Future[tuple[bytes, str]] = self.hass.loop.create_future()
        self._inflight[url] = future
        try:
            item = await self._async_download(coordinator, url)
        except Exception as err:
            self._failed[url] = (
                time.monotonic() + FAILURE_TTL,
                isinstance(err, ValueError),
            )
            while len(self._failed) > FAILURE_MAX_ITEMS:
                del self._failed[next(iter(self._failed))]
            future.set_exception(err)
            future.exception()  # מסמן שהחריגה נקראה, כדי שלא תירשם אזהרה
            raise
        else:
            self._remember(url, item)
            future.set_result(item)
            return item
        finally:
            self._inflight.pop(url, None)
            if not future.done():
                # הבקשה הראשונה בוטלה (הדפדפן נסגר): גם הממתינים לאותה תמונה משתחררים
                future.cancel()

    @staticmethod
    async def _async_download(
        coordinator: NewsCardCoordinator, url: str
    ) -> tuple[bytes, str]:
        """הורדת התמונה ובדיקת הסוג. ValueError לקובץ שאינו תמונה נתמכת."""
        result = await async_fetch(
            coordinator.session,
            url,
            max_bytes=IMAGE_MAX_BYTES,
            accept=ACCEPT_IMAGE,
            timeout=15,
            # הכתובת באה מתוכן הפיד: לא לפנות לרשת המקומית
            public_only=True,
            allowed_host=urlparse(coordinator.url).hostname,
        )
        body = result.content or b""
        content_type = (result.content_type or "").lower()
        if not content_type.startswith("image/"):
            # שרתים רבים (למשל CNN) מחזירים application/octet-stream
            content_type = sniff_image(body) or content_type
        if not content_type.startswith("image/") or content_type in BLOCKED_TYPES:
            raise ValueError(content_type)
        return body, content_type

    def _remember(self, url: str, item: tuple[bytes, str]) -> None:
        self._cache[url] = item
        self._cache_bytes += len(item[0])
        while len(self._cache) > CACHE_MAX_ITEMS or self._cache_bytes > CACHE_MAX_BYTES:
            _, (old, _) = self._cache.popitem(last=False)
            self._cache_bytes -= len(old)
