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
    html = '<link rel="alternate" type="application/json+oembed" href="/o"><link rel="alternate" type="application/atom+xml" href="/atom">'
    assert discover_feeds(html, "https://a.b/") == [("https://a.b/atom", "https://a.b/atom")]


def test_find_page_image() -> None:
    html = '<meta name="twitter:image" content="/t.jpg"><meta property="og:image" content="https://a/og.jpg">'
    assert find_page_image(html) == "https://a/og.jpg"
    assert find_page_image('<link rel="image_src" href="/i.png">') == "/i.png"
    assert find_page_image("<p>nothing</p>") is None
