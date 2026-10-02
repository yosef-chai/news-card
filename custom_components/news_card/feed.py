"""ניתוח ונרמול פידים (RSS / Atom / RDF / JSON Feed) לחוזה נתונים אחיד.

המודול טהור: בלי ייבוא מ-Home Assistant, כדי שאפשר יהיה לבדוק אותו לבד.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import json
import logging
import re
from typing import Any, TypedDict
from urllib.parse import urljoin, urlparse

import feedparser

_LOGGER = logging.getLogger(__name__)

SUMMARY_MAX = 2000
TITLE_FROM_SUMMARY_MAX = 100
IMAGE_EXT = re.compile(r"\.(jpe?g|png|gif|webp|avif|bmp|svg)(\?|#|$)", re.I)
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
    """הפיד לא נקרא. reason הוא מפתח תרגום."""

    def __init__(self, reason: str, discovered: list[tuple[str, str]] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.discovered = discovered or []


class _TextExtractor(HTMLParser):
    """ממיר HTML לטקסט נקי ושומר מעברי שורה של בלוקים."""

    BLOCK = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
    SKIP = {"script", "style", "noscript", "iframe", "figcaption"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(value: str | None) -> str:
    """טקסט נקי מ-HTML: בלי תגיות, ישויות מפוענחות, רווחים מנורמלים."""
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


def _is_image(url: str | None, mime: str | None = None, medium: str | None = None) -> bool:
    if not url:
        return False
    if medium:
        return medium == "image"
    if mime:
        return mime.startswith("image/")
    return bool(IMAGE_EXT.search(url))


def _first_img(html: str | None, base: str | None) -> str | None:
    """התמונה הראשונה שאינה זבל מתוך HTML, כולל lazy-load."""
    if not html:
        return None
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
    """סדר עדיפויות: media:content → media:thumbnail → itunes:image → enclosure → <img>."""
    images = [
        m
        for m in entry.get("media_content") or []
        if _is_image(m.get("url"), m.get("type"), m.get("medium"))
    ]
    if images:
        return abs_url(max(images, key=_size)["url"], base)
    thumbs = [t for t in entry.get("media_thumbnail") or [] if t.get("url")]
    if thumbs:
        return abs_url(max(thumbs, key=_size)["url"], base)
    itunes = entry.get("image")
    if isinstance(itunes, dict) and itunes.get("href"):
        return abs_url(itunes["href"], base)
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and _is_image(link.get("href"), link.get("type")):
            return abs_url(link["href"], base)
    for content in entry.get("content") or []:
        if found := _first_img(content.get("value"), base):
            return found
    return _first_img(entry.get("summary"), base)


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


def make_id(*candidates: Any) -> str:
    """מזהה יציב וקצר."""
    raw = next((str(c) for c in candidates if c), "")
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _clean_title(title: str, source: str | None) -> str:
    """הסרת סיומת " - מקור" (Google News)."""
    if source and title.endswith(f" - {source}") and len(title) > len(source) + 3:
        return title[: -len(source) - 3].rstrip()
    return title


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
    summary = html_to_text(summary_html)
    title = html_to_text(title).replace("\n", " ")
    title = _clean_title(title, source)
    if not title:
        title = truncate(summary.replace("\n", " "), TITLE_FROM_SUMMARY_MAX)
    # Google News: התקציר הוא רק הכותרת + שם המקור
    if summary == title or summary.startswith(title):
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
        "author": html_to_text(author) or None,
        "source": source,
        "categories": categories[:10],
        "image": image,
        "image_proxy": None,
        "media": media,
    }


def _from_feedparser(parsed: Any, url: str) -> ParsedFeed:
    feed = parsed.get("feed", {})
    feed_link = abs_url(feed.get("link"), url) or f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
    feed_title = html_to_text(feed.get("title")) or urlparse(url).netloc
    icon = None
    if isinstance(feed.get("image"), dict):
        icon = abs_url(feed["image"].get("href"), url)
    icon = icon or abs_url(feed.get("icon"), url) or abs_url(feed.get("logo"), url)

    entries: list[NewsEntry] = []
    for entry in parsed.get("entries", []):
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
            content = entry.get("content") or []
            summary_html = entry.get("summary") or (content[0].get("value") if content else "")
            if not summary_html and entry.get("media_description"):
                summary_html = entry.get("media_description")
            entries.append(
                _build_entry(
                    raw_id=entry.get("id"),
                    title=entry.get("title") or "",
                    link=link or feed_link,
                    published=_iso(
                        entry.get("published_parsed")
                        or entry.get("updated_parsed")
                        or entry.get("created_parsed")
                    ),
                    summary_html=summary_html,
                    author=entry.get("author"),
                    source=source or feed_title,
                    categories=[t.get("term") for t in entry.get("tags") or [] if t.get("term")],
                    image=_entry_image(entry, base),
                    media=_entry_media(entry, base),
                )
            )
        except Exception:  # noqa: BLE001 - פריט שבור לא יפיל את כל הפיד
            _LOGGER.debug("Skipping broken entry in %s", url, exc_info=True)
    return ParsedFeed({"title": feed_title, "link": feed_link, "icon": icon}, entries)


def _from_json_feed(data: dict[str, Any], url: str) -> ParsedFeed:
    feed_link = abs_url(data.get("home_page_url"), url) or url
    feed_title = html_to_text(data.get("title")) or urlparse(url).netloc
    entries: list[NewsEntry] = []
    for item in data.get("items") or []:
        try:
            if not isinstance(item, dict):
                continue
            authors = item.get("authors") or ([item["author"]] if item.get("author") else [])
            media = next(
                (
                    {"url": u, "type": a.get("mime_type", "")}
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
                    author=next((a.get("name") for a in authors if isinstance(a, dict)), None),
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


class _FeedLinkFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower().split()
        if "alternate" in rel and a.get("type", "").lower() in FEED_LINK_TYPES and a.get("href"):
            self.found.append((a["href"], a.get("title", "")))


def discover_feeds(html: str, base_url: str) -> list[tuple[str, str]]:
    """פידים שמוצהרים בדף HTML (<link rel="alternate">), בלי כפילויות; פידי תגובות בסוף."""
    finder = _FeedLinkFinder()
    try:
        finder.feed(html)
    except Exception:  # noqa: BLE001
        return []
    result: dict[str, str] = {}
    for href, title in finder.found:
        if url := abs_url(href, base_url):
            result.setdefault(url, title.strip() or url)
    return sorted(result.items(), key=lambda kv: "comment" in kv[0].lower())


def _looks_like_html(content: bytes, content_type: str | None) -> bool:
    head = content[:2048].lstrip().lower()
    return (content_type or "").startswith("text/html") or head.startswith((b"<!doctype html", b"<html"))


def parse_feed(
    content: bytes,
    url: str,
    content_type: str | None = None,
    max_entries: int = 30,
) -> ParsedFeed:
    """מנתח תוכן גולמי. זורק FeedError עם reason not_a_feed / invalid_feed."""
    head = content[:64].lstrip()
    if head.startswith(b"{") or "json" in (content_type or ""):
        try:
            data = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as err:
            raise FeedError("invalid_feed") from err
        if not isinstance(data, dict) or "jsonfeed.org" not in str(data.get("version", "")):
            raise FeedError("not_a_feed")
        result = _from_json_feed(data, url)
    elif _looks_like_html(content, content_type):
        raise FeedError(
            "not_a_feed", discover_feeds(content.decode("utf-8", "replace"), url)
        )
    else:
        # הצהרת XML שלא בתחילת הקובץ (רווח מוביל) שוברת את זיהוי הקידוד
        parsed = feedparser.parse(content.lstrip(), response_headers={"content-location": url})
        if not parsed.get("version") and not parsed.get("entries"):
            raise FeedError("invalid_feed")
        result = _from_feedparser(parsed, url)

    seen: set[str] = set()
    unique = [e for e in result.entries if not (e["id"] in seen or seen.add(e["id"]))]
    # מיון יציב: פריטים עם תאריך לפי חדש→ישן, בלי תאריך שומרים על סדר הפיד
    if all(e["published"] for e in unique):
        unique.sort(key=lambda e: e["published"] or "", reverse=True)
    result.entries = unique[:max_entries]
    return result


def apply_first_seen(entries: list[NewsEntry], first_seen: dict[str, str], now: datetime) -> None:
    """פריט בלי תאריך מקבל את זמן הראייה הראשון (נשמר בין הפעלות)."""
    stamp = now.astimezone(UTC).isoformat()
    for entry in entries:
        if not entry["published"]:
            entry["published"] = first_seen.setdefault(entry["id"], stamp)
            entry["published_estimated"] = True
