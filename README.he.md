<div dir="rtl">

<p align="center"><img src="assets/logo.png" width="120" alt="הלוגו של News Card"></p>

# News Card

[English](README.md)

אינטגרציה וכרטיס חדשות ל-Home Assistant, שמותקנים יחד כחבילה אחת:
- האינטגרציה קוראת כל פיד RSS, ‏Atom, ‏RDF או JSON Feed.
- היא מנקה את הכתבות ומוצאת להן תמונות.
- היא יוצרת ישויות ואירועים לאוטומציות.
- הכרטיס מציג את החדשות כרשימה או כבר תחתון בגלילה אינסופית.

## התקנה

### דרך HACS (מומלץ)

1. ב-HACS ← ⋮ ← **Custom repositories** מוסיפים את `https://github.com/yosef-chai/news-card` בקטגוריה **Integration**.
2. מחפשים **News Card** ומורידים.
3. מפעילים מחדש את Home Assistant.
4. **הגדרות ← מכשירים ושירותים ← הוספת שילוב ← News Card** ומזינים כתובת של פיד או של אתר.

הכרטיס נרשם אוטומטית, בלי צורך להוסיף משאב ללוח.

### התקנה ידנית

מעתיקים את `custom_components/news_card` אל `config/custom_components/` ומפעילים מחדש.

## הגדרות הפיד

| אפשרות | ברירת מחדל | הסבר |
|---|---|---|
| כתובת הפיד או האתר | — | אם מזינים כתובת של אתר, נמצאים הפידים שלו |
| אימות תעודת SSL | פעיל | כדאי לכבות רק לאתר מוכר עם תעודה שבורה |
| תדירות עדכון | ‏15 דק' | ‏5–1440 |
| מספר כתבות לשמירה | ‏30 | ‏1–100 |
| מילות מפתח | — | כתבה חדשה שמתאימה להן מפעילה `keyword_match` |
| טעינת תמונות דרך Home Assistant | פעיל | פותר חסימות ותמונות http |
| חיפוש תמונה חסרה בדף הכתבה | פעיל | נבדק פעם אחת לכל כתבה |

## הכרטיס

```yaml
type: custom:news-card
entities:
  - sensor.jdn_latest_article
display: ticker        # list = רשימה | ticker = בר תחתון
show_image: true
show_date: false
show_time: true
sort: desc             # desc = החדשות קודם | asc | random
max_items: 15
tap_action: dialog     # link | dialog | none
date_format: relative  # absolute | relative
```

בעורך החזותי בוחרים **מקורות חדשות** לפי השם, וכל הכתבות שלהם מוצגות לפי הגדרות הכרטיס. מהירות הגלילה (5–100 פיקסלים לשנייה) מופיעה בבר התחתון, וגם ברשימה כשמפעילים **גלילה אוטומטית**: כשלכרטיס יש גובה קבוע והכתבות לא נכנסות, הרשימה גוללת לבד. הגלילה נעצרת כשמעבירים עליה את העכבר או קוראים כתבה, וממשיכה כשחוזרים.

## התראות לטלפון ולרמקולים, בלי אוטומציות

**הגדרות ← מכשירים ושירותים ← News Card ← הפיד ← הוספת התראה.**

1. בוחרים **מתי**: על כל כתבה חדשה, או כל יום בשעה קבועה (ובוחרים ימים).
2. בוחרים **לאן**: טלפונים עם אפליקציית Home Assistant כבר מסומנים; מוסיפים רמקולים כדי לשמוע.
3. רשות: מילות מפתח, תקציר הכתבה (מתאים לתחזית מזג אוויר), והשעות שבהן מותר לרמקולים לדבר.

הרמקולים מכריזים בשפה של Home Assistant וממשיכים אחר כך את מה שהתנגן. מחוץ לשעות ההשמעה נשלחת רק התראה לטלפון. לכל פיד אפשר להוסיף כמה התראות, ולערוך או למחוק אותן מאותו דף.

## אוטומציות

**הדרך הפשוטה:** בעורך האוטומציות בוחרים בטריגר **News Card ← כתבה חדשה**, בוחרים פידים (ישויות, מכשירים או אזורים), ואפשר להקליד מילות מפתח. הכתבה נמצאת ב-`trigger.to_state.attributes`:

```yaml
triggers:
  - trigger: news_card.new_article
    target:
      entity_id: event.jdn_new_article
    options:
      keywords: [גשם, סערה]   # רשות: הכותרת או התקציר צריכים להכיל אחת מהן
actions:
  - action: notify.mobile_app_phone
    data:
      message: "{{ trigger.to_state.attributes.title }}"
```

**כתבה חדשה מפיד אחד:** משתמשים בטריגר מצב על ישות האירוע, והנתונים נמצאים ב-`trigger.to_state.attributes`:

```yaml
triggers:
  - trigger: state
    entity_id: event.jdn_new_article
    not_from: unavailable
actions:
  - action: notify.mobile_app_phone
    data:
      message: "{{ trigger.to_state.attributes.title }}"
```

### Blueprints

אוטומציות מוכנות. לוחצים על הכפתור כדי לייבא, וממלאים את הטופס.

| Blueprint | |
|---|---|
| **התראה על כתבות חדשות** — התראה לטלפון עם תמונה וקישור על כל כתבה חדשה (אפשר רק עם מילות מפתח). | [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fnotify_new_article.yaml) |
| **הקראת כותרות חדשות** — מקריא כל כותרת חדשה ברמקולים, רק בשעות שבוחרים. | [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fspeak_new_article.yaml) |
| **סיכום חדשות יומי** — בשעה קבועה שולח את הכותרות האחרונות לטלפון ו/או מקריא אותן, ואפשר לסמן אותן כנקראו. | [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyosef-chai%2Fnews-card%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnews_card%2Fnews_briefing.yaml) |

### טריגרים, תנאים ופעולות

| סוג | שם | מה עושה |
|---|---|---|
| טריגר | **כתבה חדשה** (`news_card.new_article`) | מופעל על כל כתבה חדשה, ואפשר להקליד מילות מפתח. הנתונים ב-`trigger.to_state.attributes`. |
| טריגר | **אין כתבות חדשות** (`news_card.no_new_articles`) | מופעל פעם אחת כשפיד לא פרסם כלום זמן מה (ברירת מחדל 12 שעות), למשל כשהאתר לא זמין. הנתונים: `trigger.feed`, ‏`trigger.last_article`. |
| תנאי | **כתבה מהזמן האחרון** (`news_card.recent_article`) | נכון אם פיד פרסם כתבה בטווח הזמן שנבחר, ואפשר להגביל למילות מפתח. |
| פעולה | **שליחה לטלפון** (`news_card.send_to_phone`) | שולחת את הכתבה האחרונה (או רשימה קצרה) לטלפונים עם אפליקציית Home Assistant, עם תמונה וקישור. |
| פעולה | **הכרזה ברמקולים** (`news_card.announce`) | מקריאה את הכתבה האחרונה בשפה של Home Assistant; מוזיקה שמתנגנת נעצרת וממשיכה. |
| פעולה | `news_card.mark_read` | מסמנת כתבות כנקראו (כולן, או לפי `article_id`). הכרטיס מעמעם אותן בכל המכשירים. |
| פעולה | `news_card.get_entries` | מחזירה את הכתבות השמורות. אפשר לסנן לפי `limit`, ‏`keyword` ו-`since`. |
| פעולה | `news_card.refresh` | מוריד את הפיד עכשיו. |

לכל פיד יש גם חיישן **כתבות שלא נקראו**.

**כל הפידים יחד:** משתמשים בטריגר אירוע `news_card_new_article`, והנתונים נמצאים ב-`trigger.event.data`.


## מגבלות ידועות

- **לוחות במצב YAML:** אם הכרטיס לא מופיע, צריך להוסיף את המשאב `/news_card/frontend/news-card.js` מסוג module.
- **תצוגת Panel:** תקלה פתוחה בממשק עלולה להציג "שגיאת תצורה" עד רענון הדף.
- **אייקון בחנות של HACS:** עלול להופיע ריק. בדף השילובים ובמכשירים האייקון מוצג כרגיל.
- **Google News:** הקישורים הם דפי הפניה, ולכן אין ממה לחלץ תמונות.
- **ישויות Feedreader:** מספקות רק את הכתבה האחרונה.

## פתרון תקלות

- **לוג דיבאג:** מוסיפים את `custom_components.news_card: debug` תחת `logger`.
- **קובץ אבחון:** ⋮ ← הורדת אבחון.
- **תקלת "הפיד לא זמין" במרכז התיקונים:** לוחצים **תיקון** ומזינים כתובת חדשה.

## הסרה

1. מוחקים כל פיד: הגדרות ← מכשירים ושירותים ← News Card ← ⋮ ← מחיקה.
2. מסירים את החבילה ב-HACS ומפעילים מחדש.
3. מסירים את הכרטיסים מהלוחות.

</div>
