<div dir="rtl">

# <img src="https://raw.githubusercontent.com/yosef-chai/news-card/main/custom_components/news_card/brand/icon.png" alt="" width="40" height="40"> News Card

[![HACS Custom][hacs-badge]][hacs]
[![GitHub Release][release-badge]][release]
[![Home Assistant][ha-badge]][ha]
[![Validate][validate-badge]][validate]
[![Tests][tests-badge]][tests]
[![License][license-badge]][license]

[English][readme-en] | **עברית**

חדשות מפידים ל-Home Assistant, בחבילה אחת שמותקנת יחד:

- **אינטגרציה** שקוראת כל פיד RSS, ‏Atom, ‏RDF או JSON Feed, והופכת אותו לישויות, אירועים, פעולות והתראות.
- **כרטיס ללוח המחוונים** שמציג את החדשות כרשימה, או כפס רץ בגלילה אינסופית.

<img src="https://raw.githubusercontent.com/yosef-chai/news-card/main/assets/preview-he.png" width="520" alt="News Card עם חמש כתבות ברשימה, ומתחתיו פס רץ">

**[יכולות](#יכולות)** · **[התקנה](#התקנה)** · **[הגדרה](#הגדרה)** · **[הכרטיס](#הכרטיס)** · **[אוטומציות](#אוטומציות)** · **[פתרון תקלות](#פתרון-תקלות)**

## יכולות

- **קורא כל פיד.** ‏RSS 0.9x, ‏1.0 ו-2.0, ‏Atom, ‏RDF, ‏CDF ו-JSON Feed 1.0 ו-1.1. הפיד מזוהה לפי התוכן, ולכן גם RSS שמוגש כ-`text/html`, ‏BOM או אזהרה של השרת לפני ה-XML לא מפריעים.
- **מוצא את הפיד בשבילך.** מדביקים כתובת של אתר ומקבלים את הפידים שהוא מפרסם. אם האתר לא מצהיר על פיד, נבדקות גם הכתובות המקובלות (`/feed`, ‏`/rss`, ‏`/atom.xml` ועוד) והקישורים "RSS" שבדף. פידים שכבר יש לך ב-Feedreader מוצעים ברשימה.
- **כתבות נקיות.** ‏HTML, ישויות תווים ו-HTML שקודד פעמיים מנוקים. פידים שלא ב-UTF-8 (למשל עברית ב-windows-1255) מפוענחים נכון. שורות קבועות כמו "The post … appeared first on …" יורדות, ושמות הכותבים מגיעים בלי מייל.
- **תמונות.** כל כתבה מקבלת את התמונה הכי טובה שיש לה: `media:content`, ‏`media:thumbnail`, ‏`itunes:image`, קובץ מצורף, או ה-`<img>` האמיתי הראשון. פרק בפודקאסט מקבל את תמונת התוכנית. לכתבה בלי שום תמונה נבדקת תמונת השיתוף של הדף שלה (`og:image`).
- **פרוקסי לתמונות.** התמונות יכולות להיטען דרך Home Assistant, וזה פותר אתרים שחוסמים קישור ישיר ותמונות `http` בלוח `https`.
- **הכרטיס.** רשימה או פס רץ, עם בחירה אם להציג תמונה, תאריך, שעה, מקור וכותב. מיון, הגבלת כמות, זמן מלא או יחסי, חלון תקציר, עמעום כתבות שנקראו, עורך חזותי, התאמה לגודל בתצוגת Sections, עברית ואנגלית ותמיכה מלאה בימין לשמאל.
- **התראות בלי אוטומציות.** כתבות חדשות לטלפון ולרמקולים, או ריכוז בשעה קבועה, ישר מדף הפיד.
- **אוטומציות.** טריגרים "כתבה חדשה" ו"אין כתבות חדשות", תנאי "כתבה מהזמן האחרון", חמש פעולות, שלושה Blueprints, ישות אירוע ואירוע bus.
- **אמין.** מוריד רק כשהפיד השתנה. ממשיך להציג את העותק הטוב האחרון כשהאתר נופל. מאט אחרי כשלים ומכבד `Retry-After`. פותח הודעה במרכז התיקונים כשפיד צריך את העזרה שלך.

### שימושים לדוגמה

- **פס מבזקים** בתחתית טאבלט על הקיר.
- **תחזית מזג האוויר** שמוקראת כל בוקר ברמקול במטבח.
- התראה לטלפון כשפיד מזכיר **"סערה"** או **"כביש חסום"**.
- **תקציר יומי** של הכותרות הראשיות, לטלפון, עם סימון שנקראו.
- **פרקים חדשים בפודקאסט**, **גרסאות חדשות ב-GitHub** או **סרטונים חדשים ביוטיוב**, כי גם הם פידים.
- התראה כשפיד **מפסיק לפרסם**, למשל כי האתר נפל.

## התקנה

דורש Home Assistant 2026.9 ומעלה.

### דרך HACS (מומלץ)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.][my-hacs-badge]][my-hacs]

1. לוחצים על הכפתור. או ב-HACS פותחים **⋮ ← Custom repositories** ומוסיפים את `https://github.com/yosef-chai/news-card` בקטגוריה **Integration**.
2. מחפשים **News Card** ולוחצים **Download**.
3. מפעילים מחדש את Home Assistant.

> [!NOTE]
> הכרטיס נרשם אוטומטית, בלי צורך להוסיף משאב ללוח.

### התקנה ידנית

1. מורידים את **Source code (zip)** מ[הגרסה האחרונה][release].
2. מעתיקים את `custom_components/news_card` לתיקייה `config/custom_components/`.
3. מפעילים מחדש את Home Assistant.

## הגדרה

[![Open your Home Assistant instance and start setting up a new integration.][my-flow-badge]][my-flow]

לוחצים על הכפתור, או נכנסים ל**הגדרות ← מכשירים ושירותים ← הוספת שילוב ← News Card**, ומזינים כתובת של פיד או של אתר. כל פיד הוא רשומה ומכשיר נפרדים. את הכתובת משנים אחר כך ב-**⋮ ← הגדרה מחדש**, וכל השאר נמצא ב**הגדרות**.

| אפשרות | ברירת מחדל | הסבר |
| --- | --- | --- |
| כתובת הפיד או האתר | — | כתובת של פיד, או של אתר שהפידים שלו יימצאו לבד. |
| בדיקת תעודת האבטחה | פעיל | כדאי לכבות רק באתר שמכירים והתעודה שלו שבורה. |
| תדירות עדכון | ‏15 דק' | ‏5–1440 דקות. |
| כמה כתבות לשמור | ‏30 | ‏1–100. |
| מילות מפתח | — | מופרדות בפסיק או בשורה חדשה. כתבה חדשה שמזכירה אחת מהן מפעילה `keyword_match`. |
| טעינת תמונות דרך Home Assistant | פעיל | הפרוקסי לתמונות. |
| חיפוש תמונה חסרה בדף הכתבה | פעיל | לכתבה בלי תמונה, לוקחים את תמונת השיתוף מהדף (`og:image`). |
| User-Agent כשהאתר מסרב | — | **דפדפן** (Chrome עדכני) או כל טקסט. נשלח רק אחרי שהאתר דחה את הבקשה הרגילה (403, ‏406, ‏429). אחרי שהוא עובד משתמשים בו ישירות 24 שעות, ואז מנסים שוב את הרגיל. |

### ישויות

לכל פיד יש מכשיר אחד עם הישויות האלה:

| ישות | הסבר |
| --- | --- |
| `sensor.<feed>_latest_article` | הכותרת של הכתבה החדשה ביותר. מאפיינים: `entry_id`, ‏`link`, ‏`summary`, ‏`published`, ‏`source`, ‏`image`. |
| `sensor.<feed>_unread_articles` | כתבות שעוד לא סומנו כנקראו. |
| `sensor.<feed>_articles` | מספר הכתבות השמורות (אבחון). |
| `sensor.<feed>_last_update` | ההורדה המוצלחת האחרונה (אבחון). |
| `event.<feed>_new_article` | מפעיל `new_article` על כל כתבה חדשה, ו-`keyword_match` כשהיא מזכירה מילת מפתח. שדות הכתבה הם המאפיינים שלו. |

לכל כתבה יש השדות: `id`, ‏`title`, ‏`link`, ‏`published`, ‏`published_estimated`, ‏`summary`, ‏`author`, ‏`source`, ‏`categories`, ‏`image`, ‏`image_proxy`, ‏`media`.

### איך הנתונים מתעדכנים

- הפיד נבדק לפי תדירות העדכון. פיד שלא השתנה עולה בקשה אחת, בלי ניתוח (ETag ו-Last-Modified).
- כל כתבה חדשה מפעילה אירועים פעם אחת. כלום לא מופעל בהורדה הראשונה, אחרי הפעלה מחדש, או כשמגדילים את מספר הכתבות לשמירה.
- אחרי כשל, ההמתנה עד הבדיקה הבאה מוכפלת בכל פעם, עד שעה, ויותר אם האתר מבקש ב-`Retry-After`. העותק הטוב האחרון נשאר, והכרטיס מסמן אותו כלא עדכני.
- הכרטיס מקבל עדכונים בדחיפה דרך מנוי WebSocket, ולכן אף פעם לא שואל שוב ושוב.

## הכרטיס

מוסיפים את **News Card** מעורך הלוח ובוחרים **מקורות חדשות** לפי השם. כל האפשרויות נמצאות בעורך החזותי.

| שם | סוג | ברירת מחדל | הסבר |
| --- | --- | --- | --- |
| `type` | string | **חובה** | `custom:news-card` |
| `feeds` | list | — | מקורות לפי מזהה מכשיר. זה מה שהעורך החזותי שומר. |
| `entities` | list | — | מקורות לפי ישות: כל ישות של פיד News Card, או ישות `event` של Feedreader (הכתבה האחרונה בלבד). אפשר לשלב עם `feeds`. |
| `title` | string | — | כותרת הכרטיס. בפס הרץ זו התווית שלפני הכותרות. |
| `display` | `list` \| `ticker` | `list` | רשימה, או פס רץ בגלילה אינסופית. |
| `show_image` | boolean | `true` | תמונת הכתבה. |
| `show_date` | boolean | `true` | תאריך הפרסום. |
| `show_time` | boolean | `true` | שעת הפרסום. |
| `show_source` | boolean | `true` | שם המקור. |
| `show_author` | boolean | `false` | שם הכותב. |
| `date_format` | `absolute` \| `relative` | `absolute` | ‏`relative` מציג "לפני 5 דקות", כש-`show_date` או `show_time` פעילים. |
| `sort` | `desc` \| `asc` \| `random` | `desc` | החדשות קודם, הישנות קודם, או אקראי. |
| `max_items` | number | `30` | ‏1–100, מכל המקורות יחד. |
| `tap_action` | `link` \| `dialog` \| `none` | `link` | פתיחת הכתבה, הצגת התקציר בחלון, או כלום. |
| `mark_read` | boolean | `false` | עמעום כתבות שנפתחו. בפידים של News Card זה נשמר ב-Home Assistant, ולכן משותף לכל המכשירים ונספר בחיישן הכתבות שלא נקראו. |
| `auto_scroll` | boolean | `false` | רק לרשימה. כשלכרטיס יש גובה קבוע והכתבות לא נכנסות, הרשימה גוללת לבד. |
| `scroll_speed` | number | `30` | פיקסלים לשנייה (5–100), לפס הרץ ולרשימה הגוללת. |

<div dir="ltr">

```yaml
type: custom:news-card
entities:
  - sensor.jdn_latest_article
```

</div>

<details>
<summary>כל האפשרויות, עם ברירות המחדל</summary>

<div dir="ltr">

```yaml
type: custom:news-card
entities:
  - sensor.jdn_latest_article
  - sensor.cnn_latest_article
title: חדשות
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

</div>

</details>

<details>
<summary>פס רץ בתחתית הלוח</summary>

<div dir="ltr">

```yaml
type: custom:news-card
entities:
  - sensor.jdn_latest_article
display: ticker
title: מבזקים
show_date: false
scroll_speed: 40
```

</div>

</details>

- כתבות מכמה פידים מתמזגות לרשימה אחת, ממוינות לפי תאריך ובלי כפילויות.
- בשפה שנכתבת מימין לשמאל, כמו עברית, הפס הרץ זז משמאל לימין, ובשאר השפות מימין לשמאל.
- הגלילה עוצרת כשמעבירים עליה את העכבר, כשמשתמשים במקלדת או כשקוראים כתבה, וממשיכה כשחוזרים. כשהמערכת מבקשת להפחית תנועה, היא לא זזה בכלל.

## אוטומציות

### טריגרים, תנאים ופעולות

| סוג | שם | מה עושה |
| --- | --- | --- |
| טריגר | **כתבה חדשה** (`news_card.new_article`) | מופעל על כל כתבה חדשה בפידים שנבחרו (ישויות, מכשירים או אזורים). אפשרות: `keywords`. הכתבה נמצאת ב-`trigger.to_state.attributes`. |
| טריגר | **אין כתבות חדשות** (`news_card.no_new_articles`) | מופעל פעם אחת כשפיד לא מפרסם כלום זמן מה (אפשרות `for`, ברירת מחדל 12 שעות), למשל כי האתר נפל. נתונים: `trigger.feed`, ‏`trigger.last_article`. |
| תנאי | **כתבה מהזמן האחרון** (`news_card.recent_article`) | נכון אם פיד פרסם כתבה בטווח הזמן שנבחר (אפשרות `within`, ברירת מחדל שעה). אפשרות: `keywords`. |
| פעולה | **קבלת כתבות** (`news_card.get_entries`) | מחזירה את הכתבות השמורות, בלי להוריד שוב. שדות: `limit`, ‏`keyword`, ‏`since`. |
| פעולה | **רענון** (`news_card.refresh`) | מורידה את הפיד עכשיו. |
| פעולה | **סימון כנקרא** (`news_card.mark_read`) | מסמנת כתבות כנקראו: את כולן, או את אלה שב-`article_id`. הכרטיס מעמעם אותן בכל המכשירים. |
| פעולה | **שליחה לטלפון** (`news_card.send_to_phone`) | שולחת את הכתבה האחרונה, או רשימה קצרה (`count`), לטלפונים עם אפליקציית Home Assistant, עם תמונה וקישור. |
| פעולה | **הכרזה ברמקולים** (`news_card.announce`) | מקריאה את הכתבה האחרונה בשפה של Home Assistant. מוזיקה שמתנגנת עוצרת וממשיכה. |

לכל הפידים יחד יש גם את אירוע ה-bus `news_card_new_article`. הנתונים שלו הם שדות הכתבה, ועוד `entity_id`, ‏`config_entry_id`, ‏`feed_title`, ‏`feed_url` ו-`matched_keywords`.

### Blueprints

אוטומציות מוכנות. לוחצים על כפתור כדי לייבא, וממלאים את הטופס.

| Blueprint | |
| --- | --- |
| **התראה על כתבות חדשות.** התראה לטלפון עם תמונה וקישור על כל כתבה חדשה, ואפשר רק עם מילות מפתח. | [![Import blueprint][bp-badge]](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fnotify_new_article.yaml) |
| **הקראת כותרות חדשות.** כל כותרת חדשה ברמקולים, רק בשעות שבוחרים. | [![Import blueprint][bp-badge]](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fspeak_new_article.yaml) |
| **סיכום חדשות יומי.** בשעה קבועה, הכותרות האחרונות לטלפון, לרמקולים או לשניהם, ואפשר גם לסמן אותן כנקראו. | [![Import blueprint][bp-badge]](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fnews_briefing.yaml) |

### התראות בלי אוטומציות

נכנסים ל**הגדרות ← מכשירים ושירותים ← News Card ← הפיד ← הוספת התראה**.

1. בוחרים **מתי**: על כל כתבה חדשה, או כל יום בשעה קבועה, בימים שבוחרים.
2. בוחרים **לאן**: טלפונים עם אפליקציית Home Assistant כבר מסומנים. מוסיפים רמקולים כדי גם לשמוע.
3. אפשר להוסיף מילות מפתח, את תקציר הכתבה (מתאים לתחזית מזג אוויר) ואת השעות שבהן מותר לרמקולים לדבר.

הרמקולים מכריזים בשפה של Home Assistant, ואחר כך ממשיכים את מה שהתנגן. מחוץ לשעות ההשמעה ההתראה מגיעה רק לטלפון. לכל פיד אפשר להוסיף כמה התראות, ולערוך או למחוק אותן מאותו דף.

### דוגמאות

<details>
<summary>התראה לטלפון על כתבות חדשות שמזכירות מילת מפתח</summary>

<div dir="ltr">

```yaml
triggers:
  - trigger: news_card.new_article
    target:
      entity_id: event.jdn_new_article
    options:
      keywords: [גשם, סערה]
actions:
  - action: notify.mobile_app_phone
    data:
      title: "{{ trigger.to_state.attributes.source }}"
      message: "{{ trigger.to_state.attributes.title }}"
      data:
        url: "{{ trigger.to_state.attributes.link }}"
        image: "{{ trigger.to_state.attributes.image }}"
```

</div>

</details>

<details>
<summary>תחזית מזג האוויר ב-9:00 בכל יום חוץ משבת, לטלפון ולרמקול</summary>

<div dir="ltr">

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

</div>

</details>

<details>
<summary>הודעה כשפיד שותק</summary>

<div dir="ltr">

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
      message: "{{ trigger.feed }} לא פרסם מאז {{ trigger.last_article }}"
```

</div>

</details>

<details>
<summary>הקראת הכותרות האחרונות עם <code>get_entries</code></summary>

<div dir="ltr">

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

</div>

</details>

<details>
<summary>אוטומציה אחת לכל הפידים, עם אירוע ה-bus</summary>

<div dir="ltr">

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

</div>

</details>

## מגבלות ידועות

- **אתרים שמסרבים לקוראי פידים.** כשאתר עונה 403, ‏406 או 429, ההוספה מציעה לנסות שוב עם User-Agent אחר, ופיד קיים מקבל הודעה במרכז התיקונים שבה אפשר לבחור אחד. חלק מהאתרים (למשל gov.il, כאן, Times of Israel ו-AP) מציגים אתגר JavaScript ‏(Cloudflare, ‏DataDome, ‏Imperva) שרק דפדפן אמיתי עובר. שם שום User-Agent לא עוזר, ולכן הוא לא מוצע.
- **פידים שדורשים כניסה** לא נתמכים.
- **Google News:** הקישורים הם דפי הפניה של Google, ולכן אין משם תמונות לכתבות.
- **פידים גדולים מאוד** מעל 10MB, כמו פודקאסט ותיק, נקראים עד 10MB. שם נמצאים הפרקים החדשים.
- **ישויות Feedreader** מספקות רק את הכתבה האחרונה.
- **קישורי התמונות** שנחתמים לכרטיס תקפים 24 שעות ומתחדשים לבד. ‏`get_entries` מחזירה את כתובת התמונה המקורית, ושם `image_proxy` הוא `null`.
- **לוחות במצב YAML, או Home Assistant Cast.** הכרטיס נטען אוטומטית. אם הוא לא מופיע, מוסיפים את `/news_card/frontend/news-card.js` כמשאב לוח מסוג JavaScript module.
- **תצוגת Panel.** תקלה פתוחה בממשק עלולה להציג "שגיאת תצורה" עד רענון הדף, כי מודולים חיצוניים לא תמיד נטענים לפני שתצוגות Panel מוצגות. בתצוגות Sections ו-Masonry זה לא קורה.
- **האריח בחנות של HACS** עלול להופיע בלי אייקון. בדף השילובים, בתהליכי ההגדרה ובדפי המכשירים האייקון מוצג כרגיל.

## פתרון תקלות

### פיד לא מתעדכן

הכרטיס מסמן אותו כ**לא עדכני**, ומעבר עם העכבר על התווית מסביר למה. כדאי להציץ ב**הגדרות ← תיקונים**: פיד שעבר כתובת, נמחק או שהאתר מסרב לו מקבל שם הודעה, ושם אפשר להזין כתובת חדשה או User-Agent.

### הכרטיס אומר שהאינטגרציה לא מותקנת

מפעילים מחדש את Home Assistant אחרי ההתקנה, ואז מרעננים את הדפדפן ומנקים את המטמון שלו.

### תמונות לא נטענות

מפעילים את **טעינת תמונות דרך Home Assistant** בהגדרות הפיד. זה פותר אתרים שחוסמים קישור ישיר ותמונות `http` בלוח `https`.

### לוג דיבאג ואבחון

מוסיפים את זה ל-`configuration.yaml` ומפעילים מחדש:

<div dir="ltr">

```yaml
logger:
  default: warning
  logs:
    custom_components.news_card: debug
```

</div>

קובץ האבחון נמצא ב**הגדרות ← מכשירים ושירותים ← News Card ← ⋮ ← הורדת אבחון**. יש בו את סטטוס ה-HTTP האחרון, השגיאה וכמה כתבות לדוגמה, בלי הטוקנים של הפיד. כדאי לצרף אותו כש[פותחים תקלה][issues].

## הסרה

1. נכנסים ל**הגדרות ← מכשירים ושירותים ← News Card**, ובכל פיד בוחרים **⋮ ← מחיקה**. גם הנתונים השמורים שלו נמחקים.
2. מסירים את News Card ב-HACS (או מוחקים את `config/custom_components/news_card`) ומפעילים מחדש את Home Assistant.
3. מסירים את כרטיסי News Card מהלוחות.

## תרומה לפרויקט

דיווחי תקלות ורעיונות מתקבלים בשמחה ב-[issues][issues]. התרגומים נמצאים ב-[`custom_components/news_card/translations`][translations] ובטבלה `STRINGS` של הכרטיס.

הרצת הבדיקות ב-Linux, ‏macOS או WSL:

<div dir="ltr">

```bash
pip install -r requirements_test.txt
pytest --cov=custom_components.news_card
mypy
```

</div>

## רישיון

[MIT][license] © Yosef Chai

</div>

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
[readme-en]: https://github.com/yosef-chai/news-card/blob/main/README.md
[issues]: https://github.com/yosef-chai/news-card/issues
[translations]: https://github.com/yosef-chai/news-card/tree/main/custom_components/news_card/translations
[my-hacs]: https://my.home-assistant.io/redirect/hacs_repository/?owner=yosef-chai&repository=news-card&category=integration
[my-hacs-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[my-flow]: https://my.home-assistant.io/redirect/config_flow_start/?domain=news_card
[my-flow-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
[bp-badge]: https://my.home-assistant.io/badges/blueprint_import.svg
