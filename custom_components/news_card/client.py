"""הורדת פידים, דפים ותמונות עם מגבלות גודל וזמן ומיפוי שגיאות למפתחות תרגום."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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
    """כשל רשת. reason הוא מפתח תרגום; retry_after בשניות, כשהשרת ביקש להמתין."""

    def __init__(self, reason: str, status: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(f"{reason} ({status})" if status else reason)
        self.reason = reason
        self.status = status
        self.retry_after = retry_after


# אתגר JavaScript של שירות הגנה (Cloudflare, DataDome, Imperva): רק דפדפן אמיתי עובר, גם עם User-Agent של דפדפן
CHALLENGE_HEADERS = ("x-datadome", "x-iinfo")
RETRY_AFTER_MAX = 24 * 3600

# סירובים שבהם User-Agent אחר יכול לעזור
FALLBACK_REASONS = ("refused", "rate_limited")
USER_AGENT_BROWSER = "browser"
USER_AGENT_MAX = 512
# ponytail: גרסת Chrome קבועה; לעדכן מדי פעם, אתרים מחמירים דוחים גרסאות ישנות מאוד
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def resolve_user_agent(option: str | None) -> str | None:
    """ערך ההגדרה ל-User-Agent בפועל: ריק = אין, "browser" = Chrome עדכני, אחרת הטקסט עצמו."""
    option = (option or "").strip()
    return BROWSER_USER_AGENT if option == USER_AGENT_BROWSER else option or None


def valid_user_agent(option: str) -> bool:
    """טקסט שאפשר לשלוח ככותרת: מודפס, בלי שורות חדשות, באורך סביר."""
    return len(option) <= USER_AGENT_MAX and option.isprintable()


def _retry_after(value: str | None) -> int | None:
    """Retry-After בשניות: מספר או תאריך HTTP."""
    if not value:
        return None
    try:
        seconds = int(value) if value.strip().isdigit() else int(
            (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        )
    except (TypeError, ValueError):
        return None
    return min(max(seconds, 0), RETRY_AFTER_MAX)


def http_error(resp: aiohttp.ClientResponse) -> FetchError:
    """ממפה תשובת שגיאה לסיבה שאפשר להסביר למשתמש."""
    status = resp.status
    challenge = resp.headers.get("cf-mitigated") == "challenge" or any(h in resp.headers for h in CHALLENGE_HEADERS)
    if challenge and status in (401, 403, 405, 429, 503):
        reason = "blocked"
    elif status in (403, 406):
        # 406 עם Accept שכולל */* הוא כמעט תמיד חומת אש (WAF), לא בעיית פורמט
        reason = "refused"
    elif status in (401, 407):
        reason = "auth_required"
    elif status in (404, 410):
        reason = "not_found"
    elif status == 429:
        reason = "rate_limited"
    elif status >= 500:
        reason = "server_error"
    else:
        reason = "http_error"
    return FetchError(reason, status, _retry_after(resp.headers.get("Retry-After")))


@dataclass
class FetchResult:
    """תוצאת הורדה. content הוא None כשהשרת ענה 304."""

    status: int
    content: bytes | None
    content_type: str | None
    etag: str | None
    modified: str | None
    url: str
    charset: str | None = None


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
    user_agent: str | None = None,
) -> FetchResult:
    """הורדה עם תקרת גודל. truncate=True חותך במקום להיכשל (לדפי HTML)."""
    headers = {"User-Agent": user_agent or USER_AGENT, "Accept": accept}
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
                    raise http_error(resp)
                length = int(resp.headers.get("Content-Length") or 0)
                if length > max_bytes and not truncate:
                    raise FetchError("too_large")
                body = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        if truncate:
                            del body[max_bytes:]
                            break
                        raise FetchError("too_large")
                return FetchResult(
                    resp.status,
                    bytes(body),
                    resp.content_type,
                    resp.headers.get("ETag"),
                    resp.headers.get("Last-Modified"),
                    str(resp.url),
                    resp.charset,
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
