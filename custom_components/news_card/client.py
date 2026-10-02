"""הורדת פידים, דפים ותמונות עם מגבלות גודל וזמן ומיפוי שגיאות למפתחות תרגום."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
import ssl

import aiohttp

from .const import FETCH_TIMEOUT

USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsCard/1.0; Home Assistant; "
    "+https://github.com/yosef-chai/news-card)"
)
ACCEPT_FEED = (
    "application/rss+xml, application/atom+xml, application/feed+json, "
    "application/xml;q=0.9, text/xml;q=0.9, text/html;q=0.7, */*;q=0.5"
)


class FetchError(Exception):
    """כשל רשת. reason הוא מפתח תרגום."""

    def __init__(self, reason: str, status: int | None = None) -> None:
        super().__init__(f"{reason} ({status})" if status else reason)
        self.reason = reason
        self.status = status


@dataclass
class FetchResult:
    """תוצאת הורדה. content הוא None כשהשרת ענה 304."""

    status: int
    content: bytes | None
    content_type: str | None
    etag: str | None
    modified: str | None
    url: str


async def async_fetch(
    session: aiohttp.ClientSession,
    url: str,
    *,
    max_bytes: int,
    accept: str = ACCEPT_FEED,
    etag: str | None = None,
    modified: str | None = None,
    truncate: bool = False,
    timeout: float = FETCH_TIMEOUT,
) -> FetchResult:
    """הורדה עם תקרת גודל. truncate=True חותך במקום להיכשל (לדפי HTML)."""
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        async with asyncio.timeout(timeout):
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status == 304:
                    return FetchResult(304, None, None, etag, modified, str(resp.url))
                if resp.status >= 400:
                    raise FetchError("http_error", resp.status)
                length = int(resp.headers.get("Content-Length") or 0)
                if length > max_bytes and not truncate:
                    raise FetchError("too_large")
                body = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        if truncate:
                            break
                        raise FetchError("too_large")
                return FetchResult(
                    resp.status,
                    bytes(body),
                    resp.content_type,
                    resp.headers.get("ETag"),
                    resp.headers.get("Last-Modified"),
                    str(resp.url),
                )
    except FetchError:
        raise
    except TimeoutError as err:
        raise FetchError("timeout") from err
    except (aiohttp.ClientSSLError, ssl.SSLError) as err:
        raise FetchError("ssl_error") from err
    except (aiohttp.ClientError, ValueError) as err:
        raise FetchError("cannot_connect") from err


_META = re.compile(r"<meta\b[^>]*>", re.I)
_LINK = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def find_page_image(html: str) -> str | None:
    """תמונת השיתוף של דף: og:image → twitter:image → image_src."""
    found: dict[str, str] = {}
    for tag in _META.findall(html):
        attrs = {m[0].lower(): m[1] or m[2] for m in _ATTR.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image") and attrs.get("content"):
            found.setdefault(key, attrs["content"])
    for tag in _LINK.findall(html):
        attrs = {m[0].lower(): m[1] or m[2] for m in _ATTR.findall(tag)}
        if attrs.get("rel", "").lower() == "image_src" and attrs.get("href"):
            found.setdefault("image_src", attrs["href"])
    for key in ("og:image:secure_url", "og:image", "og:image:url", "twitter:image", "image_src"):
        if key in found:
            return found[key]
    return None
