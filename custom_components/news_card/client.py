"""הורדת פידים, דפים ותמונות עם מגבלות גודל וזמן ומיפוי שגיאות למפתחות תרגום."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import ipaddress
import re
import socket
import ssl
from urllib.parse import urljoin, urlparse

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

    def __init__(
        self, reason: str, status: int | None = None, retry_after: int | None = None
    ) -> None:
        """שומר את הסיבה, הסטטוס וזמן ההמתנה שהשרת ביקש."""
        super().__init__(f"{reason} ({status})" if status else reason)
        self.reason = reason
        self.status = status
        self.retry_after = retry_after


# אתגר JavaScript של שירות הגנה (Cloudflare, DataDome, Imperva): רק דפדפן אמיתי עובר, גם עם User-Agent של דפדפן
CHALLENGE_HEADERS = ("x-datadome", "x-iinfo")
RETRY_AFTER_MAX = 24 * 3600
MAX_REDIRECTS = 5
REDIRECT_STATUSES = (301, 302, 303, 307, 308)

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
        seconds = (
            int(value)
            if value.strip().isdigit()
            else int((parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        )
    except TypeError, ValueError:
        return None
    return min(max(seconds, 0), RETRY_AFTER_MAX)


def http_error(resp: aiohttp.ClientResponse) -> FetchError:
    """ממפה תשובת שגיאה לסיבה שאפשר להסביר למשתמש."""
    status = resp.status
    challenge = resp.headers.get("cf-mitigated") == "challenge" or any(
        h in resp.headers for h in CHALLENGE_HEADERS
    )
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


async def _async_resolve(host: str) -> list[str]:
    """כתובות ה-IP של שם מארח."""
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, None, type=socket.SOCK_STREAM
    )
    return [str(info[4][0]) for info in infos]


async def async_check_public(url: str, allowed_host: str | None = None) -> None:
    """זורק FetchError("not_allowed") לכתובת ברשת המקומית.

    קישורים ותמונות מגיעים מתוכן הפיד, ובלי הבדיקה פיד זדוני יכול לגרום ל-Home Assistant
    לשלוח בקשות לנתב או למכשירים בבית. המארח של הפיד עצמו מותר, כי המשתמש בחר בו.
    """
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not host:
        raise FetchError("not_allowed")
    if allowed_host and host == allowed_host.lower():
        return
    if host == "localhost" or host.endswith(
        (".localhost", ".local", ".internal", ".home.arpa")
    ):
        raise FetchError("not_allowed")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = await _async_resolve(host)
        except OSError as err:
            raise FetchError("cannot_connect") from err
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise FetchError("not_allowed")


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
    stop_at: bytes | None = None,
    public_only: bool = False,
    allowed_host: str | None = None,
) -> FetchResult:
    """הורדה עם תקרת גודל. truncate=True חותך במקום להיכשל (לדפי HTML).

    stop_at: מפסיקים לקרוא כשהטקסט מופיע (בלי הבדל אותיות), למשל </head> בדף כתבה.
    public_only: רק כתובות ציבוריות, כולל בכל הפניה בדרך (לכתובות שמגיעות מתוכן הפיד).
    """
    headers = {"User-Agent": user_agent or USER_AGENT, "Accept": accept}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        async with asyncio.timeout(timeout):
            for _ in range(MAX_REDIRECTS + 1):
                if public_only:
                    await async_check_public(url, allowed_host)
                async with session.get(
                    url, headers=headers, allow_redirects=not public_only
                ) as resp:
                    if (
                        public_only
                        and resp.status in REDIRECT_STATUSES
                        and (location := resp.headers.get("Location"))
                    ):
                        url = urljoin(str(resp.url), location)
                        continue
                    return await _async_read(
                        resp, max_bytes, truncate, stop_at, etag, modified
                    )
    except FetchError:
        raise
    except TimeoutError as err:
        raise FetchError("timeout") from err
    except (aiohttp.ClientSSLError, ssl.SSLError) as err:
        raise FetchError("ssl_error") from err
    except (aiohttp.ClientError, ValueError) as err:
        raise FetchError("cannot_connect") from err
    raise FetchError("cannot_connect")  # יותר מדי הפניות


async def _async_read(
    resp: aiohttp.ClientResponse,
    max_bytes: int,
    truncate: bool,
    stop_at: bytes | None,
    etag: str | None,
    modified: str | None,
) -> FetchResult:
    if resp.status == 304:
        return FetchResult(304, None, None, etag, modified, str(resp.url))
    if resp.status >= 400:
        raise http_error(resp)
    length = int(resp.headers.get("Content-Length") or 0)
    if length > max_bytes and not truncate:
        raise FetchError("too_large")
    body = bytearray()
    marker = stop_at.lower() if stop_at else None
    async for chunk in resp.content.iter_chunked(64 * 1024):
        start = max(0, len(body) - len(marker or b""))
        body.extend(chunk)
        if len(body) > max_bytes:
            if truncate:
                del body[max_bytes:]
                break
            raise FetchError("too_large")
        # בודקים רק את החלק החדש (ועוד כמה בתים מהקודם, למקרה שהסימן נחתך בין שני חלקים)
        if marker and marker in bytes(body[start:]).lower():
            break
    return FetchResult(
        resp.status,
        bytes(body),
        resp.content_type,
        resp.headers.get("ETag"),
        resp.headers.get("Last-Modified"),
        str(resp.url),
        resp.charset,
    )


_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_LINK = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def find_page_image(html: str) -> str | None:
    """תמונת השיתוף של דף: og:image → twitter:image → image_src."""
    found: dict[str, str] = {}
    for tag in _META.findall(html):
        attrs = {m[0].lower(): m[1] or m[2] for m in _ATTR.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key in (
            "og:image",
            "og:image:url",
            "og:image:secure_url",
            "twitter:image",
        ) and attrs.get("content"):
            found.setdefault(key, attrs["content"])
    for tag in _LINK.findall(html):
        attrs = {m[0].lower(): m[1] or m[2] for m in _ATTR.findall(tag)}
        if attrs.get("rel", "").lower() == "image_src" and attrs.get("href"):
            found.setdefault("image_src", attrs["href"])
    for key in (
        "og:image:secure_url",
        "og:image",
        "og:image:url",
        "twitter:image",
        "image_src",
    ):
        if key in found:
            return found[key]
    return None


def extract_page_image(content: bytes, charset: str | None = None) -> str | None:
    """פענוח דף שהורד וחיפוש תמונת השיתוף בו. חוסם (עד PAGE_MAX_BYTES), ולכן רץ ב-executor."""
    try:
        html = content.decode(charset or "utf-8", "replace")
    except LookupError:  # קידוד לא מוכר בכותרת Content-Type
        html = content.decode("utf-8", "replace")
    return find_page_image(html)
