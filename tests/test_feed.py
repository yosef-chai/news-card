"""בדיקות הנרמול על פידים אמיתיים ועל מקרי קצה."""

from datetime import UTC, datetime

import pytest

from custom_components.news_card.client import find_page_image
from custom_components.news_card.feed import (
    FeedError,
    apply_first_seen,
    discover_feeds,
    html_to_text,
    parse_feed,
)

from .conftest import fixture

ALL = [
    "jdn.xml", "ims.xml", "google.xml", "cnn.xml", "fox.xml", "emess.xml", "hmnews.xml",
    "atom.xml", "rdf.xml", "jsonfeed.json", "podcast.xml", "youtube.xml", "bozo.xml",
]


@pytest.mark.parametrize("name", ALL)
def test_every_entry_is_complete(name: str) -> None:
    result = parse_feed(fixture(name), f"https://example.com/{name}")
    assert result.entries
    assert result.info["title"]
    for entry in result.entries:
        assert entry["title"]
        assert entry["link"].startswith(("http://", "https://"))
        assert len(entry["id"]) == 16
        assert "<" not in entry["title"]
        if entry["image"]:
            assert entry["image"].startswith(("http://", "https://"))


@pytest.mark.parametrize("name", ["jdn.xml", "cnn.xml", "fox.xml", "podcast.xml", "youtube.xml"])
def test_images_found_for_every_entry(name: str) -> None:
    entries = parse_feed(fixture(name), "https://example.com/").entries
    assert all(e["image"] for e in entries)


@pytest.mark.parametrize("name", ["emess.xml", "hmnews.xml"])
def test_images_from_content_html(name: str) -> None:
    assert any(e["image"] for e in parse_feed(fixture(name), "https://example.com/").entries)


def test_cnn_picks_largest_media() -> None:
    first = parse_feed(fixture("cnn.xml"), "http://rss.cnn.com/").entries[0]
    assert "super-169" in first["image"]


def test_google_news_source_suffix() -> None:
    entries = parse_feed(fixture("google.xml"), "https://news.google.com/rss").entries
    assert all(e["source"] == "C14" for e in entries)
    assert not any(e["title"].endswith(" - C14") for e in entries)
    assert all(e["summary"] == "" for e in entries)


def test_ims_hebrew_text_with_line_breaks() -> None:
    entry = parse_feed(fixture("ims.xml"), "https://ims.gov.il/").entries[0]
    assert "תחזית" in entry["title"]
    assert "\n" in entry["summary"]
    assert "<" not in entry["summary"]
    assert entry["published"].startswith("2026-")


def test_emess_leading_whitespace_encoding() -> None:
    entry = parse_feed(fixture("emess.xml"), "https://www.emess.co.il/feed").entries[0]
    assert "×" not in entry["title"]
    assert entry["author"]


def test_podcast_media_and_categories() -> None:
    entry = parse_feed(fixture("podcast.xml"), "https://feeds.npr.org/").entries[0]
    assert entry["media"]["type"].startswith("audio/")


def test_bozo_feed_fallbacks() -> None:
    entries = parse_feed(fixture("bozo.xml"), "https://broken.example/feed").entries
    first, second = entries
    assert first["link"] == "https://broken.example/relative/1"
    assert first["image"] == "https://broken.example/img/a.jpg"  # פיקסל המעקב דולג
    assert first["published"] is None
    assert second["title"].startswith("No title")
    assert second["link"] == "https://broken.example/"


def test_json_feed() -> None:
    result = parse_feed(fixture("jsonfeed.json"), "https://www.jsonfeed.org/feed.json", "application/feed+json")
    assert result.info["title"] == "JSON Feed"
    assert result.entries[0]["published"]


def test_html_page_discovers_feeds() -> None:
    with pytest.raises(FeedError) as err:
        parse_feed(fixture("page.html"), "https://www.jdn.co.il/", "text/html")
    assert err.value.reason == "not_a_feed"
    assert err.value.discovered[0][0] == "https://www.jdn.co.il/feed/"
    assert "comments" in err.value.discovered[-1][0]


@pytest.mark.parametrize(
    ("content", "reason"),
    [(b"not xml at all", "invalid_feed"), (b"{broken", "invalid_feed"), (b'{"a": 1}', "not_a_feed")],
)
def test_invalid_content(content: bytes, reason: str) -> None:
    with pytest.raises(FeedError) as err:
        parse_feed(content, "https://example.com/")
    assert err.value.reason == reason


def test_max_entries_and_sorting() -> None:
    entries = parse_feed(fixture("google.xml"), "https://x/", max_entries=5).entries
    assert len(entries) == 5
    dates = [e["published"] for e in entries]
    assert dates == sorted(dates, reverse=True)


def test_first_seen_is_stable() -> None:
    entries = parse_feed(fixture("bozo.xml"), "https://broken.example/").entries
    seen: dict[str, str] = {}
    apply_first_seen(entries, seen, datetime(2026, 1, 1, tzinfo=UTC))
    assert entries[0]["published_estimated"]
    again = parse_feed(fixture("bozo.xml"), "https://broken.example/").entries
    apply_first_seen(again, seen, datetime(2026, 5, 5, tzinfo=UTC))
    assert again[0]["published"] == entries[0]["published"]


def test_html_to_text() -> None:
    assert html_to_text("<p>a&amp;b<br>c</p><script>x</script>") == "a&b\nc"
    assert html_to_text(None) == ""


def test_discover_ignores_non_feeds() -> None:
    html = (
        '<link rel="alternate" type="application/json+oembed" href="/o"><link rel="alternate" type="application/atom+xml" href="/atom">'
        '<link rel="alternate" type="application/json" href="/wp-json/wp/v2/posts/1">'
        '<link rel="alternate" type="application/json" title="JSON Feed" href="/feeds/json">'
    )
    assert discover_feeds(html, "https://a.b/")[0] == [
        ("https://a.b/atom", "https://a.b/atom"),
        ("https://a.b/feeds/json", "JSON Feed"),
    ]


def test_feed_like_links() -> None:
    """אתר בלי <link> לפיד: קישורי "RSS" מכל מקום, ונתיבי rss/feed רק מהאתר עצמו ולא דפי כתבה."""
    html = """<a href="/">home</a><a href="/music-feed/2026/clip.htm">clip</a><a href="/rss">RSS</a>
    <a href="https://x.com/site_feed">X</a><a href="https://feeds.feedburner.com/site">RSS 2.0</a>
    <a href="/srv/news-rss">חדשות</a><a href="https://rss.a.b/feed/1"><b>ספורט</b></a><a href="/forum/external.php?type=RSS2">forum</a>"""
    declared, links = discover_feeds(html, "https://www.a.b/")
    assert declared == []
    assert links == [
        ("https://www.a.b/rss", "RSS"),
        ("https://feeds.feedburner.com/site", "RSS 2.0"),
        ("https://www.a.b/srv/news-rss", "חדשות"),
        ("https://rss.a.b/feed/1", "ספורט"),
        ("https://www.a.b/forum/external.php?type=RSS2", "forum"),
    ]


def _rss(items: str, channel: str = "", ns: str = "") -> bytes:
    return (
        f'<rss version="2.0" {ns}><channel><title>T</title><link>https://a.b/</link>{channel}{items}</channel></rss>'
    ).encode()


def test_double_escaped_html() -> None:
    body = _rss(
        "<item><title>Q&amp;amp;A</title><link>https://a.b/1</link><description><![CDATA["
        "&lt;img src=&quot;https://a.b/i.jpg&quot;&gt;&lt;p&gt;Hi &amp;amp; bye&lt;/p&gt;]]></description></item>"
    )
    entry = parse_feed(body, "https://a.b/feed").entries[0]
    assert entry["title"] == "Q&A"
    assert entry["summary"] == "Hi & bye"
    assert entry["image"] == "https://a.b/i.jpg"


@pytest.mark.parametrize(
    ("description", "summary"),
    [
        ("<p>Body.</p><p>The post <a href='x'>X</a> first appeared on <a href='y'>Y</a>.</p>", "Body."),
        ("<p>Body.</p><p>Read more of this story at Slashdot.</p>", "Body."),
        ("<p>Some text Read More</p>", "Some text…"),
        ("<p>Some text [&#8230;]</p><p>המשך קריאה</p>", "Some text…"),
        ("<p>You can read more about it on our blog.</p>", "You can read more about it on our blog."),
    ],
)
def test_summary_boilerplate(description: str, summary: str) -> None:
    body = _rss(f"<item><title>t</title><link>https://a.b/1</link><description><![CDATA[{description}]]></description></item>")
    assert parse_feed(body, "https://a.b/feed").entries[0]["summary"] == summary


def test_author_profile_url_and_long_title() -> None:
    body = _rss(
        f"<item><title>{'word ' * 100}</title><link>https://a.b/1</link>"
        "<dc:creator>Duet ! (https://www.flickr.com/people/115338398@N03/)</dc:creator></item>"
        "<item><title>lemmy</title><link>https://a.b/2</link><dc:creator>https://lemmy.ca/u/Crumpled6273</dc:creator></item>",
        ns='xmlns:dc="http://purl.org/dc/elements/1.1/"',
    )
    flickr, lemmy = parse_feed(body, "https://a.b/feed").entries
    assert flickr["author"] == "Duet !"
    assert len(flickr["title"]) <= 301
    assert flickr["title"].endswith("…")
    assert lemmy["author"] == "Crumpled6273"


def test_bing_news() -> None:
    body = _rss(
        '<item><title>t</title><link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fsite.example%2fa%3fx%3d1&amp;c=1</link>'
        "<News:Source>Site</News:Source><News:Image>http://www.bing.com/th?id=ONUT.x&amp;pid=News</News:Image></item>",
        ns='xmlns:News="https://www.bing.com:443/news/search?q=x&amp;format=rss"',
    )
    entry = parse_feed(body, "https://www.bing.com/news/search?q=x&format=rss").entries[0]
    assert entry["link"] == "https://site.example/a?x=1"
    assert entry["source"] == "Site"
    assert entry["image"] == "http://www.bing.com/th?id=ONUT.x&pid=News"


def test_podcast_episode_without_page_or_image() -> None:
    body = _rss(
        '<item><title>Ep 1</title><guid isPermaLink="false">ep1</guid>'
        '<enclosure url="https://cdn.a.b/ep1.mp3" length="1" type="audio/mpeg"/></item>',
        channel='<itunes:image href="https://a.b/show.jpg"/>',
        ns='xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"',
    )
    entry = parse_feed(body, "https://a.b/podcast.xml").entries[0]
    assert entry["link"] == "https://cdn.a.b/ep1.mp3"
    assert entry["image"] == "https://a.b/show.jpg"


@pytest.mark.parametrize(
    ("extra", "image"),
    [
        # media:content בלי type ובלי סיומת (CDN) הוא תמונה; וידאו לא
        ('<media:content url="https://cdn.a.b/photo/123"/>', "https://cdn.a.b/photo/123"),
        ('<media:content url="https://cdn.a.b/clip.mp4"/>', None),
        ('<media:content url="https://cdn.a.b/v" medium="video"/>', None),
        ('<itunes:image href="https://a.b/ep.jpg"/>', "https://a.b/ep.jpg"),
        ("<image><url>https://a.b/item.jpg</url></image>", "https://a.b/item.jpg"),
        ('<enclosure url="https://a.b/e.png" length="0" type="image/png"/>', "https://a.b/e.png"),
    ],
)
def test_item_image_sources(extra: str, image: str | None) -> None:
    ns = 'xmlns:media="http://search.yahoo.com/mrss/" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"'
    body = _rss(f"<item><title>t</title><link>https://a.b/1</link>{extra}</item>", ns=ns)
    assert parse_feed(body, "https://a.b/feed").entries[0]["image"] == image


def test_page_with_unknown_charset() -> None:
    page = b'<html><head><link rel="alternate" type="application/rss+xml; charset=utf-8" href="/rss"></head></html>'
    with pytest.raises(FeedError) as err:
        parse_feed(page, "https://a.b/", "text/html", charset="x-bogus")
    assert err.value.discovered == [("https://a.b/rss", "https://a.b/rss")]


def test_glued_attributes_are_repaired() -> None:
    """WordPress של NASA: בלי רווח בין מאפיינים בתגית השורש, ו-feedparser לא מחזיר כלום."""
    body = (
        b'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"\n'
        b'\txmlns:dc="http://purl.org/dc/elements/1.1/"\n'
        b'\t xmlns:apod="https://a.b/apod/"xmlns:media="http://search.yahoo.com/mrss/" >\n'
        b"<channel><title>NASA</title><item><title>Moon</title><link>https://a.b/moon</link></item></channel></rss>"
    )
    assert parse_feed(body, "https://a.b/feed").entries[0]["title"] == "Moon"


def test_future_dates_use_first_seen() -> None:
    """שעון מקומי שסומן כ-GMT (jpost, וואלה): תאריך עתידי מוחלף בזמן הראייה הראשון, שנשמר."""
    now = datetime(2026, 10, 3, 21, 0, tzinfo=UTC)
    body = _rss(
        "<item><title>future</title><link>https://a.b/1</link><pubDate>Sun, 04 Oct 2026 00:01:00 GMT</pubDate></item>"
        "<item><title>close</title><link>https://a.b/2</link><pubDate>Sat, 03 Oct 2026 21:05:00 GMT</pubDate></item>"
    )
    seen: dict[str, str] = {}
    entries = parse_feed(body, "https://a.b/feed").entries
    apply_first_seen(entries, seen, now)
    assert entries[0]["published"] == now.isoformat()
    assert entries[0]["published_estimated"]
    assert entries[1]["published"] == "2026-10-03T21:05:00+00:00"
    assert not entries[1]["published_estimated"]
    again = parse_feed(body, "https://a.b/feed").entries
    apply_first_seen(again, seen, datetime(2026, 10, 3, 21, 30, tzinfo=UTC))
    assert again[0]["published"] == now.isoformat()


HEB_RSS = '<rss version="2.0"><channel><title>שלום</title><link>https://a.b/</link><item><title>כותרת</title><link>https://a.b/1</link></item></channel></rss>'


@pytest.mark.parametrize(
    ("content", "charset"),
    [
        # הקידוד מגיע רק מהשרת
        (HEB_RSS.encode("cp1255"), "windows-1255"),
        # ההצהרה במסמך נכונה וברירת המחדל של השרת שגויה
        (f'<?xml version="1.0" encoding="windows-1255"?>{HEB_RSS}'.encode("cp1255"), "iso-8859-1"),
        # ההצהרה שגויה (UTF-8) והשרת צודק
        (f'<?xml version="1.0" encoding="utf-8"?>{HEB_RSS}'.encode("cp1255"), "windows-1255"),
        # UTF-8 תקין גובר על הצהרה שגויה
        (f'<?xml version="1.0" encoding="windows-1255"?>{HEB_RSS}'.encode(), None),
    ],
)
def test_encoding(content: bytes, charset: str | None) -> None:
    result = parse_feed(content, "https://a.b/feed", "text/xml", charset=charset)
    assert result.info["title"] == "שלום"
    assert result.entries[0]["title"] == "כותרת"


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (HEB_RSS.encode(), "text/html"),
        (HEB_RSS.encode(), "application/json"),
        (b"\xef\xbb\xbf\n\n" + HEB_RSS.encode(), None),
        (b"<br />\n<b>Warning</b>: Cannot modify header information<br />\n" + HEB_RSS.encode(), "text/html"),
        (b"<!-- <html> --><?xml version='1.0'?>" + HEB_RSS.encode(), None),
    ],
)
def test_detects_feed_by_content(content: bytes, content_type: str | None) -> None:
    assert parse_feed(content, "https://a.b/feed", content_type).entries[0]["title"] == "כותרת"


def test_json_feed_with_bom_and_wrong_type() -> None:
    body = b'\xef\xbb\xbf {"version": "https://jsonfeed.org/version/1.1", "title": "J", "authors": [{"name": "Feed Author"}],'
    body += b'"items": [{"id": "1", "url": "https://a.b/1", "title": "t"}]}'
    entry = parse_feed(body, "https://a.b/feed.json", "text/plain").entries[0]
    assert entry["title"] == "t"
    assert entry["author"] == "Feed Author"


def test_xhtml_page_is_discovered() -> None:
    page = b'<?xml version="1.0"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><head>'
    page += b'<link rel="alternate" type="application/rss+xml" href="/rss"/></head></html>'
    with pytest.raises(FeedError) as err:
        parse_feed(page, "https://a.b/", "application/xhtml+xml")
    assert err.value.discovered == [("https://a.b/rss", "https://a.b/rss")]


def test_authors_and_categories() -> None:
    body = b"""<rss version="2.0"><channel><title>T</title><link>https://a.b/</link>
    <item><title>1</title><link>https://a.b/1</link><author>bob@a.b (Bob Smith)</author>
      <category>News</category><category>News</category></item>
    <item><title>2</title><link>https://a.b/2</link><author>editor@a.b</author></item>
    </channel></rss>"""
    first, second = parse_feed(body, "https://a.b/feed").entries
    assert first["author"] == "Bob Smith"
    assert first["categories"] == ["News"]
    assert second["author"] is None
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>A</title>
    <entry><title>x</title><id>1</id><link href="https://a.b/x"/>
      <author><name>Ann</name><email>ann@a.b</email></author><author><name>Dan</name></author>
      <category term="https://a.b/tags/ai" label="AI"/><category term="https://a.b/scheme#"/></entry></feed>"""
    entry = parse_feed(atom, "https://a.b/atom").entries[0]
    assert entry["author"] == "Ann, Dan"
    assert entry["categories"] == ["AI"]


def test_find_page_image() -> None:
    html = '<meta name="twitter:image" content="/t.jpg"><meta property="og:image" content="https://a/og.jpg">'
    assert find_page_image(html) == "https://a/og.jpg"
    assert find_page_image('<link rel="image_src" href="/i.png">') == "/i.png"
    assert find_page_image("<p>nothing</p>") is None
