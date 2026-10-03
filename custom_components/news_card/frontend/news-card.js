/**
 * News Card — כרטיס חדשות ל-Home Assistant.
 * מקבל נתונים מהאינטגרציה news_card דרך מנוי WebSocket (דחיפה, בלי polling),
 * ותומך גם בישויות event של Feedreader (הכתבה האחרונה בלבד).
 */

const CARD_VERSION = "1.7.0";
const DOMAIN = "news_card";
const READ_KEY = "news-card:read";
const READ_LIMIT = 500;

const STRINGS = {
  en: {
    loading: "Loading news…",
    empty: "No articles yet.",
    no_entities: "Choose at least one news source.",
    not_installed: "News Card isn't installed, or hasn't loaded yet.",
    connection_error: "Couldn't load the news.",
    retry: "Retry",
    entity_not_found: "{entity} was not found.",
    entry_not_loaded: "The feed of {entity} is not loaded.",
    unavailable: "{entity} is unavailable.",
    stale: "Outdated",
    stale_tip: "The feed isn't updating. Last successful update: {time}",
    why_blocked: "The site blocks feed readers.",
    why_refused: "The site refused. A different User-Agent in the feed options may help.",
    why_not_found: "The feed isn't at its address anymore.",
    why_rate_limited: "The site asked to slow down; we'll try again later.",
    why_server_error: "The site is having trouble.",
    why_auth_required: "The feed needs a login.",
    open_article: "Open article",
    close: "Close",
    no_feeds_hint: "Add a feed in Settings → Devices & services → News Card.",
    estimated: "Approximate time",
    // עורך
    feeds: "News sources",
    advanced: "Advanced",
    entities: "Entities (advanced)",
    helper_feeds: "All articles from the chosen sources show up according to the settings below.",
    helper_scroll_speed: "Pixels per second. Scrolling pauses when the mouse is on it, when you use the keyboard, or while you read an article.",
    auto_scroll: "Scroll automatically",
    helper_auto_scroll: "If the card has a fixed height and the articles don't fit, the list scrolls by itself.",
    title: "Title",
    display: "Display",
    display_list: "List",
    display_ticker: "Ticker at the bottom",
    content: "Content",
    show_image: "Image",
    show_date: "Date",
    show_time: "Time",
    show_source: "Source",
    show_author: "Author",
    order: "Order and amount",
    sort: "Sort",
    sort_desc: "Newest first",
    sort_asc: "Oldest first",
    sort_random: "Random",
    max_items: "Number of articles",
    date_format: "Time format",
    date_absolute: "Date and time",
    date_relative: "Relative (5 minutes ago)",
    interaction: "Interaction",
    tap_action: "On tap",
    tap_link: "Open the article",
    tap_dialog: "Show summary",
    tap_none: "Nothing",
    mark_read: "Dim articles you've opened",
    helper_mark_read: "Saved in Home Assistant, so it works on every device and counts toward the Unread articles sensor.",
    scroll_speed: "Scroll speed",
    helper_entities: "News Card feeds, or Feedreader event entities (latest article only).",
    err_entities: "'entities' must be a list of entity IDs.",
    err_value: "Invalid value for '{key}'.",
  },
  he: {
    loading: "טוען חדשות…",
    empty: "עדיין אין כתבות.",
    no_entities: "צריך לבחור לפחות מקור חדשות אחד.",
    not_installed: "האינטגרציה News Card לא מותקנת, או שעוד לא נטענה.",
    connection_error: "לא הצלחנו לטעון את החדשות.",
    retry: "לנסות שוב",
    entity_not_found: "{entity} לא נמצאה.",
    entry_not_loaded: "הפיד של {entity} לא נטען.",
    unavailable: "{entity} לא זמינה.",
    stale: "לא עדכני",
    stale_tip: "הפיד לא מתעדכן. עדכון אחרון שהצליח: {time}",
    why_blocked: "האתר חוסם קוראי פידים.",
    why_refused: "האתר סירב. User-Agent אחר בהגדרות הפיד יכול לעזור.",
    why_not_found: "הפיד כבר לא בכתובת שלו.",
    why_rate_limited: "האתר ביקש להאט, ננסה שוב בהמשך.",
    why_server_error: "יש תקלה באתר.",
    why_auth_required: "הפיד דורש כניסה.",
    open_article: "לכתבה המלאה",
    close: "סגירה",
    no_feeds_hint: "אפשר להוסיף פיד בהגדרות ← מכשירים ושירותים ← News Card.",
    estimated: "זמן משוער",
    feeds: "מקורות חדשות",
    advanced: "מתקדם",
    entities: "ישויות (מתקדם)",
    helper_feeds: "כל הכתבות מהמקורות שנבחרו יוצגו לפי ההגדרות שלמטה.",
    helper_scroll_speed: "פיקסלים לשנייה. הגלילה עוצרת כשהעכבר עליה, כשמשתמשים במקלדת או כשקוראים כתבה.",
    auto_scroll: "גלילה אוטומטית",
    helper_auto_scroll: "אם לכרטיס יש גובה קבוע והכתבות לא נכנסות, הרשימה תגלול לבד.",
    title: "כותרת",
    display: "תצוגה",
    display_list: "רשימה",
    display_ticker: "פס רץ בתחתית",
    content: "תוכן",
    show_image: "תמונה",
    show_date: "תאריך",
    show_time: "שעה",
    show_source: "מקור",
    show_author: "כותב",
    order: "סדר וכמות",
    sort: "מיון",
    sort_desc: "החדשות קודם",
    sort_asc: "הישנות קודם",
    sort_random: "אקראי",
    max_items: "מספר כתבות",
    date_format: "תצוגת זמן",
    date_absolute: "תאריך ושעה",
    date_relative: "יחסי (לפני 5 דקות)",
    interaction: "פעולה",
    tap_action: "בלחיצה",
    tap_link: "פתיחת הכתבה",
    tap_dialog: "הצגת תקציר",
    tap_none: "שום דבר",
    mark_read: "עמעום כתבות שכבר פתחת",
    helper_mark_read: "נשמר ב-Home Assistant, אז זה עובד בכל המכשירים ונספר בחיישן הכתבות שלא נקראו.",
    scroll_speed: "מהירות גלילה",
    helper_entities: "פידים של News Card, או ישויות event של Feedreader (הכתבה האחרונה בלבד).",
    err_entities: "'entities' צריך להיות רשימה של מזהי ישויות.",
    err_value: "ערך לא תקין עבור '{key}'.",
  },
};

const DEFAULTS = {
  display: "list",
  show_image: true,
  show_date: true,
  show_time: true,
  show_source: true,
  show_author: false,
  sort: "desc",
  max_items: 30,
  date_format: "absolute",
  tap_action: "link",
  mark_read: false,
  auto_scroll: false,
  scroll_speed: 30,
};

const ENUMS = {
  display: ["list", "ticker"],
  sort: ["desc", "asc", "random"],
  date_format: ["absolute", "relative"],
  tap_action: ["link", "dialog", "none"],
};

/** שפת הממשק: מה-hass אם יש, אחרת מהדפדפן. */
function pageLanguage(hass) {
  const lang = hass?.locale?.language || document.querySelector("home-assistant")?.hass?.locale?.language || navigator.language || "en";
  return lang.toLowerCase().startsWith("he") ? "he" : "en";
}

function t(lang, key, vars = {}) {
  const text = STRINGS[lang]?.[key] ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
}

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

/** קישור בטוח בלבד: http/https. */
function safeUrl(url) {
  if (!url || typeof url !== "string") return null;
  try {
    const parsed = new URL(url, location.href);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/** hash קטן ליציבות הסדר האקראי בין רינדורים. */
function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return h >>> 0;
}

function normalizeConfig(config) {
  if (!config || typeof config !== "object") throw new Error("Invalid configuration");
  let entities = config.entities ?? (config.entity ? [config.entity] : []);
  if (typeof entities === "string") entities = [entities];
  if (!Array.isArray(entities)) throw new Error(t(pageLanguage(), "err_entities"));
  entities = entities.map((e) => (typeof e === "object" && e ? e.entity : e)).filter((e) => typeof e === "string" && e.includes("."));
  if (config[""] && typeof config[""] === "object") config = { ...config, ...config[""] };
  let feeds = config.feeds ?? [];
  if (typeof feeds === "string") feeds = [feeds];
  if (!Array.isArray(feeds)) throw new Error(t(pageLanguage(), "err_entities"));
  const out = { ...DEFAULTS, ...config, entities, feeds: feeds.filter((f) => typeof f === "string" && f) };
  delete out.entity;
  delete out[""];
  for (const [key, values] of Object.entries(ENUMS)) {
    if (!values.includes(out[key])) throw new Error(t(pageLanguage(), "err_value", { key }));
  }
  out.max_items = Math.max(1, Math.min(100, Number(out.max_items) || DEFAULTS.max_items));
  // ticker_speed הוא השם הישן של scroll_speed
  out.scroll_speed = Math.max(5, Math.min(100, Number(config.scroll_speed ?? config.ticker_speed) || DEFAULTS.scroll_speed));
  delete out.ticker_speed;
  out.auto_scroll = !!out.auto_scroll;
  return out;
}

function readSet() {
  try {
    return new Set(JSON.parse(localStorage.getItem(READ_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveRead(set) {
  try {
    localStorage.setItem(READ_KEY, JSON.stringify([...set].slice(-READ_LIMIT)));
  } catch {
    /* אחסון חסום (מצב פרטי) — הסימון יישאר רק לזמן הצפייה */
  }
}

const STYLE = `
  :host { display: block; height: 100%; }
  ha-card {
    height: 100%; display: flex; flex-direction: column; overflow: hidden;
    box-sizing: border-box;
  }
  .header {
    display: flex; align-items: center; gap: var(--ha-space-2, 8px);
    padding: var(--ha-space-3, 12px) var(--ha-space-4, 16px) var(--ha-space-2, 8px);
  }
  .header h1 {
    flex: 1; margin: 0; min-width: 0;
    font-family: var(--ha-card-header-font-family, var(--ha-font-family-heading, inherit));
    font-size: var(--ha-card-header-font-size, var(--ha-font-size-xl, 20px));
    font-weight: var(--ha-font-weight-normal, 400);
    line-height: var(--ha-line-height-condensed, 1.2);
    color: var(--ha-card-header-color, var(--primary-text-color));
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .chip {
    font-size: var(--ha-font-size-xs, 10px); font-weight: var(--ha-font-weight-medium, 500);
    padding: 2px var(--ha-space-2, 8px); border-radius: var(--ha-border-radius-pill, 999px);
    color: var(--warning-color, #ffa600);
    background: color-mix(in srgb, var(--warning-color, #ffa600) 15%, transparent);
    white-space: nowrap;
  }
  .list { flex: 1; min-height: 0; overflow-y: auto; padding: 0 0 var(--ha-space-2, 8px); }
  .item {
    display: flex; align-items: flex-start; gap: var(--ha-space-3, 12px);
    padding: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
    color: inherit; text-decoration: none; text-align: start;
    width: 100%; box-sizing: border-box; border: none; background: none; font: inherit;
    border-radius: 0; outline: none; position: relative;
  }
  .item + .item::before {
    content: ""; position: absolute; top: 0; inset-inline: var(--ha-space-4, 16px);
    border-top: 1px solid var(--divider-color);
  }
  .tappable { cursor: pointer; }
  .tappable:hover { background: color-mix(in srgb, var(--primary-text-color) 4%, transparent); }
  .tappable:focus-visible { box-shadow: inset 0 0 0 2px var(--primary-color); }
  .thumb {
    flex: none; width: 72px; height: 54px; object-fit: cover;
    border-radius: var(--ha-border-radius-md, 8px);
    background: color-mix(in srgb, var(--primary-text-color) 6%, transparent);
  }
  .body { flex: 1; min-width: 0; }
  .title {
    font-size: var(--ha-font-size-m, 14px); font-weight: var(--ha-font-weight-medium, 500);
    line-height: var(--ha-line-height-normal, 1.4); color: var(--primary-text-color);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    overflow-wrap: anywhere;
  }
  .meta {
    margin-top: 2px; font-size: var(--ha-font-size-s, 12px);
    color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .read .title { color: var(--secondary-text-color); font-weight: var(--ha-font-weight-normal, 400); }
  .read .thumb { opacity: 0.6; }
  .state {
    flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: var(--ha-space-2, 8px); padding: var(--ha-space-4, 16px); text-align: center;
    color: var(--secondary-text-color); font-size: var(--ha-font-size-m, 14px);
  }
  .alert {
    margin: var(--ha-space-2, 8px) var(--ha-space-4, 16px); padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
    border-radius: var(--ha-border-radius-md, 8px); font-size: var(--ha-font-size-s, 12px);
    color: var(--primary-text-color);
    background: color-mix(in srgb, var(--alert-color, var(--error-color, #db4437)) 12%, transparent);
    border-inline-start: 4px solid var(--alert-color, var(--error-color, #db4437));
  }
  .alert.warning { --alert-color: var(--warning-color, #ffa600); }
  button.text {
    font: inherit; font-weight: var(--ha-font-weight-medium, 500); color: var(--primary-color);
    background: none; border: none; cursor: pointer; padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
    border-radius: var(--ha-border-radius-pill, 999px);
  }
  button.text:hover { background: color-mix(in srgb, var(--primary-color) 10%, transparent); }
  .skeleton { height: 54px; margin: var(--ha-space-2, 8px) var(--ha-space-4, 16px); border-radius: var(--ha-border-radius-md, 8px);
    background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--primary-text-color) 6%, transparent), transparent) 0 0 / 200% 100%;
    animation: shimmer 1.4s infinite linear; }
  @keyframes shimmer { to { background-position: -200% 0; } }

  /* בר תחתון */
  .ticker { flex: 1; display: flex; align-items: center; gap: var(--ha-space-2, 8px); min-height: 48px;
    padding-inline: var(--ha-space-3, 12px); }
  .ticker .label { flex: none; font-weight: var(--ha-font-weight-bold, 700); font-size: var(--ha-font-size-m, 14px);
    color: var(--primary-color); max-width: 30%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .viewport { flex: 1; min-width: 0; overflow: hidden;
    mask-image: linear-gradient(90deg, transparent, #000 24px, #000 calc(100% - 24px), transparent); }
  .track { display: flex; width: max-content; animation: scroll var(--duration, 60s) linear infinite; will-change: transform; }
  .group { display: flex; flex: none; }
  /* עוצרים כשמצביעים, כשמנווטים במקלדת, כשקוראים כתבה וכשהכרטיס מחוץ למסך */
  .viewport:hover .track, .viewport:has(:focus-visible) .track, .reading .track, .offscreen .track,
  .list.auto:hover .vtrack, .list.auto:has(:focus-visible) .vtrack, .reading .vtrack, .offscreen .vtrack { animation-play-state: paused; }
  @keyframes scroll { to { transform: translateX(calc(-50% * var(--dir, 1))); } }
  .tick { display: inline-flex; align-items: center; gap: var(--ha-space-2, 8px); white-space: nowrap;
    padding: var(--ha-space-1, 4px) var(--ha-space-3, 12px); color: var(--primary-text-color); text-decoration: none;
    font-size: var(--ha-font-size-m, 14px); border: none; background: none; font-family: inherit; border-radius: var(--ha-border-radius-sm, 4px); }
  .tick:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
  .tick .tthumb { width: 28px; height: 28px; border-radius: var(--ha-border-radius-sm, 4px); object-fit: cover; }
  .tick .ttime { color: var(--secondary-text-color); font-size: var(--ha-font-size-s, 12px); }
  .tick.read .ttitle { color: var(--secondary-text-color); }
  .sep { color: var(--divider-color); align-self: center; }
  /* רשימה בגלילה אוטומטית */
  .list.auto { overflow: hidden; padding-bottom: 0;
    mask-image: linear-gradient(transparent, #000 16px, #000 calc(100% - 16px), transparent); }
  .vtrack { animation: vscroll var(--duration, 60s) linear infinite; will-change: transform; }
  @keyframes vscroll { to { transform: translateY(-50%); } }
  .vgroup + .vgroup > :first-child::before { content: ""; position: absolute; top: 0; inset-inline: var(--ha-space-4, 16px);
    border-top: 1px solid var(--divider-color); }
  @media (prefers-reduced-motion: reduce) {
    .track { animation: none; }
    .viewport { overflow-x: auto; mask-image: none; }
    .group[aria-hidden], .vgroup[aria-hidden] { display: none; }
    .vtrack { animation: none; }
    .list.auto { overflow-y: auto; mask-image: none; }
  }

  /* חלון תקציר */
  dialog {
    width: min(560px, calc(100vw - 32px)); max-height: calc(100vh - 64px); padding: 0; border: none;
    border-radius: var(--ha-dialog-border-radius, var(--ha-border-radius-3xl, 28px));
    background: var(--ha-dialog-surface-background, var(--card-background-color, #fff));
    color: var(--primary-text-color); box-shadow: var(--ha-box-shadow-l, 0 8px 32px rgba(0,0,0,.3)); overflow: hidden auto;
  }
  dialog::backdrop { background: var(--ha-dialog-scrim-color, rgba(0, 0, 0, 0.32)); }
  .dimg { display: block; width: 100%; max-height: 280px; object-fit: cover; }
  .dbody { padding: var(--ha-space-6, 24px); }
  .dtitle { margin: 0 0 var(--ha-space-2, 8px); font-size: var(--ha-font-size-xl, 20px); font-weight: var(--ha-font-weight-normal, 400);
    line-height: var(--ha-line-height-condensed, 1.3); }
  .dmeta { font-size: var(--ha-font-size-s, 12px); color: var(--secondary-text-color); margin-bottom: var(--ha-space-4, 16px); }
  .dsummary { white-space: pre-line; line-height: var(--ha-line-height-normal, 1.6); font-size: var(--ha-font-size-m, 14px); }
  .dactions { display: flex; justify-content: flex-end; gap: var(--ha-space-2, 8px); padding: 0 var(--ha-space-4, 16px) var(--ha-space-4, 16px); }
  .dactions a { text-decoration: none; }
  .hidden { display: none !important; }
  .retrying { visibility: hidden; }
`;

class NewsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._feeds = {};
    this._status = "loading";
    this._signature = "";
    this._read = readSet();
    this._visible = true;
    this._seed = Math.random();
    this.shadowRoot.addEventListener("error", (ev) => this._onImageError(ev), true);
    this.shadowRoot.addEventListener("load", (ev) => ev.target.classList?.remove("retrying"), true);
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    // עדכון שהגיע בזמן שהחלון פתוח מוחל אחרי הסגירה
    this.shadowRoot.addEventListener("close", () => {
      this._setReading(false);
      // הפוקוס חוזר לפריט; מורידים אותו כדי שהגלילה לא תישאר עצורה בגללו
      if (this.shadowRoot.activeElement?.closest?.(".track, .vtrack")) this.shadowRoot.activeElement.blur();
      if (this._dirty) this._render();
    }, true);
    this.shadowRoot.addEventListener("keydown", (ev) => {
      if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches?.("[data-open]")) {
        ev.preventDefault();
        this._onClick(ev);
      }
    });
  }

  // ---------- API של לוח המחוונים ----------

  static getConfigElement() {
    return document.createElement("news-card-editor");
  }

  static getStubConfig(hass) {
    const first = Object.values(hass?.entities || {}).find((e) => e.platform === DOMAIN && e.device_id);
    return { feeds: first ? [first.device_id] : [], display: "list", max_items: 5 };
  }

  setConfig(config) {
    const next = normalizeConfig(config);
    const key = (c) => `${c.feeds.join()}|${c.entities.join()}`;
    const resubscribe = !this._config || key(next) !== key(this._config);
    this._reps = 1;
    this._loopSize = 0;
    this._vloop = false;
    this._config = next;
    if (resubscribe) {
      this._feeds = {};
      this._status = "loading";
      this._subscribe();
    }
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._subscribe();
    // רינדור רק כשמשהו רלוונטי השתנה: שפה, זמינות ישויות, או מצב ישות Feedreader
    const sig = [hass.locale?.language, hass.locale?.time_format, hass.locale?.time_zone, hass.entities === this._lastEntities ? "" : String(Math.random()), ...this._ids().map((id) => {
      const st = hass.states[id];
      if (!st) return "missing";
      return this._isFeedreader(id) ? `${st.state}|${st.last_updated}` : st.state === "unavailable" ? "u" : "ok";
    })].join(";");
    if (sig !== this._signature) {
      this._signature = sig;
      if (this._lastEntities !== hass.entities) {
        this._lastEntities = hass.entities;
        this._subscribe(); // רישום הישויות השתנה: אולי נוסף מקור
      }
      this._render();
    }
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    if (this._config?.display === "ticker") return 1;
    return 1 + Math.min(this._items().length || 3, this._config?.max_items || 5) * 1.5;
  }

  getGridOptions() {
    if (this._config?.display === "ticker") return { columns: 12, rows: 1, min_columns: 6, min_rows: 1, max_rows: 1 };
    return { columns: 12, rows: 4, min_columns: 3, min_rows: 2 };
  }

  connectedCallback() {
    this._subscribe();
    this._io = new IntersectionObserver(([entry]) => {
      this._visible = entry.isIntersecting;
      this.shadowRoot.querySelector("ha-card")?.classList.toggle("offscreen", !this._visible);
    });
    this._io.observe(this);
    this._ro = new ResizeObserver(() => this._scheduleLayout());
    this._ro.observe(this);
    this._timer = setInterval(() => {
      // בבר הגלילה לא מרנדרים כל דקה כדי לא לאפס את מיקום הגלילה
      if (this._visible && this._config?.date_format === "relative" && this._config.display === "list" && !this._vloop) this._render();
    }, 60000);
  }

  disconnectedCallback() {
    this._unsubscribe();
    this._io?.disconnect();
    this._ro?.disconnect();
    clearInterval(this._timer);
    cancelAnimationFrame(this._raf);
  }

  // ---------- נתונים ----------

  /** הישויות של כל המקורות: מכשירים שנבחרו בעורך + ישויות שהוגדרו ב-YAML. */
  _ids() {
    if (!this._config) return [];
    const ids = [...this._config.entities];
    const all = Object.values(this._hass?.entities || {});
    for (const device of this._config.feeds) {
      const mine = all.filter((e) => e.device_id === device);
      const pick =
        mine.find((e) => e.platform === DOMAIN && e.entity_id.startsWith("sensor.") && !e.entity_category) ||
        mine.find((e) => e.platform === DOMAIN) ||
        mine.find((e) => e.platform === "feedreader" && e.entity_id.startsWith("event."));
      if (pick && !ids.includes(pick.entity_id)) ids.push(pick.entity_id);
    }
    return ids;
  }

  _isFeedreader(id) {
    return this._hass?.entities?.[id]?.platform === "feedreader";
  }

  /** האם שפת הממשק נכתבת מימין לשמאל (לפי HA, ואם אין מידע — לפי כיוון הדף). */
  _isRtl() {
    const lang = this._hass?.locale?.language;
    const meta = lang && this._hass?.translationMetadata?.translations?.[lang];
    if (meta && "isRTL" in meta) return !!meta.isRTL;
    return getComputedStyle(this).direction === "rtl" || document.dir === "rtl";
  }

  _lang() {
    return pageLanguage(this._hass);
  }

  async _subscribe() {
    if (!this._hass || !this._config || !this.isConnected) return;
    const ids = this._ids().filter((id) => !this._isFeedreader(id));
    const key = ids.join();
    if (this._subKey === key && this._unsub) return;
    this._unsubscribe();
    this._subKey = key;
    if (!ids.length) {
      this._status = "ready";
      this._render();
      return;
    }
    const token = (this._token = Symbol("sub"));
    try {
      const unsub = await this._hass.connection.subscribeMessage((msg) => {
        if (token !== this._token) return; // תשובה למנוי ישן אחרי שינוי הגדרות
        this._feeds = { ...this._feeds, ...msg.feeds };
        // ערבוב מחדש רק כשהכתבות עצמן השתנו, לא כשרק סומנה כתבה כנקראה
        const ids = Object.values(this._feeds).map((f) => f.entries?.map((e) => e.id).join()).join("|");
        if (ids !== this._entryIds) {
          this._entryIds = ids;
          this._seed = Math.random();
        }
        this._status = "ready";
        this._render();
      }, { type: `${DOMAIN}/subscribe`, entity_ids: ids });
      if (token !== this._token) unsub();
      else this._unsub = unsub;
    } catch (err) {
      if (token !== this._token) return;
      this._subKey = undefined;
      this._status = err?.code === "unknown_command" ? "not_installed" : "connection_error";
      console.warn("news-card: subscribe failed", err);
      this._render();
    }
  }

  _unsubscribe() {
    this._token = undefined;
    if (this._unsub) {
      this._unsub().catch?.(() => {});
      this._unsub = undefined;
    }
    this._subKey = undefined;
  }

  /** רשימה אחידה מכל הפידים: איחוד, הסרת כפילויות, מיון, חיתוך. */
  _items() {
    if (!this._config) return [];
    const all = [];
    for (const id of this._ids()) {
      if (this._isFeedreader(id)) {
        const st = this._hass?.states[id];
        const a = st?.attributes;
        if (a?.title) {
          all.push({
            id: a.link || a.title, title: a.title, link: a.link, summary: a.description || "", published: st.state && st.state !== "unknown" ? st.state : null,
            published_estimated: false, source: this._hass.devices?.[this._hass.entities[id]?.device_id]?.name || null, author: null, image: null, image_proxy: null,
          });
        }
        continue;
      }
      const feed = this._feeds[id];
      if (feed?.entries) all.push(...feed.entries.map((e) => ({ ...e, source: e.source || feed.title, entity: id })));
    }
    const seen = new Set();
    const unique = all.filter((e) => {
      const k = e.link || e.id;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    const time = (e) => (e.published ? Date.parse(e.published) || 0 : 0);
    if (this._config.sort === "random") {
      const seed = String(this._seed);
      unique.sort((a, b) => hash(a.id + seed) - hash(b.id + seed));
    } else {
      const dir = this._config.sort === "asc" ? 1 : -1;
      unique.sort((a, b) => (time(a) - time(b)) * dir);
    }
    return unique.slice(0, this._config.max_items);
  }

  // ---------- עיצוב זמן ----------

  _timeZone() {
    const h = this._hass;
    return h?.locale?.time_zone === "server" && h.config?.time_zone ? h.config.time_zone : undefined;
  }

  _hour12() {
    const f = this._hass?.locale?.time_format;
    return f === "12" ? true : f === "24" ? false : undefined;
  }

  _formatTime(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    const lang = this._hass?.locale?.language || this._lang();
    const c = this._config;
    if (c.date_format === "relative") {
      const diff = (date.getTime() - Date.now()) / 1000;
      const units = [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
      const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
      for (const [unit, sec] of units) {
        // ‏ICU בעברית מוסיף מספר בסוגריים ("לפני שעתיים (2)"); הוא מיותר
        if (Math.abs(diff) >= sec) return rtf.format(Math.round(diff / sec), unit).replace(/\s*\(\d+\)/, "");
      }
      return rtf.format(0, "minute");
    }
    if (!c.show_date && !c.show_time) return "";
    const opts = { timeZone: this._timeZone(), hour12: this._hour12() };
    if (c.show_date) Object.assign(opts, { day: "numeric", month: "short" });
    if (c.show_date && date.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
    if (c.show_time) Object.assign(opts, { hour: "numeric", minute: "2-digit" });
    try {
      return new Intl.DateTimeFormat(lang, opts).format(date);
    } catch {
      return date.toLocaleString();
    }
  }

  _meta(item) {
    const c = this._config;
    const parts = [];
    if (c.show_source && item.source) parts.push(esc(item.source));
    if (c.show_author && item.author) parts.push(esc(item.author));
    const showTime = c.date_format === "relative" ? c.show_date || c.show_time : true;
    const time = showTime ? this._formatTime(item.published) : "";
    if (time) parts.push(item.published_estimated ? `<span title="${esc(t(this._lang(), "estimated"))}">~${esc(time)}</span>` : esc(time));
    return parts.join(" · ");
  }

  // ---------- רינדור ----------

  _render() {
    if (!this._config) return;
    if (this.shadowRoot.querySelector("dialog")?.open) {
      this._dirty = true;
      return;
    }
    this._dirty = false;
    const lang = this._lang();
    const c = this._config;
    const items = this._items();
    const problems = this._problems(lang);
    const staleFeeds = this._ids().map((id) => this._feeds[id]).filter((f) => f?.stale);
    const staleChip = staleFeeds.length
      ? `<span class="chip" title="${esc(
          [t(lang, "stale_tip", { time: this._formatAbsolute(staleFeeds[0].last_success) }), STRINGS[lang][`why_${staleFeeds[0].error}`]]
            .filter(Boolean)
            .join(" "),
        )}">${esc(t(lang, "stale"))}</span>`
      : "";

    let body;
    if (!this._ids().length) {
      body = `<div class="state">${esc(t(lang, "no_entities"))}<span>${esc(t(lang, "no_feeds_hint"))}</span></div>`;
    } else if (this._status === "not_installed" || this._status === "connection_error") {
      body = `<div class="state">${esc(t(lang, this._status))}<button class="text" data-retry>${esc(t(lang, "retry"))}</button></div>`;
    } else if (this._status === "loading" && !items.length) {
      body = c.display === "ticker" ? `<div class="state">${esc(t(lang, "loading"))}</div>` : `<div class="list" aria-busy="true">${'<div class="skeleton"></div>'.repeat(3)}</div>`;
    } else if (!items.length) {
      body = problems.length ? "" : `<div class="state">${esc(t(lang, "empty"))}</div>`;
    } else {
      body = c.display === "ticker" ? this._tickerHtml(items, lang) : this._listHtml(items);
    }

    const header = c.display !== "ticker" && (c.title || staleChip)
      ? `<div class="header"><h1>${esc(c.title || "")}</h1>${staleChip}</div>`
      : "";
    const alerts = problems.map((p) => `<div class="alert ${p.level}" role="status">${esc(p.text)}</div>`).join("");
    const offscreen = this._visible ? "" : " offscreen";

    // הכיוון נקבע לפי שפת הממשק בלבד, גם לטקסט בשפה אחרת בתוך הכרטיס
    const dir = this._isRtl() ? "rtl" : "ltr";
    const html = `<ha-card dir="${dir}" class="mode-${c.display}${offscreen}">${header}${alerts}${body}</ha-card>`;
    if (html === this._html && this.shadowRoot.querySelector("ha-card")) return;
    this._html = html;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>${html}${this._dialogHtml(dir)}`;
    this._itemsById = new Map(items.map((i) => [i.id, i]));
    this.shadowRoot.querySelector("ha-card")?.classList.toggle("reading", !!this._reading);
    if (c.display === "ticker" || c.auto_scroll) this._scheduleLayout();
  }

  /** המדידה דורשת פריסה; כשהכרטיס עוד לא מוצג (עורך, טעינה) מנסים שוב בפריים הבא. */
  _scheduleLayout(attempt = 0) {
    cancelAnimationFrame(this._raf);
    this._raf = requestAnimationFrame(() => {
      if (!this._layout() && attempt < 120) this._scheduleLayout(attempt + 1);
    });
  }

  _problems(lang) {
    const out = [];
    for (const id of this._ids()) {
      const name = this._hass?.states[id]?.attributes?.friendly_name || id;
      const feed = this._feeds[id];
      if (feed?.error && !feed.entries) {
        out.push({ level: "error", text: t(lang, feed.error, { entity: name }) });
      } else if (this._hass && !this._hass.states[id]) {
        out.push({ level: "error", text: t(lang, "entity_not_found", { entity: id }) });
      } else if (this._isFeedreader(id) && this._hass?.states[id]?.state === "unavailable") {
        out.push({ level: "warning", text: t(lang, "unavailable", { entity: name }) });
      }
    }
    return out;
  }

  _formatAbsolute(iso) {
    if (!iso) return "—";
    try {
      return new Intl.DateTimeFormat(this._hass?.locale?.language || this._lang(), {
        dateStyle: "medium", timeStyle: "short", timeZone: this._timeZone(), hour12: this._hour12(),
      }).format(new Date(iso));
    } catch {
      return iso;
    }
  }

  _img(item, cls) {
    if (!this._config.show_image) return "";
    const proxy = safeUrl(item.image_proxy ? new URL(item.image_proxy, location.href).href : null);
    const original = safeUrl(item.image);
    const src = proxy || original;
    if (!src) return "";
    const fallback = proxy && original ? ` data-fallback="${esc(original)}"` : "";
    return `<img class="${cls}" src="${esc(src)}"${fallback} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">`;
  }

  /** עטיפת פריט לפי פעולת הלחיצה: קישור, כפתור לחלון, או טקסט. */
  _wrap(item, cls, inner) {
    const read = this._config.mark_read && (item.read || this._read.has(item.id)) ? " read" : "";
    const link = safeUrl(item.link);
    const action = this._config.tap_action;
    if (action === "link" && link) {
      return `<a class="${cls} tappable${read}" href="${esc(link)}" target="_blank" rel="noopener noreferrer" data-id="${esc(item.id)}" role="listitem">${inner}</a>`;
    }
    if (action === "dialog") {
      return `<div class="${cls} tappable${read}" role="button" tabindex="0" data-open="${esc(item.id)}" data-id="${esc(item.id)}">${inner}</div>`;
    }
    return `<div class="${cls}${read}" role="listitem">${inner}</div>`;
  }

  _listHtml(items) {
    const rows = items.map((item) => {
      const meta = this._meta(item);
      const inner = `${this._img(item, "thumb")}<div class="body"><div class="title">${esc(item.title)}</div>${meta ? `<div class="meta">${meta}</div>` : ""}</div>`;
      return this._wrap(item, "item", inner);
    });
    if (!this._config.auto_scroll) return `<div class="list" role="list">${rows.join("")}</div>`;
    if (!this._vloop) return `<div class="list auto" role="list">${rows.join("")}</div>`;
    // הכתבות לא נכנסות בגובה: שני עותקים בלולאה אנכית (העותק השני מוסתר מקורא מסך)
    const duration = this._loopSize ? ` style="--duration:${Math.max(2, this._loopSize / this._config.scroll_speed)}s"` : "";
    return `<div class="list auto" aria-live="off"><div class="vtrack"${duration}><div class="vgroup" role="list">${rows.join("")}</div><div class="vgroup" aria-hidden="true" inert>${rows.join("")}</div></div></div>`;
  }

  _tickerHtml(items, lang) {
    const reps = this._reps || 1;
    const one = items.map((item) => {
      const time = this._config.date_format === "relative" || this._config.show_date || this._config.show_time ? this._formatTime(item.published) : "";
      const inner = `${this._img(item, "tthumb")}<span class="ttitle">${esc(item.title)}</span>${time ? `<span class="ttime">${esc(time)}</span>` : ""}`;
      return this._wrap(item, "tick", inner);
    }).join('<span class="sep" aria-hidden="true">•</span>');
    const group = Array(reps).fill(one).join('<span class="sep" aria-hidden="true">•</span>') + '<span class="sep" aria-hidden="true">•</span>';
    const label = this._config.title ? `<span class="label">${esc(this._config.title)}</span>` : "";
    // aria-live כבוי: קורא מסך לא יוצף בכל גלילה; העותק השני מוסתר ממנו
    const rtl = this._isRtl();
    // RTL: התוכן זז ימינה (משמאל לימין); LTR: התוכן זז שמאלה
    const duration = this._loopSize ? `--duration:${Math.max(2, this._loopSize / this._config.scroll_speed)}s;` : "";
    return `<div class="ticker" dir="${rtl ? "rtl" : "ltr"}">${label}
      <div class="viewport" aria-live="off"><div class="track" style="--dir:${rtl ? -1 : 1};${duration}"><div class="group" role="list">${group}</div><div class="group" aria-hidden="true" inert>${group}</div></div></div>
    </div>`;
  }

  /** מדידה אחרי פריסה. מחזיר false אם עוד אין גודל (ואז מנסים שוב בפריים הבא). */
  _layout() {
    const c = this._config;
    if (!c) return true;
    if (c.display === "ticker") return this._layoutTicker();
    if (c.auto_scroll) return this._layoutList();
    return true;
  }

  /** בר: חזרות כדי שעותק אחד ימלא את הרוחב, ומשך לפי המהירות. */
  _layoutTicker() {
    const viewport = this.shadowRoot.querySelector(".viewport");
    const group = this.shadowRoot.querySelector(".group");
    const track = this.shadowRoot.querySelector(".track");
    if (!viewport || !group || !track) return false;
    const width = group.scrollWidth;
    if (!width || !viewport.clientWidth) return false;
    const reps = this._reps || 1;
    const needed = Math.max(1, Math.ceil((viewport.clientWidth * reps) / width));
    if (needed > reps && needed < 50) {
      this._reps = needed;
      this._render();
      return true;
    }
    this._setLoop(track, width);
    return true;
  }

  /** רשימה: גוללת רק כשהכתבות גבוהות מהכרטיס (גובה קבוע); אחרת נשארת רגילה. */
  _layoutList() {
    const list = this.shadowRoot.querySelector(".list.auto");
    if (!list) return true;
    if (!list.clientHeight) return false;
    if (!this._vloop) {
      if (list.scrollHeight > list.clientHeight + 1) {
        this._vloop = true;
        this._render();
      }
      return true;
    }
    const height = list.querySelector(".vgroup")?.offsetHeight || 0;
    if (!height) return false;
    if (height <= list.clientHeight) {
      this._vloop = false; // הכרטיס גדל וכל הכתבות נכנסות
      this._loopSize = 0;
      this._render();
      return true;
    }
    this._setLoop(list.querySelector(".vtrack"), height);
    return true;
  }

  /** משך = אורך עותק אחד ÷ מהירות, כך שהמהירות בפיקסלים לשנייה מדויקת. */
  _setLoop(track, size) {
    this._loopSize = size;
    track?.style.setProperty("--duration", `${Math.max(2, size / this._config.scroll_speed)}s`);
  }

  _dialogHtml(dir) {
    return `<dialog dir="${dir}" aria-labelledby="dtitle">
      <img class="dimg hidden" alt="" referrerpolicy="no-referrer">
      <div class="dbody"><h2 class="dtitle" id="dtitle"></h2><div class="dmeta"></div><div class="dsummary"></div></div>
      <div class="dactions"><button class="text" data-close></button><a class="hidden" target="_blank" rel="noopener noreferrer"><button class="text" tabindex="-1"></button></a></div>
    </dialog>`;
  }

  /** החלון מקבל רק טקסט נקי דרך textContent — לעולם לא HTML מהפיד. */
  _openDialog(item) {
    const d = this.shadowRoot.querySelector("dialog");
    if (!d) return;
    const lang = this._lang();
    const img = d.querySelector(".dimg");
    const src = this._config.show_image ? safeUrl(item.image_proxy ? new URL(item.image_proxy, location.href).href : null) || safeUrl(item.image) : null;
    img.classList.toggle("hidden", !src);
    if (src) {
      img.src = src;
      if (item.image_proxy && item.image) img.dataset.fallback = item.image;
    }
    d.querySelector(".dtitle").textContent = item.title;
    const meta = [item.source, item.author, this._formatAbsolute(item.published)].filter(Boolean).join(" · ");
    d.querySelector(".dmeta").textContent = meta;
    d.querySelector(".dsummary").textContent = item.summary || "";
    d.querySelector("[data-close]").textContent = t(lang, "close");
    const a = d.querySelector("a");
    const link = safeUrl(item.link);
    a.classList.toggle("hidden", !link);
    if (link) {
      a.href = link;
      a.dataset.id = item.id;
      a.querySelector("button").textContent = t(lang, "open_article");
    }
    d.showModal();
  }

  // ---------- אירועים ----------

  _onClick(ev) {
    const path = ev.composedPath();
    const el = (sel) => path.find((n) => n.matches?.(sel));
    if (el("[data-retry]")) {
      this._status = "loading";
      this._render();
      this._subscribe();
      return;
    }
    const dialog = this.shadowRoot.querySelector("dialog");
    if (el("[data-close]") || (dialog?.open && path[0] === dialog)) {
      dialog?.close();
      return;
    }
    const opener = el("[data-open]");
    if (opener) {
      const item = this._itemsById?.get(opener.dataset.open);
      if (item) {
        this._markRead(item.id);
        this._openDialog(item);
        this._setReading(true); // ממשיך כשהחלון נסגר (אירוע close)
      }
      return;
    }
    const link = el("a[data-id]");
    if (link) this._readInNewTab();
    if (link) this._markRead(link.dataset.id);
  }

  /** כתבה שנפתחה: בפידים של News Card נשמר בשרת (משותף לכל המכשירים), ב-Feedreader בדפדפן. */
  _markRead(id) {
    if (!this._config?.mark_read || !id) return;
    const item = this._itemsById?.get(id);
    if (item?.entity && !item.read) {
      item.read = true;
      this._hass.callService(DOMAIN, "mark_read", { entity_id: item.entity, article_id: [id] }).catch((err) => console.warn("news-card: mark_read failed", err));
    } else if (!item?.entity) {
      this._read.add(id);
      saveRead(this._read);
    }
    // עדכון קל של המחלקה בלי רינדור מלא
    this.shadowRoot.querySelectorAll(`[data-id="${CSS.escape(id)}"]`).forEach((n) => n.classList.add("read"));
  }

  _setReading(on) {
    this._reading = on;
    this.shadowRoot.querySelector("ha-card")?.classList.toggle("reading", on);
  }

  /** כתבה שנפתחה בלשונית אחרת: הגלילה עומדת עד שחוזרים ללוח. */
  _readInNewTab() {
    this._setReading(true);
    const resume = () => {
      if (document.visibilityState !== "visible" || !document.hasFocus()) return;
      window.removeEventListener("focus", resume);
      document.removeEventListener("visibilitychange", resume);
      this._setReading(false);
      this.shadowRoot.activeElement?.blur();
    };
    window.addEventListener("focus", resume);
    document.addEventListener("visibilitychange", resume);
    // אם לא נפתחה לשונית (חסימת חלונות, אפליקציה), ממשיכים אחרי רגע
    setTimeout(() => {
      if (document.visibilityState === "visible" && document.hasFocus()) resume();
    }, 1500);
  }

  _onImageError(ev) {
    const img = ev.target;
    if (!(img instanceof HTMLImageElement)) return;
    const fallback = img.dataset.fallback;
    if (fallback && img.src !== fallback) {
      delete img.dataset.fallback;
      img.src = fallback; // פרוקסי נכשל → כתובת מקורית
      return;
    }
    const retries = Number(img.dataset.retries || 0);
    if (retries < 2) {
      // כשל זמני (למשל HA בהפעלה מחדש): ניסיון חוזר עם השהיה
      img.dataset.retries = String(retries + 1);
      img.classList.add("retrying");
      const src = img.src;
      setTimeout(() => {
        if (img.isConnected) {
          img.removeAttribute("src");
          img.src = src;
        }
      }, 2000 * (retries + 1));
      return;
    }
    img.classList.add("hidden");
  }
}


/** עורך חזותי: ha-form עם סכמה שמשתנה לפי הבחירות (למשל מהירות רק לבר התחתון). */
class NewsCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    else this._render();
  }

  _schema(config) {
    const lang = pageLanguage(this._hass);
    const opt = (key, values) => values.map((v) => ({ value: v, label: t(lang, `${key}_${v}`) }));
    const ticker = config.display === "ticker";
    const display = [{ name: "display", selector: { select: { mode: "box", options: opt("display", ENUMS.display) } } }];
    const speed = { name: "scroll_speed", selector: { number: { min: 5, max: 100, step: 1, mode: "slider", unit_of_measurement: "px/s" } } };
    if (ticker) display.push(speed);
    else {
      display.push({ name: "auto_scroll", selector: { boolean: {} } });
      if (config.auto_scroll) display.push(speed);
    }
    const advanced = [{ name: "entities", selector: { entity: { multiple: true, filter: [{ integration: DOMAIN }, { integration: "feedreader", domain: "event" }] } } }];
    return [
      { name: "feeds", selector: { device: { multiple: true, filter: [{ integration: DOMAIN }, { integration: "feedreader" }] } } },
      { name: "title", selector: { text: {} } },
      ...display,
      {
        type: "expandable", name: "content", flatten: true, icon: "mdi:text-box-outline",
        schema: [
          { type: "grid", name: "", flatten: true, schema: ["show_image", "show_date", "show_time", "show_source", "show_author"].map((name) => ({ name, selector: { boolean: {} } })) },
          { name: "date_format", selector: { select: { mode: "dropdown", options: opt("date", ENUMS.date_format) } } },
        ],
      },
      {
        type: "expandable", name: "order", flatten: true, icon: "mdi:sort",
        schema: [{ type: "grid", name: "", flatten: true, schema: [
          { name: "sort", selector: { select: { mode: "dropdown", options: opt("sort", ENUMS.sort) } } },
          { name: "max_items", selector: { number: { min: 1, max: 100, mode: "box" } } },
        ] }],
      },
      {
        type: "expandable", name: "interaction", flatten: true, icon: "mdi:gesture-tap",
        schema: [
          { name: "tap_action", selector: { select: { mode: "dropdown", options: opt("tap", ENUMS.tap_action) } } },
          ...(config.tap_action === "none" ? [] : [{ name: "mark_read", selector: { boolean: {} } }]),
        ],
      },
      { type: "expandable", name: "advanced", flatten: true, icon: "mdi:cog-outline", schema: advanced },
    ];
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => (STRINGS.en[schema.name] ? t(pageLanguage(this._hass), schema.name) : undefined);
      this._form.computeHelper = (schema) => {
        const key = `helper_${schema.name}`;
        return STRINGS.en[key] ? t(pageLanguage(this._hass), key) : undefined;
      };
      this._form.addEventListener("value-changed", (ev) => {
        let config = { ...ev.detail.value };
        if (config[""] && typeof config[""] === "object") config = { ...config, ...config[""] };
        delete config[""];
        // מנקים ערכים ריקים כדי שה-YAML יישאר נקי
        for (const key of ["entities", "feeds", "title"]) {
          if (Array.isArray(config[key]) ? !config[key].length : !config[key]) delete config[key];
        }
        this._config = config;
        this._form.schema = this._schema(config);
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { ...DEFAULTS, ...this._config };
    this._form.schema = this._schema(this._config);
  }
}

/**
 * ‏HA טוען את הקובץ (add_extra_js_url) לפני שהוא מתקין polyfill של רישום רכיבים,
 * ואז ההגדרה הראשונה הולכת לאיבוד. לכן מגדירים שוב עד שה-polyfill מוכן.
 */
function defineCard() {
  if (!customElements.get("news-card")) customElements.define("news-card", NewsCard);
  if (!customElements.get("news-card-editor")) customElements.define("news-card-editor", NewsCardEditor);
}

if (!window.customCards?.some((c) => c.type === "news-card")) {
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "news-card",
    name: "News Card",
    description: "News from RSS, Atom and JSON feeds as a list or an infinite ticker.",
    preview: true,
    documentationURL: "https://github.com/yosef-chai/news-card",
    getEntitySuggestion: (hass, entityId) => {
      const e = hass?.entities?.[entityId];
      return e?.platform === DOMAIN && e.device_id ? { config: { type: "custom:news-card", feeds: [e.device_id] } } : null;
    },
  });
  console.info(`%c NEWS-CARD %c ${CARD_VERSION} `, "color:#fff;background:#2b8fd0;font-weight:700", "color:#2b8fd0");
}
defineCard();
// ponytail: בדיקה כל 250ms עד 30 שניות; מספיק לכל טעינת ממשק רגילה
let tries = 0;
const timer = setInterval(() => {
  defineCard();
  if (++tries > 120 || (window.CustomElementRegistryPolyfill && customElements.get("news-card") && customElements.get("news-card-editor"))) clearInterval(timer);
}, 250);
