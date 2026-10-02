<p align="center"><img src="assets/logo.png" width="120" alt="News Card logo"></p>

# News Card

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/yosef-chai/news-card/actions/workflows/validate.yml/badge.svg)](https://github.com/yosef-chai/news-card/actions/workflows/validate.yml)
[![Tests](https://github.com/yosef-chai/news-card/actions/workflows/tests.yml/badge.svg)](https://github.com/yosef-chai/news-card/actions/workflows/tests.yml)

[עברית](README.he.md)

This is a news feed integration and dashboard card for Home Assistant, installed together as one package.
- The integration reads any RSS, Atom, RDF or JSON Feed.
- It cleans up each article and finds an image when the feed has one.
- It creates entities and events you can use in automations.
- The card shows the news as a list, or as a bottom ticker that scrolls endlessly.

## Features

- **Any feed**
  - Supported formats: RSS 0.9x/1.0/2.0, Atom, RDF, CDF and JSON Feed 1.0/1.1.
  - If you paste a website address instead of a feed, it finds the feeds that page publishes.
  - Feeds you already set up in **Feedreader** are offered in a list.
- **Clean data**
  - HTML is removed, and character encodings and entities are decoded.
  - Relative links are made absolute.
  - The source name Google News adds to each title is removed.
  - If an article has no date, it gets a stable "first seen" date.
- **Images** are taken from, in order:
  - `media:content` (the largest one)
  - `media:thumbnail`
  - `itunes:image`
  - an image enclosure
  - the first real `<img>` in the article (tracking pixels and emoji are skipped)
  - the article page's share image, `og:image` (optional, checked once per article)
- **Image proxy**
  - Images can load through Home Assistant. This fixes sites that block hotlinking and `http` images on an `https` dashboard.
  - The proxy only serves images that appear in your feeds.
- **Card**
  - List or infinite ticker, with image, date, time, source and author toggles.
  - Newest first, oldest first or random order, and a limit on the number of articles.
  - Absolute or relative time.
  - Tapping an article can open it, show its summary in a dialog, or do nothing.
  - Can dim articles you already opened.
  - Visual editor, resizable in sections dashboards, English and Hebrew, RTL support.
- **Alerts** to phones and speakers, set up from the feed page without automations.
- **Automations**: **New article** and **No new articles** triggers, a **Recent article** condition, a **Mark as read** action with an unread counter, ready-made blueprints, an event entity for new articles and keyword matches, the `news_card_new_article` bus event, and the `news_card.get_entries` and `news_card.refresh` actions.
- **Reliable**
  - Downloads only when the feed changed (ETag / Last-Modified).
  - Keeps the last good copy and keeps showing it, marked as outdated, while a site is down.
  - Opens a repair issue when a feed is gone.
  - Clear error messages in the setup flow, the card and the logs.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/yosef-chai/news-card` as **Integration**.
2. Search for **News Card** and download it.
3. Restart Home Assistant.
4. **Settings → Devices & services → Add integration → News Card**, then enter a feed address.

The card is registered automatically. You don't need to add a dashboard resource.

### Manual

Copy `custom_components/news_card` into `config/custom_components/`, then restart Home Assistant.

## Configuration

Each feed is its own integration entry.

| Option | Default | Description |
|---|---|---|
| Feed or website address | — | Feed URL, or a site URL (its feeds are discovered) |
| Verify SSL certificate | on | Turn off only for a trusted site with a broken certificate |
| Update interval | 15 min | 5–1440 minutes |
| Maximum articles to keep | 30 | 1–100 |
| Keywords | — | Comma or line separated. Matching new articles fire `keyword_match` |
| Load images through Home Assistant | on | Image proxy |
| Find missing images on the article page | on | Reads `og:image` once per article that has no image |

To change the address, use **⋮ → Reconfigure**. Everything else is under **Configure**.

### Entities (per feed)

| Entity | Description |
|---|---|
| `sensor.<feed>_latest_article` | Title of the newest article. Attributes: link, published, source, image |
| `sensor.<feed>_articles` | Number of articles (diagnostic) |
| `sensor.<feed>_last_update` | Last successful update (diagnostic) |
| `event.<feed>_new_article` | Fires `new_article` and `keyword_match` |

### How data updates

- The feed is checked at the update interval.
- An unchanged feed costs a single request with no parsing.
- New articles fire events once each. Nothing fires on the first load, after a restart, or when you raise the article limit.
- The card receives updates over a WebSocket subscription, so there's no polling.

## Card

Add it from the dashboard editor (**News Card**). Pick one or more **news sources** by name, and all their articles appear according to the card settings. The scroll speed option shows up for the bottom ticker, and for a list with **Scroll automatically** turned on.

In YAML, sources can be given as devices (`feeds`, what the editor saves) or as entities (`entities`):

```yaml
type: custom:news-card
entities:            # or feeds: [<device id>, ...]
  - sensor.jdn_latest_article
  - sensor.cnn_com_rss_channel_hp_hero_latest_article
title: News
display: list          # list | ticker
show_image: true
show_date: true
show_time: true
show_source: true
show_author: false
date_format: absolute  # absolute | relative
sort: desc             # desc | asc | random
max_items: 30
tap_action: link       # link | dialog | none
mark_read: false        # dim opened articles; shared by all devices (Unread articles sensor)
auto_scroll: false      # list only: scroll by itself when the articles don't fit a fixed height
scroll_speed: 30        # pixels per second (5–100), for the ticker and the auto-scrolling list
```

- Several feeds are merged into one list, sorted by date.
- A Feedreader `event` entity can be added too. It only provides the latest article.
- The ticker scrolls left to right in right-to-left languages (such as Hebrew) and right to left in left-to-right languages.
- Scrolling pauses automatically while you hover over it, use the keyboard, or read an article (dialog open or article tab active), and resumes when you come back. It doesn't move when the system asks for reduced motion.

## Alerts: phone and speakers, without automations

**Settings → Devices & services → News Card → the feed → Add alert.**

1. Choose **when**: for every new article, or every day at a set time (choose the days).
2. Choose **where**: phones with the Home Assistant app are already selected; add speakers to hear it too.
3. Optional: keywords, the article summary (good for weather forecasts), and the hours when speakers may talk.

The speakers announce the news in your Home Assistant language and then resume what was playing. Outside the speaking hours only the phone is notified. Each feed can have several alerts; edit or delete them from the same page.

## Automation examples

Weather forecast at 9:00 except Saturday, to the phone and a speaker:

```yaml
triggers:
  - trigger: time
    at: "09:00:00"
conditions:
  - condition: time
    weekday: [sun, mon, tue, wed, thu, fri]
actions:
  - action: news_card.send_to_phone
    data:
      entity_id: sensor.ims_latest_article
      phones: <your phone>
      include_summary: true
  - action: news_card.announce
    data:
      entity_id: sensor.ims_latest_article
      speakers: media_player.kitchen
      include_summary: true
```

The easiest way: in the automation editor pick the **News Card → New article** trigger, choose feeds (entities, devices or areas) and optionally type keywords. The article is in `trigger.to_state.attributes`:

```yaml
triggers:
  - trigger: news_card.new_article
    target:
      entity_id: event.jdn_new_article
    options:
      keywords: [rain, storm]   # optional: title or summary must contain one
actions:
  - action: notify.mobile_app_phone
    data:
      message: "{{ trigger.to_state.attributes.title }}"
```

### Blueprints

Ready-made automations. Click a button to import one, then fill in the form.

| Blueprint | |
|---|---|
| **Notify about new articles** — a phone notification with the image and a link for every new article (optionally only with keywords). | [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fnotify_new_article.yaml) |
| **Read new headlines aloud** — speaks every new headline on your speakers, only during the hours you choose. | [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fspeak_new_article.yaml) |
| **Daily news briefing** — at a set time, sends the latest headlines to your phone and/or reads them aloud, and can mark them as read. | [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fnews_briefing.yaml) |

### Triggers, conditions and actions

| Type | Name | What it does |
|---|---|---|
| Trigger | **New article** (`news_card.new_article`) | Fires for every new article; optional keywords you type. Data: `trigger.to_state.attributes`. |
| Trigger | **No new articles** (`news_card.no_new_articles`) | Fires once when a feed has published nothing for a while (default 12 hours), for example because the site is down. Data: `trigger.feed`, `trigger.last_article`. |
| Condition | **Recent article** (`news_card.recent_article`) | True if a feed published an article within the chosen time, optionally one with keywords. |
| Action | **Send to phone** (`news_card.send_to_phone`) | Sends the latest article (or a short list) to phones with the Home Assistant app, with its image and a link. |
| Action | **Announce on speakers** (`news_card.announce`) | Reads the latest article aloud in your Home Assistant language; music pauses and resumes. |
| Action | `news_card.mark_read` | Marks articles as read (all, or by `article_id`). The card dims them on every device. |
| Action | `news_card.get_entries` | Returns the stored articles; filter by `limit`, `keyword` and `since`. |
| Action | `news_card.refresh` | Downloads the feed now. |

Each feed also has an **Unread articles** sensor.

```yaml
triggers:
  - trigger: news_card.no_new_articles
    target:
      entity_id: event.jdn_new_article
    options:
      for: { hours: 12 }
conditions:
  - condition: news_card.recent_article
    target:
      entity_id: event.ims_new_article
    options:
      within: { hours: 1 }
      keywords: [storm]
actions:
  - action: persistent_notification.create
    data:
      message: "{{ trigger.feed }} has not published since {{ trigger.last_article }}"
```

### More examples

Announce every new article from a feed (state trigger on the event entity; the data is in `trigger.to_state.attributes`):

```yaml
triggers:
  - trigger: state
    entity_id: event.jdn_new_article
    not_from: unavailable
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'new_article' }}"
actions:
  - action: notify.mobile_app_phone
    data:
      title: "{{ trigger.to_state.attributes.source }}"
      message: "{{ trigger.to_state.attributes.title }}"
      data:
        url: "{{ trigger.to_state.attributes.link }}"
        image: "{{ trigger.to_state.attributes.image }}"
```

One automation for all feeds (event trigger; the data is in `trigger.event.data`):

```yaml
triggers:
  - trigger: event
    event_type: news_card_new_article
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.matched_keywords | count > 0 }}"
actions:
  - action: persistent_notification.create
    data:
      title: "{{ trigger.event.data.feed_title }}"
      message: "{{ trigger.event.data.title }} — {{ trigger.event.data.link }}"
```

Read the latest headlines aloud:

```yaml
actions:
  - action: news_card.get_entries
    data:
      entity_id: sensor.jdn_latest_article
      limit: 3
    response_variable: news
  - action: tts.speak
    target:
      entity_id: tts.home_assistant_cloud
    data:
      media_player_entity_id: media_player.kitchen
      message: >
        {% for e in news['sensor.jdn_latest_article'].entries %}{{ e.title }}. {% endfor %}
```

Each article in events and action responses has these fields:
`id, title, link, published, published_estimated, summary, author, source, categories, image, image_proxy, media`.

## Known limitations

- **Dashboards in YAML mode:** the card loads automatically through `frontend.add_extra_js_url`. If it doesn't appear, add the resource `/news_card/frontend/news-card.js` as a JavaScript module.
- **Panel view:** an open frontend issue can show "Configuration error" until the page is refreshed, because custom modules don't always finish loading before panel views render. Sections and masonry views are not affected.
- **HACS store icon:** the local `brand/` icon appears on the integrations page, in setup flows and on device pages. The HACS store tile may still show an empty icon until HACS reads local brand images.
- **Google News:** links point to Google's redirect pages, so article images can't be looked up there.
- **Feedreader entities:** they only provide the latest article.
- **Proxied images:** links signed for the card are valid for 24 hours and are renewed automatically. The `get_entries` action returns the original image URL (`image_proxy` is `null`).

## Troubleshooting

- **Debug logs:** add this to `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.news_card: debug
  ```

- **Diagnostics:** **Settings → Devices & services → News Card → ⋮ → Download diagnostics** shows the last HTTP status, the error, and sample articles.
- **Repair issue "feed unreachable":** the site returned 404/410, or failed for 24 hours. Use **Fix** to enter a new address.
- **The card says "integration not installed":** restart Home Assistant after installing, then clear the browser cache.

## Removal

1. **Settings → Devices & services → News Card → ⋮ → Delete** for each feed. The stored data is deleted too.
2. Remove it in HACS (or delete `custom_components/news_card`), then restart Home Assistant.
3. Remove any News Card cards from your dashboards.

## Development

```bash
pip install -r requirements_test.txt
pytest --cov=custom_components.news_card
```

## License

MIT
