"""ניתוח ונרמול פידים (RSS / Atom / RDF / JSON Feed) לחוזה נתונים אחיד.

המודול טהור: בלי ייבוא מ-Home Assistant, כדי שאפשר יהיה לבדוק אותו לבד.
"""

from __future__ import annotations

import calendar
import codecs
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import logging
import re
from typing import Any, TypedDict, override
from urllib.parse import parse_qs, urljoin, urlparse

import feedparser

_LOGGER = logging.getLogger(__name__)

SUMMARY_MAX = 2000
TITLE_MAX = 300
# הפרש שעונים סביר בין השרת לבינינו; מעבר לזה התאריך נחשב עתידי
FUTURE_TOLERANCE = timedelta(minutes=10)
TITLE_FROM_SUMMARY_MAX = 100
IMAGE_EXT = re.compile(r"\.(jpe?g|png|gif|webp|avif|bmp|svg)(\?|#|$)", re.I)
NOT_IMAGE_EXT = re.compile(
    r"\.(mp3|m4a|aac|ogg|oga|opus|wav|flac|mp4|m4v|mov|webm|mkv|avi|m3u8|mpd|pdf|zip|html?|php)(\?|#|$)", re.I
)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")
# תמונות שהן לא תמונת כתבה: פיקסלי מעקב, אימוג'י, אווטרים
JUNK_IMAGE = re.compile(
    r"(s\.w\.org/images/core/emoji|gravatar\.com|feedburner|/pixel|tracking|"
    r"doubleclick|/emoji/|spacer\.gif|blank\.gif|1x1|"
    r"(twitter|facebook|linkedin|whatsapp|share|social)[-_]?(icon|button|logo))",
    re.I,
)
FEED_LINK_TYPES = {
    "application/rss+xml",
    "application/atom+xml",
    "application/rdf+xml",
    "application/feed+json",
    "application/json+feed",
    "text/xml",
    "application/xml",
}
# קישורי <a> שנראים כמו פיד, לאתרים שלא מצהירים על פיד ב-<link> (ynet, וואלה, מעריב, הארץ)
FEED_LABEL = re.compile(r"\b(?:rss|atom)\b", re.I)
FEED_PATH = re.compile(r"(?:^|[/._=-])(?:rss\d?|feeds?|atom|rdf)(?:[/._&=?-]|$)", re.I)
PAGE_PATH = re.compile(r"\.(?:s?html?|jpe?g|png|gif|webp|svg|pdf|mp[34])$", re.I)
LABEL_MAX = 40
LINKS_MAX = 50
# זיהוי לפי התוכן ולא לפי Content-Type: שרתים רבים מגישים פיד כ-text/html או application/json
SNIFF_BYTES = 16 * 1024
_COMMENT = re.compile(rb"<!--.*?-->", re.S)
_FEED_ROOT = re.compile(rb"<(?:[\w.-]+:)?(?:rss|feed|RDF)[\s>]", re.I)
_HTML_START = re.compile(rb"<(?:html[\s>]|!doctype\s+html)", re.I)
_XML_DECL = re.compile(rb"<\?xml\s")
_XML_ENCODING = re.compile(rb"""<\?xml[^>]*?encoding\s*=\s*["']([\w.:-]+)["']""")
# ברירות מחדל של שרתים, שגויות לעיתים קרובות; קידוד ספציפי גובר עליהן
GENERIC_CHARSETS = {"iso8859-1", "ascii"}
# מייל או כתובת פרופיל שמוצמדים לשם הכותב (RSS, Flickr)
CONTACT = re.compile(r"\(?(?:[\w.+-]+@[\w-]+(?:\.[\w-]+)+|https?://[^\s)]+)\)?")
AUTHOR_MAX = 100
# שורות סיום שמערכות ניהול תוכן מוסיפות לתקציר (WordPress, Slashdot, "המשך קריאה")
READ_MORE = r"(?:continue reading|read more|read the full (?:story|article)|keep reading|להמשך קריאה|המשך קריאה|לכתבה המלאה|קרא עוד|קראו עוד)"
BOILERPLATE = re.compile(
    rf"^(?:the post .+ (?:appeared first|first appeared) on .+|read more of this story at slashdot\.?|{READ_MORE}\b.{{0,120}})$",
    re.I,
)
TEXT_TAIL = re.compile(rf"(?:\s*\[(?:…|\.\.\.)\]|\s+{READ_MORE}\W*)$", re.I)
# HTML שקודד פעמיים (&lt;p&gt;, &amp;quot;) נשאר עם תגיות או ישויות אחרי פענוח אחד
ESCAPED_HTML = re.compile(
    r"&(?:#\d+|#x[0-9a-f]+|[a-z]{2,8});|<(?:p|br|img|a|div|span|strong|em|b|i|ul|ol|li|h[1-6]|figure|table)\b[^>]*>",
    re.I,
)
# אתרים שהקישור בפיד שלהם הוא הפניה עם כתובת הכתבה בפרמטר url
REDIRECT_HOSTS = {"www.bing.com", "bing.com"}
# שגיאת XML נפוצה שמפילה את feedparser לגמרי: מאפיינים צמודים בלי רווח ("a="1"b="2")
GLUED_ATTRS = re.compile(rb"""(=\s*(?:"[^"<>]*"|'[^'<>]*'))(?=[A-Za-z_][\w:.-]*\s*=)""")


class NewsMedia(TypedDict):
    """קובץ שמע/וידאו מצורף."""

    url: str
    type: str


class NewsEntry(TypedDict):
    """פריט חדשות אחיד. כל השכבות (פעולה, WebSocket, אירועים, כרטיס) משתמשות בו."""

    id: str
    title: str
    link: str | None
    published: str | None
    published_estimated: bool
    summary: str
    author: str | None
    source: str | None
    categories: list[str]
    image: str | None
    image_proxy: str | None
    media: NewsMedia | None


class FeedInfo(TypedDict):
    """פרטי הפיד עצמו."""

    title: str
    link: str | None
    icon: str | None


@dataclass
class ParsedFeed:
    """תוצאת ניתוח."""

    info: FeedInfo
    entries: list[NewsEntry]


class FeedError(Exception):
    """הפיד לא נקרא. reason הוא מפתח תרגום; discovered הם פידים שהדף מצהיר עליהם, links קישורים שנראים כמו פיד."""

    def __init__(
        self,
        reason: str,
        discovered: list[tuple[str, str]] | None = None,
        links: list[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.discovered = discovered or []
        self.links = links or []


class _TextExtractor(HTMLParser):
    """ממיר HTML לטקסט נקי ושומר מעברי שורה של בלוקים."""

    BLOCK = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
    SKIP = {"script", "style", "noscript", "iframe", "figcaption"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    @override
    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    @override
    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(value: str | None) -> str:
    """טקסט נקי מ-HTML: בלי תגיות, ישויות מפוענחות, רווחים מנורמלים. מפענח גם HTML שקודד פעמיים."""
    text = _html_to_text(value)
    return _html_to_text(text) if ESCAPED_HTML.search(text) else text


def _html_to_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:  # noqa: BLE001 - HTML שבור לא יפיל את הפיד
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def truncate(text: str, limit: int) -> str:
    """קיצור במילה שלמה."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:-–—")
    return f"{cut}…"


def abs_url(url: str | None, base: str | None) -> str | None:
    """כתובת מוחלטת ב-http/https בלבד."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if url.startswith("//"):
        url = f"https:{url}"
    full = urljoin(base or "", url)
    return full if urlparse(full).scheme in ("http", "https") else None


def _is_image(url: str | None, mime: str | None = None, medium: str | None = None) -> bool | None:
    """None כשאין שום רמז לסוג (בלי type, בלי medium ובלי סיומת מוכרת)."""
    if not url:
        return False
    if medium:
        return medium == "image"
    if mime:
        return mime.startswith("image/")
    if IMAGE_EXT.search(url):
        return True
    return False if NOT_IMAGE_EXT.search(url) else None


def _first_img(html: str | None, base: str | None) -> str | None:
    """התמונה הראשונה שאינה זבל מתוך HTML, כולל lazy-load ו-HTML שקודד פעמיים."""
    if not html:
        return None
    if "&lt;img" in html and not IMG_TAG.search(html):
        html = unescape(html)
    for tag in IMG_TAG.findall(html):
        attrs = {m[0].lower(): m[1] or m[2] or m[3] for m in ATTR.findall(tag)}
        if attrs.get("width") in ("0", "1") or attrs.get("height") in ("0", "1"):
            continue
        for key in ("data-src", "data-lazy-src", "data-original", "src"):
            src = attrs.get(key)
            if src and not src.startswith("data:") and not JUNK_IMAGE.search(src):
                return abs_url(src, base)
    return None


def _size(item: dict[str, Any]) -> int:
    try:
        return int(item.get("width") or 0) * int(item.get("height") or 0)
    except (TypeError, ValueError):
        return 0


def _entry_image(entry: Any, base: str | None) -> str | None:
    """סדר עדיפויות: media:content → media:thumbnail → itunes:image → <image> → enclosure → <img>."""
    media = [m for m in entry.get("media_content") or [] if isinstance(m, dict)]
    images = [m for m in media if _is_image(m.get("url"), m.get("type"), m.get("medium"))]
    if images:
        return abs_url(max(images, key=_size)["url"], base)
    thumbs = [t for t in entry.get("media_thumbnail") or [] if t.get("url")]
    if thumbs:
        return abs_url(max(thumbs, key=_size)["url"], base)
    itunes = entry.get("image")
    if isinstance(itunes, dict) and itunes.get("href"):
        return abs_url(itunes["href"], base)
    # <image><url>…</url></image> בתוך פריט: feedparser שם את הכתובת ב-href של הפריט.
    # רק עם סיומת של תמונה, כי גם <url> רגיל (קישור לכתבה) נשמר שם
    if _is_image(href := entry.get("href")) is True:
        return abs_url(href, base)
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and _is_image(link.get("href"), link.get("type")):
            return abs_url(link["href"], base)
    # media:content בלי type, בלי medium ובלי סיומת: כמעט תמיד תמונה מ-CDN; <News:Image> של Bing
    unknown = [m["url"] for m in media if _is_image(m.get("url"), m.get("type"), m.get("medium")) is None]
    for candidate in [*unknown, entry.get("news_image")]:
        if _is_image(candidate) is not False:
            return abs_url(candidate, base)
    for content in entry.get("content") or []:
        if found := _first_img(content.get("value"), base):
            return found
    return _first_img(entry.get("summary"), base)


def _unwrap_redirect(link: str | None) -> str | None:
    """קישור הפניה (Bing News) → כתובת הכתבה עצמה, כדי שגם תמונת הדף תימצא."""
    parts = urlparse(link or "")
    if parts.netloc in REDIRECT_HOSTS:
        return abs_url(parse_qs(parts.query).get("url", [""])[0], None) or link
    return link


def _entry_media(entry: Any, base: str | None) -> NewsMedia | None:
    for link in entry.get("links") or []:
        mime = (link.get("type") or "").lower()
        if link.get("rel") == "enclosure" and mime.startswith(("audio/", "video/")):
            if url := abs_url(link.get("href"), base):
                return {"url": url, "type": mime}
    return None


def _iso(struct: Any) -> str | None:
    """struct_time של feedparser (תמיד UTC) → ISO."""
    if not struct:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(struct), UTC).isoformat()
    except (OverflowError, TypeError, ValueError):
        return None


def _iso_text(value: Any) -> str | None:
    """תאריך ISO-8601 (JSON Feed). תאריך בלי אזור זמן נחשב UTC."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _author_name(raw: str) -> str:
    """שם בלי מייל או קישור לפרופיל. כותב שהוא רק קישור לפרופיל (Lemmy) → שם המשתמש מהקישור."""
    text = html_to_text(raw)
    if text.startswith(("http://", "https://")) and " " not in text:
        return urlparse(text).path.rstrip("/").rsplit("/", 1)[-1]
    return CONTACT.sub("", text).strip(" ,()")


def _author(entry: Any) -> str | None:
    """שמות הכותבים בלי מייל (ב-RSS הכותב הוא מייל, ו-feedparser מצרף אותו לשם)."""
    names = [a.get("name") for a in entry.get("authors") or [] if isinstance(a, dict)]
    clean = (_author_name(n) for n in names or [entry.get("author")] if isinstance(n, str))
    return truncate(", ".join(dict.fromkeys(n for n in clean if n)), AUTHOR_MAX) or None


def _categories(entry: Any) -> list[str]:
    """תוויות קריאות: label לפני term, בלי term שהוא כתובת (סכמות של Atom)."""
    found = (
        html_to_text(t.get("label") or t.get("term"))
        for t in entry.get("tags") or []
        if isinstance(t, dict)
    )
    return list(dict.fromkeys(c for c in found if c and "://" not in c))


def make_id(*candidates: Any) -> str:
    """מזהה יציב וקצר."""
    raw = next((str(c) for c in candidates if c), "")
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _clean_title(title: str, source: str | None) -> str:
    """שורה אחת בלי רווחים כפולים ובלי סיומת " - מקור" (Google News)."""
    title = " ".join(title.split())
    if source and title.endswith(f" - {source}") and len(title) > len(source) + 3:
        title = title[: -len(source) - 3].rstrip()
    return truncate(title, TITLE_MAX)


def _clean_summary(text: str) -> str:
    """בלי שורות הסיום הקבועות של מערכות התוכן; "[…]" או "Read more" בסוף הופכים ל-…"""
    lines = text.split("\n")
    while lines and (not lines[-1] or BOILERPLATE.match(lines[-1])):
        lines.pop()
    return TEXT_TAIL.sub("…", "\n".join(lines))


def _build_entry(
    *,
    raw_id: Any,
    title: str,
    link: str | None,
    published: str | None,
    summary_html: str | None,
    author: str | None,
    source: str | None,
    categories: list[str],
    image: str | None,
    media: NewsMedia | None,
) -> NewsEntry:
    summary = _clean_summary(html_to_text(summary_html))
    title = _clean_title(html_to_text(title), source)
    if not title:
        # פוסט בלי כותרת (Mastodon, Bluesky): תחילת הטקסט, והתקציר נשאר רק אם יש בו יותר
        flat = " ".join(summary.split())
        title = truncate(flat, TITLE_FROM_SUMMARY_MAX)
        if title == flat:
            summary = ""
    # Google News: התקציר הוא רק הכותרת + שם המקור
    elif summary == title or summary.startswith(title):
        summary = summary[len(title):].strip()
        if not summary or summary == source:
            summary = ""
    return {
        "id": make_id(raw_id, link, title),
        "title": title,
        "link": link,
        "published": published,
        "published_estimated": False,
        "summary": truncate(summary, SUMMARY_MAX),
        "author": author,
        "source": source,
        "categories": categories[:10],
        "image": image,
        "image_proxy": None,
        "media": media,
    }


def _raw_date(entry: Any) -> Any:
    # dict.get עוקף את המיפוי הישן של feedparser מ-updated ל-published (ואת האזהרה שלו)
    return dict.get(entry, "published_parsed") or dict.get(entry, "updated_parsed") or dict.get(entry, "created_parsed")


def _from_feedparser(parsed: Any, url: str, limit: int) -> ParsedFeed:
    feed = parsed.get("feed", {})
    feed_link = abs_url(feed.get("link"), url) or f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
    feed_title = html_to_text(feed.get("title")) or urlparse(url).netloc
    icon = None
    if isinstance(feed.get("image"), dict):
        icon = abs_url(feed["image"].get("href"), url)
    icon = icon or abs_url(feed.get("icon"), url) or abs_url(feed.get("logo"), url)

    # פודקאסט עם אלפי פרקים: בונים רק את החדשים (פי 2 מהנדרש, למקרה של כפילויות)
    raw = parsed.get("entries", [])
    if all(_raw_date(e) for e in raw):
        raw = sorted(raw, key=_raw_date, reverse=True)
    entries: list[NewsEntry] = []
    for entry in raw[: limit * 2]:
        try:
            base = entry.get("link") or feed_link
            link = abs_url(entry.get("link"), feed_link)
            if not link:
                alt = next(
                    (lk.get("href") for lk in entry.get("links") or [] if lk.get("rel") == "alternate"),
                    None,
                )
                guid = entry.get("id")
                link = abs_url(alt, feed_link) or (
                    guid if isinstance(guid, str) and guid.startswith(("http://", "https://")) else None
                )
            source_obj = entry.get("source")
            source = html_to_text(source_obj.get("title")) if isinstance(source_obj, dict) else ""
            source = source or html_to_text(entry.get("news_source"))  # Bing News
            content = entry.get("content") or []
            summary_html = entry.get("summary") or (content[0].get("value") if content else "")
            if not summary_html and entry.get("media_description"):
                summary_html = entry.get("media_description")
            media = _entry_media(entry, base)
            entries.append(
                _build_entry(
                    raw_id=entry.get("id"),
                    title=entry.get("title") or "",
                    # פרק בפודקאסט בלי דף משלו: קישור לקובץ השמע עדיף על דף התוכנית
                    link=_unwrap_redirect(link) or (media["url"] if media else None) or feed_link,
                    published=_iso(_raw_date(entry)),
                    summary_html=summary_html,
                    author=_author(entry),
                    source=source or feed_title,
                    categories=_categories(entry),
                    # פרק בפודקאסט בלי תמונה משלו מקבל את תמונת התוכנית
                    image=_entry_image(entry, base) or (icon if media else None),
                    media=media,
                )
            )
        except Exception:  # noqa: BLE001 - פריט שבור לא יפיל את כל הפיד
            _LOGGER.debug("Skipping broken entry in %s", url, exc_info=True)
    return ParsedFeed({"title": feed_title, "link": feed_link, "icon": icon}, entries)


def _from_json_feed(data: dict[str, Any], url: str) -> ParsedFeed:
    feed_link = abs_url(data.get("home_page_url"), url) or url
    feed_title = html_to_text(data.get("title")) or urlparse(url).netloc
    # 1.1: authors (גם ברמת הפיד, למי שאין לו), 1.0: author
    feed_authors = data.get("authors") or ([data["author"]] if data.get("author") else [])
    entries: list[NewsEntry] = []
    for item in data.get("items") or []:
        try:
            if not isinstance(item, dict):
                continue
            authors = item.get("authors") or ([item["author"]] if item.get("author") else feed_authors)
            media = next(
                (
                    NewsMedia(url=u, type=a.get("mime_type", ""))
                    for a in item.get("attachments") or []
                    if (a.get("mime_type") or "").startswith(("audio/", "video/"))
                    and (u := abs_url(a.get("url"), feed_link))
                ),
                None,
            )
            html = item.get("content_html") or ""
            entries.append(
                _build_entry(
                    raw_id=item.get("id"),
                    title=item.get("title") or "",
                    link=abs_url(item.get("url") or item.get("external_url"), feed_link) or feed_link,
                    published=_iso_text(item.get("date_published") or item.get("date_modified")),
                    summary_html=item.get("summary") or html or item.get("content_text"),
                    author=_author({"authors": authors}),
                    source=feed_title,
                    categories=[t for t in item.get("tags") or [] if isinstance(t, str)],
                    image=abs_url(item.get("image") or item.get("banner_image"), feed_link)
                    or _first_img(html, feed_link),
                    media=media,
                )
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Skipping broken JSON Feed item in %s", url, exc_info=True)
    icon = abs_url(data.get("icon") or data.get("favicon"), url)
    return ParsedFeed({"title": feed_title, "link": feed_link, "icon": icon}, entries)


class _PageScanner(HTMLParser):
    """פידים שהדף מצהיר עליהם (<link rel="alternate">) וכל קישורי <a> עם הטקסט שלהם."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.feeds: list[tuple[str, str]] = []
        self.anchors: list[tuple[str, str]] = []
        self._anchor: list[str] | None = None

    @override
    def handle_starttag(self, tag: str, attrs: Any) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "link":
            rel = a.get("rel", "").lower().split()
            mime = a.get("type", "").lower().split(";")[0].strip()
            # JSON Feed 1.0 הוצהר כ-application/json, כמו גם קישורי wp-json ו-oEmbed שאינם פיד
            href = a.get("href", "")
            json_feed = mime == "application/json" and "feed" in f"{href} {a.get('title')}".lower() and "wp-json" not in href
            if "alternate" in rel and (mime in FEED_LINK_TYPES or json_feed) and href:
                self.feeds.append((href, a.get("title", "")))
        elif tag == "a" and a.get("href"):
            self._anchor = [a["href"]]

    @override
    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor.append(data)

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor:
            href, *text = self._anchor
            self.anchors.append((href, " ".join("".join(text).split())))
            self._anchor = None


def _is_feed_link(url: str, label: str, host: str) -> bool:
    """קישור שנראה כמו פיד: טקסט "RSS"/"Atom", או נתיב באתר עם rss/feed/atom שאינו דף HTML של כתבה."""
    if len(label) <= LABEL_MAX and FEED_LABEL.search(label):
        return True
    parts = urlparse(url)
    link_host = parts.netloc.lower().removeprefix("www.")
    same_site = link_host == host or link_host.endswith(f".{host}")
    return bool(same_site and FEED_PATH.search(f"{parts.path}?{parts.query}") and not PAGE_PATH.search(parts.path))


def discover_feeds(html: str, base_url: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(פידים שהדף מצהיר עליהם, קישורים בדף שנראים כמו פיד), בלי כפילויות ופידי תגובות בסוף."""
    scanner = _PageScanner()
    try:
        scanner.feed(html)
    except Exception:  # noqa: BLE001
        return [], []
    declared: dict[str, str] = {}
    for href, title in scanner.feeds:
        if url := abs_url(href, base_url):
            declared.setdefault(url, title.strip() or url)
    host = urlparse(base_url).netloc.lower().removeprefix("www.")
    links: dict[str, str] = {}
    # קישור עם הטקסט "RSS" הוא בדרך כלל דף האינדקס של הפידים, ולכן ראשון
    for href, label in sorted(scanner.anchors, key=lambda a: not FEED_LABEL.search(a[1])):
        url = abs_url(href, base_url)
        if url and url not in declared and url.rstrip("/") != base_url.rstrip("/") and _is_feed_link(url, label, host):
            links.setdefault(url, label or url)

    def comments_last(item: tuple[str, str]) -> bool:
        return "comment" in item[0].lower()

    return sorted(declared.items(), key=comments_last), sorted(links.items(), key=comments_last)[:LINKS_MAX]


def _xml_start(content: bytes) -> int | None:
    """היכן מתחיל פיד ה-XML (אחרי BOM, רווחים או הודעת שגיאה של השרת), או None אם אין פיד XML."""
    # הערות הופכות לרווחים כדי שתוכנן לא יבלבל את החיפוש והמיקומים יישמרו
    head = _COMMENT.sub(lambda m: b" " * len(m[0]), content[:SNIFF_BYTES])
    root = _FEED_ROOT.search(head)
    if not root or _HTML_START.search(head, 0, root.start()):
        return None
    decl = _XML_DECL.search(head, 0, root.start())
    return decl.start() if decl else root.start()


def _codec(name: str | None) -> str | None:
    try:
        return codecs.lookup(name).name if name else None
    except LookupError:
        return None


def _decodes(data: bytes, codec: str) -> bool:
    try:
        data.decode(codec)
    except UnicodeDecodeError:
        return False
    return True


def _as_utf8(doc: bytes, http_charset: str | None) -> bytes | None:
    """המסמך ב-UTF-8, או None כשאי אפשר לדעת את הקידוד שלו.

    UTF-8 תקין נשאר כמו שהוא גם כשהוצהר אחרת. אחרת קובעת ההצהרה במסמך או הקידוד מהשרת,
    וברירת מחדל גנרית של שרת (latin-1) רק כשאין ברירה: אחרת עברית ב-windows-1255 יוצאת ג'יבריש.
    """
    if _decodes(doc, "utf-8"):
        return doc
    declared = _XML_ENCODING.match(doc)
    found = (_codec(declared and declared[1].decode()), _codec(http_charset))
    candidates = sorted(dict.fromkeys(c for c in found if c), key=lambda c: c in GENERIC_CHARSETS)
    codec = next((c for c in candidates if _decodes(doc, c)), candidates[0] if candidates else None)
    return doc.decode(codec, "replace").encode() if codec else None


def parse_feed(
    content: bytes,
    url: str,
    content_type: str | None = None,
    max_entries: int = 30,
    charset: str | None = None,
) -> ParsedFeed:
    """מנתח תוכן גולמי לפי התוכן עצמו (Content-Type הוא רק רמז). זורק FeedError עם reason not_a_feed / invalid_feed."""
    text = content.removeprefix(codecs.BOM_UTF8).lstrip()
    if text[:1] in (b"{", b"["):
        try:
            data = json.loads(text.decode("utf-8", "replace"))
        except ValueError as err:
            raise FeedError("invalid_feed") from err
        if not isinstance(data, dict) or "jsonfeed.org" not in str(data.get("version", "")):
            raise FeedError("not_a_feed")
        result = _from_json_feed(data, url)
    else:
        headers = {"content-location": url}
        start = _xml_start(content)
        if start is None and ("html" in (content_type or "") or _HTML_START.search(text[:SNIFF_BYTES])):
            html = content.decode(_codec(charset) or "utf-8", "replace")
            raise FeedError("not_a_feed", *discover_feeds(html, url))
        if start is not None:
            text = content[start:]
            if (doc := _as_utf8(text, charset)) is not None:
                text = doc
                headers["content-type"] = "application/xml; charset=utf-8"
        parsed = feedparser.parse(text, response_headers=headers)
        if parsed.get("bozo") and not parsed.get("entries") and GLUED_ATTRS.search(text[:SNIFF_BYTES]):
            parsed = feedparser.parse(GLUED_ATTRS.sub(rb"\1 ", text), response_headers=headers)
        if not parsed.get("version") and not parsed.get("entries"):
            raise FeedError("invalid_feed")
        result = _from_feedparser(parsed, url, max_entries)

    first: dict[str, NewsEntry] = {}
    for entry in result.entries:
        first.setdefault(entry["id"], entry)
    unique = list(first.values())
    # מיון יציב: פריטים עם תאריך לפי חדש→ישן, בלי תאריך שומרים על סדר הפיד
    if all(e["published"] for e in unique):
        unique.sort(key=lambda e: e["published"] or "", reverse=True)
    result.entries = unique[:max_entries]
    return result


def apply_first_seen(entries: list[NewsEntry], first_seen: dict[str, str], now: datetime) -> None:
    """פריט בלי תאריך, או עם תאריך עתידי, מקבל את זמן הראייה הראשון (נשמר בין הפעלות).

    תאריך עתידי הוא כמעט תמיד שעון מקומי שסומן כ-GMT (נפוץ באתרים ישראליים) או פרסום מתוזמן.
    """
    stamp = now.astimezone(UTC).isoformat()
    limit = now + FUTURE_TOLERANCE
    for entry in entries:
        if not entry["published"] or datetime.fromisoformat(entry["published"]) > limit:
            entry["published"] = first_seen.setdefault(entry["id"], stamp)
            entry["published_estimated"] = True
