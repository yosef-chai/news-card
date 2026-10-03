# <img src="https://raw.githubusercontent.com/yosef-chai/news-card/main/custom_components/news_card/brand/icon.png" alt="" width="40" height="40"> News Card

[![HACS Custom][hacs-badge]][hacs]
[![GitHub Release][release-badge]][release]
[![Home Assistant][ha-badge]][ha]
[![Validate][validate-badge]][validate]
[![Tests][tests-badge]][tests]
[![License][license-badge]][license]

**English** | [עברית][readme-he]

News feeds for Home Assistant, installed together as one package:

- An **integration** that reads any RSS, Atom, RDF or JSON Feed and turns it into entities, events, actions and alerts.
- A **dashboard card** that shows the news as a list or as a ticker that scrolls endlessly.

<img src="https://raw.githubusercontent.com/yosef-chai/news-card/main/assets/preview.png" width="520" alt="News Card showing five articles in a list, and a scrolling ticker below it">

**[Features](#features)** · **[Installation](#installation)** · **[Configuration](#configuration)** · **[Card](#card)** · **[Automations](#automations)** · **[Troubleshooting](#troubleshooting)**

## Features

- **Reads any feed.** RSS 0.9x, 1.0 and 2.0, Atom, RDF, CDF and JSON Feed 1.0 and 1.1. A feed is recognized by its content, so RSS served as `text/html`, a BOM, or a server warning before the XML all work.
- **Finds the feed for you.** Paste a website address and you get the feeds it publishes. If it publishes none, the usual addresses (`/feed`, `/rss`, `/atom.xml` and more) and the page's "RSS" links are checked too. Feeds you already have in Feedreader are offered in a list.
- **Clean articles.** HTML, character entities and double-escaped HTML are cleaned up. Non-UTF-8 feeds (for example windows-1255 Hebrew) are decoded correctly. Boilerplate like "The post … appeared first on …" is removed, and authors are names without emails.
- **Images.** Each article gets the best image it has: `media:content`, `media:thumbnail`, `itunes:image`, an enclosure, or the first real `<img>`. A podcast episode falls back to the show's artwork. If an article has no image at all, its page's share image (`og:image`) is looked up.
- **Image proxy.** Images can load through Home Assistant, which fixes sites that block hotlinking and `http` images on an `https` dashboard.
- **The card.** List or ticker, with image, date, time, source and author toggles. Sorting, a limit, absolute or relative time, a summary dialog, dimmed read articles, a visual editor, sections-view sizing, English and Hebrew, right-to-left support.
- **Alerts without automations.** Send new articles to phones and speakers, or a roundup at a set time, right from the feed page.
- **Automations.** New article and No new articles triggers, a Recent article condition, five actions, three blueprints, an event entity and a bus event.
- **Reliable.** Downloads only when the feed changed. Keeps showing the last good copy while a site is down. Slows down after failures and follows `Retry-After`. Opens a repair issue when a feed needs your help.

### Use cases

- A **breaking news ticker** at the bottom of a wall tablet.
- The **weather forecast** read aloud on the kitchen speaker every morning.
- A phone alert when a feed mentions **"storm"** or **"road closed"**.
- A **daily briefing** of the top headlines, sent to your phone and marked as read.
- New **podcast episodes**, **GitHub releases** or **YouTube uploads**, since they're feeds too.
- An alert when a feed **stops publishing**, for example because the site is down.

## Installation

Requires Home Assistant 2026.9 or newer.

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.][my-hacs-badge]][my-hacs]

1. Select the button above. Or in HACS, open **⋮ → Custom repositories** and add `https://github.com/yosef-chai/news-card` as **Integration**.
2. Search for **News Card** and select **Download**.
3. Restart Home Assistant.

> [!NOTE]
> The card is registered automatically. You don't need to add a dashboard resource.

### Manual

1. Download **Source code (zip)** from the [latest release][release].
2. Copy `custom_components/news_card` into your `config/custom_components/` folder.
3. Restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.][my-flow-badge]][my-flow]

Select the button, or go to **Settings → Devices & services → Add integration → News Card**, and enter a feed or website address. Each feed is its own entry and device. To change the address later, use **⋮ → Reconfigure**. Everything else is under **Configure**.

| Option | Default | Description |
| --- | --- | --- |
| Feed or website address | — | A feed URL, or a website URL whose feeds are discovered for you. |
| Check the security certificate | on | Turn off only for a site you know whose certificate is broken. |
| Update interval | 15 min | 5–1440 minutes. |
| Articles to keep | 30 | 1–100. |
| Keywords | — | Comma or line separated. A new article that mentions one fires `keyword_match`. |
| Load images through Home Assistant | on | The image proxy. |
| Find missing images on the article page | on | Reads the page's share image (`og:image`) for articles that have none. |
| User-Agent when the site refuses | — | **Browser** (a current Chrome) or any text. Sent only after the site refuses the normal request (403, 406, 429). Once it works, it's used directly for 24 hours, and then the normal request is tried again. |

### Entities

Each feed gets one device with these entities:

| Entity | Description |
| --- | --- |
| `sensor.<feed>_latest_article` | Title of the newest article. Attributes: `entry_id`, `link`, `summary`, `published`, `source`, `image`. |
| `sensor.<feed>_unread_articles` | Articles not marked as read yet. |
| `sensor.<feed>_articles` | Number of stored articles (diagnostic). |
| `sensor.<feed>_last_update` | Last successful download (diagnostic). |
| `event.<feed>_new_article` | Fires `new_article` for every new article, and `keyword_match` when it mentions a keyword. The article's fields are its attributes. |

Every article has these fields: `id`, `title`, `link`, `published`, `published_estimated`, `summary`, `author`, `source`, `categories`, `image`, `image_proxy`, `media`.

### How data updates

- The feed is checked at the update interval. An unchanged feed costs one request and no parsing (ETag and Last-Modified).
- New articles fire events once each. Nothing fires on the first download, after a restart, or when you raise the number of articles to keep.
- After a failure, the next check waits twice as long each time, up to an hour, and longer if the site asks for it with `Retry-After`. The last good copy stays in place, and the card marks it as outdated.
- The card gets updates pushed over a WebSocket subscription, so it never polls.

## Card

Add **News Card** from the dashboard editor and pick one or more **news sources** by name. Every option is in the visual editor.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `type` | string | **required** | `custom:news-card` |
| `feeds` | list | — | News sources by device ID. This is what the visual editor saves. |
| `entities` | list | — | News sources by entity: any News Card entity of a feed, or a Feedreader `event` entity (latest article only). You can combine `feeds` and `entities`. |
| `title` | string | — | Card title. In the ticker, it's the label before the headlines. |
| `display` | `list` \| `ticker` | `list` | A list, or a ticker that scrolls endlessly. |
| `show_image` | boolean | `true` | Article image. |
| `show_date` | boolean | `true` | Publication date. |
| `show_time` | boolean | `true` | Publication time. |
| `show_source` | boolean | `true` | Source name. |
| `show_author` | boolean | `false` | Author name. |
| `date_format` | `absolute` \| `relative` | `absolute` | `relative` shows "5 minutes ago" while `show_date` or `show_time` is on. |
| `sort` | `desc` \| `asc` \| `random` | `desc` | Newest first, oldest first, or random. |
| `max_items` | number | `30` | 1–100, across all sources. |
| `tap_action` | `link` \| `dialog` \| `none` | `link` | Open the article, show its summary in a dialog, or do nothing. |
| `mark_read` | boolean | `false` | Dim articles you opened. For News Card feeds this is saved in Home Assistant, so it's shared by every device and counted by the Unread articles sensor. |
| `auto_scroll` | boolean | `false` | List only. When the card has a fixed height and the articles don't fit, the list scrolls by itself. |
| `scroll_speed` | number | `30` | Pixels per second (5–100) for the ticker and the scrolling list. |

```yaml
type: custom:news-card
entities:
  - sensor.jdn_latest_article
```

<details>
<summary>Every option, with its default</summary>

```yaml
type: custom:news-card
entities:
  - sensor.jdn_latest_article
  - sensor.cnn_latest_article
title: News
display: list
show_image: true
show_date: true
show_time: true
show_source: true
show_author: false
date_format: absolute
sort: desc
max_items: 30
tap_action: link
mark_read: false
auto_scroll: false
scroll_speed: 30
```

</details>

<details>
<summary>A ticker at the bottom of a dashboard</summary>

```yaml
type: custom:news-card
entities:
  - sensor.jdn_latest_article
display: ticker
title: Breaking
show_date: false
scroll_speed: 40
```

</details>

- Articles from several feeds are merged into one list, sorted by date, without duplicates.
- The ticker moves left to right in right-to-left languages such as Hebrew, and right to left otherwise.
- Scrolling pauses while you hover over it, use the keyboard, or read an article, and resumes when you come back. It doesn't move when your system asks for reduced motion.

## Automations

### Triggers, conditions and actions

| Type | Name | What it does |
| --- | --- | --- |
| Trigger | **New article** (`news_card.new_article`) | Fires for every new article in the target feeds (entities, devices or areas). Option: `keywords`. The article is in `trigger.to_state.attributes`. |
| Trigger | **No new articles** (`news_card.no_new_articles`) | Fires once when a feed publishes nothing for a while (option `for`, default 12 hours), for example because the site is down. Data: `trigger.feed`, `trigger.last_article`. |
| Condition | **Recent article** (`news_card.recent_article`) | True if a feed published an article within the chosen time (option `within`, default 1 hour). Option: `keywords`. |
| Action | **Get articles** (`news_card.get_entries`) | Returns the stored articles without downloading. Fields: `limit`, `keyword`, `since`. |
| Action | **Refresh** (`news_card.refresh`) | Downloads the feed now. |
| Action | **Mark as read** (`news_card.mark_read`) | Marks articles as read: all of them, or the ones in `article_id`. The card dims them on every device. |
| Action | **Send to phone** (`news_card.send_to_phone`) | Sends the latest article, or a short list (`count`), to phones with the Home Assistant app, with its image and a link. |
| Action | **Announce on speakers** (`news_card.announce`) | Reads the latest article aloud in your Home Assistant language. Music pauses and then resumes. |

For all feeds at once, there's also the `news_card_new_article` bus event. Its data is the article's fields plus `entity_id`, `config_entry_id`, `feed_title`, `feed_url` and `matched_keywords`.

### Blueprints

Ready-made automations. Select a button to import one, then fill in the form.

| Blueprint | |
| --- | --- |
| **Notify about new articles.** A phone notification with the image and a link for every new article, optionally only with keywords. | [![Import blueprint][bp-badge]](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fnotify_new_article.yaml) |
| **Read new headlines aloud.** Every new headline on your speakers, only during the hours you choose. | [![Import blueprint][bp-badge]](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fspeak_new_article.yaml) |
| **Daily news briefing.** At a set time, the latest headlines to your phone, your speakers or both, and optionally marked as read. | [![Import blueprint][bp-badge]](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fnews_briefing.yaml) |

### Alerts without automations

Go to **Settings → Devices & services → News Card → your feed → Add alert**.

1. Choose **when**: every new article, or every day at a set time on the days you pick.
2. Choose **where**: phones with the Home Assistant app are already selected. Add speakers to hear it too.
3. Optionally add keywords, the article summary (good for weather forecasts), and the hours when the speakers may talk.

The speakers announce in your Home Assistant language and then resume what was playing. Outside the speaking hours, only the phone gets the alert. A feed can have several alerts, and you edit or delete them from the same page.

### Examples

<details>
<summary>A phone alert for new articles that mention a keyword</summary>

```yaml
triggers:
  - trigger: news_card.new_article
    target:
      entity_id: event.jdn_new_article
    options:
      keywords: [rain, storm]
actions:
  - action: notify.mobile_app_phone
    data:
      title: "{{ trigger.to_state.attributes.source }}"
      message: "{{ trigger.to_state.attributes.title }}"
      data:
        url: "{{ trigger.to_state.attributes.link }}"
        image: "{{ trigger.to_state.attributes.image }}"
```

</details>

<details>
<summary>The weather forecast at 9:00 every day except Saturday, to the phone and a speaker</summary>

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
      phones: <your phone device>
      include_summary: true
  - action: news_card.announce
    data:
      entity_id: sensor.ims_latest_article
      speakers: media_player.kitchen
      include_summary: true
```

</details>

<details>
<summary>A notification when a feed goes quiet</summary>

```yaml
triggers:
  - trigger: news_card.no_new_articles
    target:
      entity_id: event.jdn_new_article
    options:
      for: { hours: 12 }
actions:
  - action: persistent_notification.create
    data:
      message: "{{ trigger.feed }} hasn't published since {{ trigger.last_article }}"
```

</details>

<details>
<summary>Read the latest headlines aloud with <code>get_entries</code></summary>

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

</details>

<details>
<summary>One automation for every feed, with the bus event</summary>

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
      message: "{{ trigger.event.data.title }}: {{ trigger.event.data.link }}"
```

</details>

## Known limitations

- **Sites that refuse feed readers.** When a site answers 403, 406 or 429, setup offers to try again with a different User-Agent, and an existing feed gets a repair issue where you can set one. Some sites (for example gov.il, Kan, Times of Israel and AP) show a JavaScript challenge (Cloudflare, DataDome, Imperva) that only a real browser passes. No User-Agent helps there, so none is offered.
- **Feeds that need a login** aren't supported.
- **Google News** links point to Google's redirect pages, so article images can't be looked up there.
- **Very large feeds** over 10 MB, such as long-running podcasts, are read up to 10 MB. That part holds the newest episodes.
- **Feedreader entities** only provide the latest article.
- **Image links** signed for the card are valid for 24 hours and renewed automatically. `get_entries` returns the original image address, and `image_proxy` is `null` there.
- **Dashboards in YAML mode, or Home Assistant Cast.** The card loads automatically. If it doesn't appear, add `/news_card/frontend/news-card.js` as a dashboard resource of type JavaScript module.
- **Panel view.** An open frontend issue can show "Configuration error" until the page is refreshed, because custom modules don't always load before panel views render. Sections and masonry views aren't affected.
- **The HACS store tile** may show an empty icon. The integrations page, setup flows and device pages show the icon as usual.

## Troubleshooting

### A feed isn't updating

The card marks it as **outdated**, and hovering over the label shows why. Check **Settings → Repairs**: a feed that moved, was removed or is refused gets a repair issue, where you can enter a new address or a User-Agent.

### The card says the integration isn't installed

Restart Home Assistant after installing, then refresh the browser and clear its cache.

### Images don't load

Turn on **Load images through Home Assistant** in the feed options. It fixes sites that block hotlinking and `http` images on an `https` dashboard.

### Debug logs and diagnostics

Add this to `configuration.yaml` and restart:

```yaml
logger:
  default: warning
  logs:
    custom_components.news_card: debug
```

Diagnostics are under **Settings → Devices & services → News Card → ⋮ → Download diagnostics**. They show the last HTTP status, the error and sample articles, without the feed's tokens. Attach them when you [open an issue][issues].

## Removal

1. Go to **Settings → Devices & services → News Card**, and for each feed select **⋮ → Delete**. Its stored data is deleted too.
2. Remove News Card in HACS (or delete `config/custom_components/news_card`), then restart Home Assistant.
3. Remove the News Card cards from your dashboards.

## Contributing

Bug reports and ideas are welcome in [issues][issues]. Translations live in [`custom_components/news_card/translations`][translations] and in the `STRINGS` table of the card.

To run the checks on Linux, macOS or WSL:

```bash
pip install -r requirements_test.txt
pytest --cov=custom_components.news_card
mypy
```

## License

[MIT][license] © Yosef Chai

<!-- Links -->
[hacs]: https://hacs.xyz
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[release]: https://github.com/yosef-chai/news-card/releases/latest
[release-badge]: https://img.shields.io/github/v/release/yosef-chai/news-card
[ha]: https://www.home-assistant.io
[ha-badge]: https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fyosef-chai%2Fnews-card%2Fmain%2Fhacs.json&query=%24.homeassistant&prefix=%E2%89%A5%20&label=Home%20Assistant&logo=homeassistant&color=41BDF5
[validate]: https://github.com/yosef-chai/news-card/actions/workflows/validate.yml
[validate-badge]: https://img.shields.io/github/actions/workflow/status/yosef-chai/news-card/validate.yml?branch=main&label=validate
[tests]: https://github.com/yosef-chai/news-card/actions/workflows/tests.yml
[tests-badge]: https://img.shields.io/github/actions/workflow/status/yosef-chai/news-card/tests.yml?branch=main&label=tests
[license]: https://github.com/yosef-chai/news-card/blob/main/LICENSE
[license-badge]: https://img.shields.io/github/license/yosef-chai/news-card
[readme-he]: https://github.com/yosef-chai/news-card/blob/main/README.he.md
[issues]: https://github.com/yosef-chai/news-card/issues
[translations]: https://github.com/yosef-chai/news-card/tree/main/custom_components/news_card/translations
[my-hacs]: https://my.home-assistant.io/redirect/hacs_repository/?owner=yosef-chai&repository=news-card&category=integration
[my-hacs-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[my-flow]: https://my.home-assistant.io/redirect/config_flow_start/?domain=news_card
[my-flow-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
[bp-badge]: https://my.home-assistant.io/badges/blueprint_import.svg
