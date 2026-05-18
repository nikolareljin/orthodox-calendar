import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { buildIcsUrl, fetchMonthCalendar, fetchMoonPhase, fetchReadings, fetchSaints } from "./api";
import HagiaSophia from "./HagiaSophia";
import { TRADITIONS, WORLD_CHURCHES } from "./traditions";

const MONTH_NAMES = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];


const MIN_YEAR = 1;
const MAX_YEAR = 9999;
const DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];

// new Date(year, ...) treats years 0–99 as 1900+year; setFullYear avoids that.
function makeDate(year, month0, day) {
  const d = new Date(0);
  d.setFullYear(year, month0, day);
  return d;
}

function getCalendarCells(year, month) {
  const firstDow = makeDate(year, month - 1, 1).getDay();
  const daysInMonth = makeDate(year, month, 0).getDate(); // day 0 of next month = last day of this
  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  return cells;
}

function pad2(n) { return String(n).padStart(2, "0"); }

function toDateStr(year, month, day) {
  // Zero-pad year to 4 digits so Python's date.fromisoformat() accepts it (e.g. "0033-01-02")
  return `${String(year).padStart(4, "0")}-${pad2(month)}-${pad2(day)}`;
}

function formatGregorianDate(year, month, day) {
  const d = makeDate(year, month - 1, day);
  const dow = DAY_NAMES[d.getDay()];
  const yearStr = year < 1000 ? `${year} AD` : String(year);
  return `${dow}, ${MONTH_NAMES[month - 1]} ${day}, ${yearStr}`;
}

// Ge'ez (Amharic) script month names for the Ethiopian calendar
const ETH_MONTH_NAMES = [
  "መስከረም", "ጥቅምት", "ኅዳር", "ታኅሣሥ",
  "ጥር", "የካቲት", "መጋቢት", "ሚያዝያ",
  "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜ",
];

// Coptic (Bohairic) script month names for the Coptic calendar
const COPTIC_MONTH_NAMES = [
  "ⲑⲱⲟⲩⲧ", "ⲡⲁⲱⲡⲉ", "Ϩⲁⲑⲱⲣ", "ⲕⲓⲁϩⲕ",
  "ⲧⲱⲃⲉ", "ⲁⲙϣⲓⲣ", "ⲡⲁⲣⲉⲙϩⲁⲧ", "ⲡⲁⲣⲙⲟⲩⲧⲉ",
  "ⲡⲁϣⲟⲛⲥ", "ⲡⲁⲱⲛⲉ", "ⲉⲡⲏⲡ", "ⲙⲉⲥⲱⲣⲏ", "ⲛⲁⲥⲓⲉ",
];

function isGregorianLeap(y) {
  return y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
}

// Both Coptic and Ethiopian share the same new year date (Sep 11 or 12).
function alexandrianNewYearDay(gYear) {
  return isGregorianLeap(gYear + 1) ? 12 : 11;
}

// Shared algorithm for Coptic/Ethiopian (identical 13-month solar structure).
function _alexandrianDate(gYear, gMonth, gDay, yearOffset, monthNames, shortMonthLeapMod) {
  const nyDay = alexandrianNewYearDay(gYear);
  const isAfterNewYear = gMonth > 9 || (gMonth === 9 && gDay >= nyDay);
  const tradYear = isAfterNewYear ? gYear - yearOffset : gYear - yearOffset - 1;
  const nyGYear = isAfterNewYear ? gYear : gYear - 1;
  const nyDate = Date.UTC(nyGYear, 8, alexandrianNewYearDay(nyGYear));
  const currDate = Date.UTC(gYear, gMonth - 1, gDay);
  const daysSinceNY = Math.round((currDate - nyDate) / 86400000);
  const monthIdx = Math.min(12, Math.floor(daysSinceNY / 30));
  const dayRaw = (daysSinceNY % 30) + 1;
  // 13th month has 5 days normally, 6 in leap years (year % 4 === shortMonthLeapMod)
  const maxShortDay = tradYear % 4 === shortMonthLeapMod ? 6 : 5;
  const tradDay = monthIdx === 12 ? Math.min(dayRaw, maxShortDay) : dayRaw;
  return { year: tradYear, monthName: monthNames[monthIdx], day: tradDay };
}

function getEthiopianDate(gYear, gMonth, gDay) {
  // Ethiopian era offset: year is Gregorian − 8 (before new year) or − 7 (after)
  return _alexandrianDate(gYear, gMonth, gDay, 7, ETH_MONTH_NAMES, 3);
}

function getCopticDate(gYear, gMonth, gDay) {
  // Coptic Anno Martyrum: year is Gregorian − 284 (before Nayrouz) or − 283 (after)
  return _alexandrianDate(gYear, gMonth, gDay, 283, COPTIC_MONTH_NAMES, 3);
}

function clampYear(y) { return Math.max(MIN_YEAR, Math.min(MAX_YEAR, y)); }

function getStoredTheme() {
  try {
    return localStorage.getItem("oc-theme") || "dark";
  } catch {
    return "dark";
  }
}

function getStoredTradition() {
  try {
    const stored = localStorage.getItem("oc-tradition");
    if (!stored) return "serbian";
    // Migrate renamed key: "oriental" → "coptic"
    const migrated = stored === "oriental" ? "coptic" : stored;
    if (Object.hasOwn(TRADITIONS, migrated)) return migrated;
  } catch {
    // ignore storage errors
  }
  return "serbian";
}

function feastClass(info) {
  if (!info) return "";
  if (info.feast_types.includes("Great Feast")) return "great-feast";
  if (info.feast_types.length > 0) return "has-feast";
  return "has-saints";
}

// ── CalendarGrid ────────────────────────────────────────────────────────────
function CalendarGrid({ year, month, selectedDay, onDaySelect, todayYear, todayMonth, todayDay, monthData }) {
  const cells = useMemo(() => getCalendarCells(year, month), [year, month]);
  const isThisMonth = year === todayYear && month === todayMonth;

  return (
    <div className="cal">
      <div className="cal-weekdays">
        {["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map((d) => (
          <div key={d} className="cal-weekday">{d}</div>
        ))}
      </div>
      <div className="cal-cells">
        {cells.map((day, i) => {
          const isToday = isThisMonth && day === todayDay;
          const isSelected = day === selectedDay;
          const dateKey = day ? toDateStr(year, month, day) : null;
          const info = dateKey ? monthData[dateKey] : null;
          const cls = [
            "cal-cell",
            !day ? "empty" : "",
            isToday ? "today" : "",
            isSelected ? "selected" : "",
          ].filter(Boolean).join(" ");
          return (
            <button
              key={i}
              className={cls}
              onClick={() => day && onDaySelect(day)}
              disabled={!day}
              title={info ? info.main_feast : undefined}
              aria-label={day ? `${MONTH_NAMES[month - 1]} ${day}${info ? `: ${info.main_feast}` : ""}` : undefined}
            >
              <span className="cal-day-num">{day}</span>
              {info && <span className={`cal-dot ${feastClass(info)}`} />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

const SCOPE_LABEL = {
  universal: "Universal",
  "pan-orthodox": "Pan-Orthodox",
  local: "Local",
  oriental: "Oriental",
  "church-of-the-east": "Church of the East",
};

// ── SaintCard ───────────────────────────────────────────────────────────────
function SaintCard({ saint }) {
  const [expanded, setExpanded] = useState(false);
  const hasBody = saint.notes || saint.hagiography_url;
  const pillClass = ["feast-pill", saint.feast_type === "Great Feast" ? "great-feast" : ""].filter(Boolean).join(" ");

  return (
    <div className="saint-card">
      <button
        type="button"
        className="saint-header"
        onClick={() => hasBody && setExpanded((e) => !e)}
        disabled={!hasBody}
        aria-expanded={hasBody ? expanded : undefined}
      >
        <span className="saint-header-left">
          <span className="saint-name">{saint.title || saint.name}</span>
          {saint.name_hy && <span className="saint-name-alt">{saint.name_hy}</span>}
          <span className="saint-pills">
            {saint.feast_type && <span className={pillClass}>{saint.feast_type}</span>}
            {saint.canonized_by && (
              <span
                className={`canonized-pill scope-${saint.canonization_scope || "local"}`}
                title={`Canonized by ${saint.canonized_by}${saint.year_canonized ? ` (${saint.year_canonized})` : ""}`}
              >
                {SCOPE_LABEL[saint.canonization_scope] || "Local"} · {saint.canonized_by}
                {saint.year_canonized ? ` ${saint.year_canonized}` : ""}
              </span>
            )}
          </span>
        </span>
        {hasBody && <span className="expand-icon">{expanded ? "▲" : "▼"}</span>}
      </button>
      {expanded && hasBody && (
        <div className="saint-body">
          {saint.notes && <p className="saint-hagio">{saint.notes}</p>}
          {saint.hagiography_url && (
            <a href={saint.hagiography_url} target="_blank" rel="noreferrer" className="saint-link">
              Read full hagiography →
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// ── ReadingCard ─────────────────────────────────────────────────────────────
function ReadingCard({ reading }) {
  const [expanded, setExpanded] = useState(false);
  const hasText = Array.isArray(reading.passage) && reading.passage.length > 0;
  const ref = reading.display || reading.short_display || (() => {
    if (!reading.book) return "Reading";
    if (!Array.isArray(reading.passage) || reading.passage.length === 0) return reading.book;
    const first = reading.passage[0].verse;
    const last = reading.passage[reading.passage.length - 1].verse;
    return first === last ? `${reading.book} ${first}` : `${reading.book} ${first}–${last}`;
  })();

  return (
    <div className="reading-card">
      <button
        className="reading-header"
        onClick={() => hasText && setExpanded((e) => !e)}
        disabled={!hasText}
        aria-expanded={hasText ? expanded : undefined}
      >
        <div className="reading-header-left">
          {reading.source && <span className="reading-source">{reading.source}</span>}
          <span className="reading-ref">{ref}</span>
          {(reading.desc || reading.description) && <span className="reading-desc">{reading.desc || reading.description}</span>}
        </div>
        {hasText && <span className="expand-icon">{expanded ? "▲" : "▼"}</span>}
      </button>
      {expanded && hasText && (
        <div className="reading-body">
          {reading.passage.map((v, i) => (
            <span key={i}>
              {v.paragraph_start && i > 0 && <br />}
              <sup className="verse-num">{v.verse}</sup>
              {v.content}{" "}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function fastingGlyph(fastLevel, fastException) {
  if (!fastLevel || fastLevel === 0) return { emoji: "✅", label: "No fast" };
  // fast_exception from orthocal: 2=fish+wine+oil, 1=wine+oil, 4=wine only
  if (fastException === 2) return { emoji: "🐟", label: "Fish, Wine & Oil" };
  if (fastException === 1) return { emoji: "🍷", label: "Wine & Oil allowed" };
  if (fastException === 4) return { emoji: "🍷", label: "Wine allowed" };
  return { emoji: "🌿", label: "Strict fast" };
}

// ── Octoechos tone descriptions ─────────────────────────────────────────────
const TONE_INFO = {
  1: { name: "First Tone",        character: "Solemn and majestic — the mode of the Resurrection",    note: "Opens the eight-week Octoechos cycle after Pascha. Associated with resurrectional troparions and stichera.",  youtube: "https://www.youtube.com/watch?v=_V_c2adKRbQ" },
  2: { name: "Second Tone",       character: "Gentle and tender — humble and meditative",             note: "A subdued, introspective mode suited to prayers of contrition and quiet praise.",                             youtube: "https://www.youtube.com/watch?v=M0TwBgpyhko" },
  3: { name: "Third Tone",        character: "Balanced and calm — steady devotional reverence",       note: "A middle ground between the solemn and the joyful; used for unhurried, contemplative singing.",              youtube: "https://www.youtube.com/watch?v=zJP_1RPGm_I" },
  4: { name: "Fourth Tone",       character: "Festive and bright — joyful and triumphant",            note: "Warm and expressive; often chosen for festal hymns and vigil canons.",                                       youtube: "https://www.youtube.com/watch?v=H9-wPlQltpM" },
  5: { name: "Plagal First Tone", character: "Tender and lyrical — sweet and intimate",              note: "Plagal (derived) form of Tone 1, softer in character; the \"tone of love\" in some traditions.",             youtube: "https://www.youtube.com/watch?v=KmiXfJ00am4" },
  6: { name: "Plagal Second Tone",character: "Mournful — penitential sorrow and longing",            note: "The tone of mourning; associated with repentance and deep longing for God.",                                  youtube: "https://www.youtube.com/watch?v=VNKIcZP6ook" },
  7: { name: "Grave Tone",        character: "Solemn and weighty — deep contemplation",              note: "Dark and serious; reserved for the most solemn moments in the liturgical year.",                             youtube: "https://www.youtube.com/watch?v=0vz8UIVy7LI" },
  8: { name: "Plagal Fourth Tone",character: "Grand and majestic — the fullness of praise",          note: "Richest and most complete tone; brings the eight-week Octoechos cycle to a noble close.",                    youtube: "https://www.youtube.com/watch?v=xBo4eODl-yA" },
};

function ToneBadge({ toneNum }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const info = TONE_INFO[toneNum];

  useEffect(() => {
    if (!open) return;
    function onOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [open]);

  if (!info) return (
    <div className="fast-info"><span>♪</span><span>Tone {toneNum}</span></div>
  );

  return (
    <div className="tone-badge-wrap" ref={wrapRef}>
      <button
        className={`fast-info tone-badge${open ? " tone-badge--open" : ""}`}
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        aria-label={`Tone ${toneNum} — click for info`}
      >
        <span>♪</span>
        <span>Tone {toneNum}</span>
        <span className="tone-info-icon">ⓘ</span>
      </button>
      {open && (
        <div className="tone-popup" role="tooltip">
          <p className="tone-popup-name">{info.name}</p>
          <p className="tone-popup-char">{info.character}</p>
          <p className="tone-popup-note">{info.note}</p>
          {info.youtube && (
            <a
              href={info.youtube}
              target="_blank"
              rel="noreferrer noopener"
              className="tone-popup-listen"
            >
              ▶ Listen — Resurrectional Troparion
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// ── DayDetail ───────────────────────────────────────────────────────────────
function DayDetail({ saints, readings, moonPhase, loading, error, year, month, day, tradition }) {
  if (!day) return (
    <div className="day-detail day-detail--empty">
      <p>Select a day to see saints, fasting rule, and readings.</p>
    </div>
  );

  const entry = saints && saints[0];
  const fastText = readings?.fast_level_desc || null;
  const fastLevel = readings?.fast_level ?? null;
  const fastException = readings?.fast_exception ?? null;
  const fasting = fastLevel !== null ? fastingGlyph(fastLevel, fastException) : null;
  const toneNum = readings?.tone || null;
  const titles = readings?.titles?.length ? readings.titles : null;
  const feasts = readings?.feasts?.length ? readings.feasts : null;
  const readingsList = readings?.readings?.length ? readings.readings : null;

  return (
    <div className="day-detail">
      <div className="day-detail-header">
        <h2>{formatGregorianDate(year, month, day)}</h2>
        {entry && entry.calendar_date && (entry.calendar_system === "julian" || entry.calendar_system === "revised") && (
          <p className="cal-date-note">
            {entry.calendar_date} ({entry.calendar_system === "julian" ? "Old Style / Julian" : "Revised / New Calendar"})
          </p>
        )}
        {tradition === "ethiopian" && (() => {
          const eth = getEthiopianDate(year, month, day);
          return (
            <p className="cal-date-note eth-date-note">
              {eth.monthName} {eth.day}, {eth.year} ዓ.ም. — Ethiopian Calendar
            </p>
          );
        })()}
        {tradition === "coptic" && (() => {
          const copt = getCopticDate(year, month, day);
          return (
            <p className="cal-date-note eth-date-note">
              {copt.monthName} {copt.day}, {copt.year} Ⲁ.Ⲙ. — Coptic Calendar
            </p>
          );
        })()}
      </div>

      {error && <div className="error-msg">{error}</div>}
      {loading && <p className="loading-msg">Loading…</p>}

      {!loading && (
        <>
          {titles && (
            <div className="feasts-section">
              {titles.map((t, i) => (
                <div key={i} className="feast-item">{t}</div>
              ))}
            </div>
          )}

          <div className="day-badges">
            {moonPhase && (
              <div className="fast-info moon-info" title={`Lunar phase: ${moonPhase.phase_name} (${Math.round(moonPhase.illumination * 100)}% illuminated)`}>
                <span>{moonPhase.emoji}</span>
                <span>{moonPhase.phase_name}</span>
              </div>
            )}
            {fasting && (
              <div className="fast-info" title={fastText || fasting.label}>
                <span>{fasting.emoji}</span>
                <span>{fastText || fasting.label}</span>
              </div>
            )}
            {toneNum && <ToneBadge toneNum={toneNum} />}
          </div>

          {feasts && (
            <div className="feasts-section">
              <p className="feast-label">Feasts of the Day</p>
              {feasts.map((f, i) => (
                <div key={i} className="feast-item">{f}</div>
              ))}
            </div>
          )}

          <div className="saints-section">
            <p className="section-label">Saints Commemorated</p>
            {entry && entry.saints.length > 0 ? (
              entry.saints.map((saint, i) => <SaintCard key={i} saint={saint} />)
            ) : (
              <p className="no-data">No saints found for this tradition and date.</p>
            )}
          </div>

          {readingsList && (
            <div className="readings-section">
              <p className="section-label">Liturgical Readings</p>
              {readingsList.map((r, i) => (
                <ReadingCard key={i} reading={r} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── App ──────────────────────────────────────────────────────────────────────
export default function App() {
  const getToday = () => new Date();
  const initialToday = useMemo(getToday, []);
  const [theme, setTheme] = useState(getStoredTheme);
  const [tradition, setTradition] = useState(getStoredTradition);
  const [year, setYear] = useState(initialToday.getFullYear());
  const [month, setMonth] = useState(initialToday.getMonth() + 1);
  const [selectedDay, setSelectedDay] = useState(initialToday.getDate());
  const [yearEditing, setYearEditing] = useState(false);
  const [yearDraft, setYearDraft] = useState(String(initialToday.getFullYear()));
  const yearInputRef = useRef(null);
  const today = getToday();

  const [monthData, setMonthData] = useState({});
  const [saints, setSaints] = useState([]);
  const [readings, setReadings] = useState(null);
  const [moonPhase, setMoonPhase] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const loadDayRequestRef = useRef(0);
  const loadMonthRequestRef = useRef(0);

  useEffect(() => {
    const baseUrl = import.meta.env.BASE_URL || "/";
    const fontUrl = (file) => `${baseUrl.replace(/\/?$/, "/")}fonts/${file}`;
    const font = new FontFace(
      "NB-Byzantine",
      `url(${fontUrl("NEOBRG__1.ttf")}) format("truetype"), url(${fontUrl("nbyzn.ttf")}) format("truetype")`,
      { display: "swap" }
    );
    font.load().then((loaded) => document.fonts.add(loaded)).catch(() => {});
  }, []);

  const selectedDate = useMemo(
    () => selectedDay ? toDateStr(year, month, selectedDay) : null,
    [year, month, selectedDay]
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("oc-theme", theme);
    } catch {
      // Browsers can disable storage; the selected theme still applies for this session.
    }
  }, [theme]);

  useEffect(() => {
    try {
      localStorage.setItem("oc-tradition", tradition);
    } catch {
      // ignore storage errors
    }
  }, [tradition]);

  const loadMonth = useCallback(async () => {
    const requestId = loadMonthRequestRef.current + 1;
    loadMonthRequestRef.current = requestId;
    setMonthData({});
    try {
      const data = await fetchMonthCalendar(year, month, tradition);
      if (loadMonthRequestRef.current !== requestId) return;
      setMonthData(data);
    } catch {
      // month dots are non-critical; silently ignore
    }
  }, [year, month, tradition]);

  useEffect(() => {
    loadMonth();
  }, [loadMonth]);

  const loadDay = useCallback(async () => {
    const requestId = loadDayRequestRef.current + 1;
    loadDayRequestRef.current = requestId;
    if (!selectedDate) {
      setLoading(false);
      return;
    }
    const isCurrentRequest = () => loadDayRequestRef.current === requestId;
    setLoading(true);
    setError("");
    setSaints([]);
    setReadings(null);
    setMoonPhase(null);
    try {
      const [saintsData, readingsData, moonData] = await Promise.allSettled([
        fetchSaints(selectedDate, [tradition]),
        fetchReadings(selectedDate, tradition),
        fetchMoonPhase(selectedDate),
      ]);
      if (!isCurrentRequest()) return;
      if (saintsData.status === "fulfilled") setSaints(saintsData.value);
      else setError("Could not load saints.");
      if (readingsData.status === "fulfilled") setReadings(readingsData.value);
      if (moonData.status === "fulfilled") setMoonPhase(moonData.value);
    } finally {
      if (isCurrentRequest()) setLoading(false);
    }
  }, [selectedDate, tradition]);

  useEffect(() => {
    loadDay();
  }, [loadDay]);

  // Focus and select the year input as soon as it mounts
  useLayoutEffect(() => {
    if (yearEditing && yearInputRef.current) yearInputRef.current.select();
  }, [yearEditing]);

  function cancelYearEdit() { setYearEditing(false); }

  function startYearEdit() {
    setYearDraft(String(year));
    setYearEditing(true);
  }

  function commitYear() {
    const parsed = parseInt(yearDraft, 10);
    if (!isNaN(parsed)) {
      const clamped = clampYear(parsed);
      setYear(clamped);
      setSelectedDay(null);
    }
    setYearEditing(false);
  }

  function handleYearKey(e) {
    if (e.key === "Enter") commitYear();
    if (e.key === "Escape") cancelYearEdit();
  }

  function clampDay(day, toYear, toMonth) {
    if (!day) return day;
    const maxDay = makeDate(toYear, toMonth, 0).getDate();
    return Math.min(day, maxDay);
  }

  function prevYear() {
    cancelYearEdit();
    const newYear = clampYear(year - 1);
    setYear(newYear);
    setSelectedDay((d) => clampDay(d, newYear, month));
  }

  function nextYear() {
    cancelYearEdit();
    const newYear = clampYear(year + 1);
    setYear(newYear);
    setSelectedDay((d) => clampDay(d, newYear, month));
  }

  function prevMonth() {
    cancelYearEdit();
    if (month === 1) {
      if (year > MIN_YEAR) {
        const newYear = year - 1;
        setYear(newYear);
        setMonth(12);
        setSelectedDay((d) => clampDay(d, newYear, 12));
      }
    } else {
      const newMonth = month - 1;
      setMonth(newMonth);
      setSelectedDay((d) => clampDay(d, year, newMonth));
    }
  }

  function nextMonth() {
    cancelYearEdit();
    if (month === 12) {
      if (year < MAX_YEAR) {
        const newYear = year + 1;
        setYear(newYear);
        setMonth(1);
        setSelectedDay((d) => clampDay(d, newYear, 1));
      }
    } else {
      const newMonth = month + 1;
      setMonth(newMonth);
      setSelectedDay((d) => clampDay(d, year, newMonth));
    }
  }

  function goToToday() {
    const currentToday = getToday();
    cancelYearEdit();
    setYear(currentToday.getFullYear());
    setMonth(currentToday.getMonth() + 1);
    setSelectedDay(currentToday.getDate());
  }

  const icsUrl = buildIcsUrl(tradition, selectedDate, 365);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Orthodox Calendar</h1>
        <HagiaSophia className="header-sophia" />
        <div className="header-right">
          <button
            className="theme-toggle"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            title="Toggle theme"
          >
            {theme === "dark" ? "☀ Light" : "☽ Dark"}
          </button>
        </div>
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <p className="sidebar-title">Tradition</p>
          {Object.entries(TRADITIONS).map(([key, info]) => (
            <button
              key={key}
              className={`tradition-item ${tradition === key ? "active" : ""}`}
              onClick={() => setTradition(key)}
            >
              <span
                className="trad-type-sym"
                aria-hidden="true"
                title={info.note || "Eastern Orthodox (Chalcedonian)"}
              >
                {info.note === "Church of the East" ? "✝" : info.note === "Non-Chalcedonian" ? "✙" : "☦"}
              </span>
              {info.label}
              {info.note && <span className="tradition-note">{info.note}</span>}
              <span className="tradition-calendar-badge">{info.calendar}</span>
            </button>
          ))}
        </aside>

        <main className="main">
          <div className={`cal-detail-row${selectedDay ? " has-detail" : ""}`}>
            <div className="cal-col">
              <div className="month-nav">
                <button className="nav-btn year-btn" onClick={prevYear} title="Previous year" aria-label="Previous year">«</button>
                <button className="nav-btn" onClick={prevMonth} aria-label="Previous month">‹</button>
                <h2 className="month-label">
                  {MONTH_NAMES[month - 1]}{" "}
                  {yearEditing ? (
                    <input
                      ref={yearInputRef}
                      className="year-input"
                      type="number"
                      min={MIN_YEAR}
                      max={MAX_YEAR}
                      value={yearDraft}
                      onChange={(e) => setYearDraft(e.target.value)}
                      onBlur={commitYear}
                      onKeyDown={handleYearKey}
                      aria-label="Year"
                    />
                  ) : (
                    <button
                      type="button"
                      className="year-display"
                      onClick={startYearEdit}
                      title="Click to enter a year"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          startYearEdit();
                        }
                      }}
                    >
                      {year}
                    </button>
                  )}
                </h2>
                <button className="nav-btn" onClick={nextMonth} aria-label="Next month">›</button>
                <button className="nav-btn year-btn" onClick={nextYear} title="Next year" aria-label="Next year">»</button>
                <button className="today-btn" onClick={goToToday}>Today</button>
              </div>
              <CalendarGrid
                year={year}
                month={month}
                selectedDay={selectedDay}
                onDaySelect={setSelectedDay}
                todayYear={today.getFullYear()}
                todayMonth={today.getMonth() + 1}
                todayDay={today.getDate()}
                monthData={monthData}
              />
            </div>

            <DayDetail
              saints={saints}
              readings={readings}
              moonPhase={moonPhase}
              loading={loading}
              error={error}
              year={year}
              month={month}
              day={selectedDay}
              tradition={tradition}
            />
          </div>

          <div className="ics-section">
            <h3>Subscribe via iCal</h3>
            <div className="ics-row">
              <code className="ics-code">{icsUrl}</code>
              <a className="btn-ghost" href={icsUrl} target="_blank" rel="noreferrer">
                Open ICS
              </a>
            </div>
          </div>

          <OrthodoxWorldSection />
          <AboutSection />
        </main>
      </div>
    </div>
  );
}

// ── World Orthodox Directory ──────────────────────────────────────────────────
function WorldDirectory() {
  return (
    <div className="world-dir">
      <div className="world-dir-legend">
        <span><b>☦</b> Eastern Orthodox</span>
        <span><b>✙</b> Oriental Orthodox (Non-Chalcedonian)</span>
        <span><b>✝</b> Church of the East</span>
      </div>
      {WORLD_CHURCHES.map((group) => (
        <div key={group.category} className="world-dir-group">
          <h4 className="world-dir-group-head">
            <span className="world-dir-sym">{group.symbol}</span>
            {group.category}
            <span className="world-dir-subtitle"> — {group.subtitle}</span>
          </h4>
          <ul className="world-dir-list">
            {group.churches.map((c) => (
              <li key={c.name} className="world-dir-item">
                <a href={c.url} target="_blank" rel="noreferrer noopener" className="world-dir-link">
                  {c.name}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

// ── Orthodox World Section ────────────────────────────────────────────────────
function OrthodoxWorldSection() {
  const [open, setOpen] = useState(false);
  return (
    <div className="about-section">
      <button className="about-toggle" onClick={() => setOpen((o) => !o)}>
        <span className="section-label" style={{ margin: 0 }}>Orthodox Churches Worldwide</span>
        <span className="expand-icon">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="about-body">
          <p className="about-text" style={{ marginBottom: "16px" }}>
            All recognized canonical churches worldwide. Links only — no commentary on questions of jurisdiction or recognition.
          </p>
          <WorldDirectory />
        </div>
      )}
    </div>
  );
}

// ── About ─────────────────────────────────────────────────────────────────────
function AboutSection() {
  const [open, setOpen] = useState(false);
  return (
    <div className="about-section">
      <button className="about-toggle" onClick={() => setOpen((o) => !o)}>
        <span className="section-label" style={{ margin: 0 }}>About this calendar</span>
        <span className="expand-icon">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="about-body">
          <div className="about-grid">

            <div className="about-card">
              <h3 className="about-heading">How to use</h3>
              <ol className="about-list">
                <li>Select your <strong>tradition</strong> from the sidebar — Serbian, Greek, Russian, Georgian, Jerusalem, Armenian, and others are supported, each mapped to its calendar system (Julian or Revised).</li>
                <li>Navigate months with <strong>‹ ›</strong> or jump to today. Days with commemorations show a <strong>coloured dot</strong> — gold for Great Feasts, blue for regular saints.</li>
                <li>Click any day to see the <strong>saints and feasts</strong> celebrated that day, fasting rule, tone of the week, and the full Epistle and Gospel readings.</li>
                <li>Expand a saint card to read the <strong>hagiography</strong> excerpt and follow the link to the full biography.</li>
                <li>Use <strong>Subscribe via iCal</strong> to add the feast calendar for your tradition directly to Google Calendar, Apple Calendar, or Outlook.</li>
              </ol>
            </div>

            <div className="about-card">
              <h3 className="about-heading">History</h3>
              <p className="about-text">
                This calendar began life in <strong>1993</strong> as a program written in <strong>Pascal</strong>,
                running on <strong>DOS</strong>. Its sole purpose was to display the <strong>Julian calendar
                saints' days of the Serbian Orthodox Church</strong> — a simple liturgical aid for a single
                community on a single machine.
              </p>
              <p className="about-text">
                Over the following decades it grew alongside the web, absorbing hagiographies, feast readings,
                and the calendar systems of every canonical Orthodox church — Greek, Russian, Romanian, Bulgarian,
                Antiochian, Alexandrian, Jerusalem, Ethiopian, and Oriental Orthodox. What began as a DOS screen
                is now an open API with an iCal feed, a React front end, and data spanning more than 2,970 saints
                across the full liturgical year.
              </p>
              <p className="about-text">
                The project remains a labour of faith and a work in progress. The Synaxarion of the whole Orthodox
                world is vast; no single team can cover it alone.
              </p>
            </div>

            <div className="about-card about-card-full">
              <h3 className="about-heading">Milankovich Calendar</h3>
              <p className="about-text">
                The <strong>Revised Julian calendar</strong>, often called the <strong>Milankovich</strong>
                or <strong>New Calendar</strong>, was proposed at the 1923 Pan-Orthodox congress in
                Constantinople to reduce the growing mismatch between the old Julian dates used by Orthodox
                churches and the civil Gregorian dates used by most surrounding societies.
              </p>
              <p className="about-text">
                It is named for <strong>Milutin Milankovich</strong>, the Serbian mathematician, astronomer,
                and geophysicist who designed the leap-year rule. For fixed feasts, the Revised Julian
                calendar currently matches the Gregorian calendar, which is why many New Calendar Orthodox
                churches celebrate fixed-date feasts such as Christmas on December 25 while still using the
                Orthodox Paschalion for Pascha and the movable cycle.
              </p>
              <p className="about-text">
                The match with the Gregorian calendar is not permanent. The two calendars remain aligned
                until 2800 AD; in that year Gregorian adds a leap day that the Milankovich rule omits, so
                from March 2800 the Gregorian calendar will be one day behind the Revised Julian calendar.
              </p>
            </div>

            <div className="about-card about-card-full">
              <h3 className="about-heading">Join the effort</h3>
              <p className="about-text">
                If you maintain or have built an Orthodox calendar application — whether a mobile app, a parish
                website widget, a printed typikon generator, or a liturgical data set — we would like to hear
                from you. This project is open-source and community-owned. We are looking for:
              </p>
              <ul className="about-list">
                <li><strong>Data contributors</strong> — Synaxarion entries, Octoechos tone schedules, movable-feast logic, translations into Greek, Russian, Serbian, Romanian, Arabic, Amharic, or any other liturgical language.</li>
                <li><strong>Calendar developers</strong> — if your app already models Orthodox feast logic, let us compare notes, merge data sets, or federate APIs rather than duplicating work. Thirty years of reinventing this wheel is enough.</li>
                <li><strong>Hosting and infrastructure</strong> — the backend needs a permanent public home so the iCal feeds and API can be a shared community resource.</li>
                <li><strong>Parishes and monasteries</strong> — if you need a custom deployment, a printed format, or a specific tradition not yet covered, open an issue and describe what you need.</li>
              </ul>
              <p className="about-text">
                Open an issue or pull request at{" "}
                <a href="https://github.com/nikolareljin/orthodox-calendar" target="_blank" rel="noreferrer" className="saint-link">
                  github.com/nikolareljin/orthodox-calendar
                </a>
                , or contact us through the repository. All are welcome.
              </p>
            </div>

            <div className="about-card about-card-full">
              <h3 className="about-heading">Orthodox Churches</h3>
              <p className="about-text" style={{ marginBottom: "16px" }}>
                Each tradition in this calendar corresponds to an autocephalous or autonomous church.
                Below is a brief overview of each, with links to their official websites.
              </p>
              <div className="churches-grid">
                {Object.entries(TRADITIONS).map(([key, info]) => (
                  <div key={key} className="church-card">
                    <div className="church-logo">{info.logo}</div>
                    <div className="church-info">
                      <a
                        href={info.website}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="church-name"
                      >
                        {info.label}
                      </a>
                      <span className="church-founded">Est. {info.founded}</span>
                      {info.patron && (
                        <span className="church-patron">Patron: {info.patron}</span>
                      )}
                      <p className="church-desc">{info.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="about-card about-card-full about-card-support">
              <h3 className="about-heading">Support this project</h3>
              <p className="about-text">
                This calendar has been built and maintained by volunteers since 1993. Running a public
                API and iCal feed costs real money — server hosting, bandwidth, and the many hours spent
                curating and verifying liturgical data. If this calendar is useful to you, your parish,
                or your community, please consider a donation.
              </p>
              <p className="about-text">
                Every contribution — large or small — goes directly toward keeping the service free,
                expanding the data set to more traditions, and improving the application for everyone.
              </p>
              <div className="support-links">
                <a
                  href="https://ko-fi.com/nikolareljin"
                  target="_blank"
                  rel="noreferrer"
                  className="support-btn support-kofi"
                >
                  ☕ Support on Ko-fi
                </a>
              </div>
              <p className="about-text" style={{ marginTop: "12px", fontSize: "13px" }}>
                You can also contribute by improving the code, adding hagiography data, translating the
                interface, or simply spreading the word. All forms of support are deeply appreciated.
              </p>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
