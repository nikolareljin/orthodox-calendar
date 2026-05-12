import React, { useCallback, useEffect, useMemo, useState } from "react";
import { buildIcsUrl, fetchMonthCalendar, fetchReadings, fetchSaints } from "./api";
import HagiaSophia from "./HagiaSophia";
import { TRADITIONS } from "./traditions";

const MONTH_NAMES = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];


function getCalendarCells(year, month) {
  const firstDow = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  return cells;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

function toDateStr(year, month, day) {
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

function formatGregorianDate(year, month, day) {
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });
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

// ── SaintCard ───────────────────────────────────────────────────────────────
function SaintCard({ saint }) {
  const [expanded, setExpanded] = useState(false);
  const hasBody = saint.notes || saint.hagiography_url;
  const pillClass = ["feast-pill", saint.feast_type === "Great Feast" ? "great-feast" : ""].filter(Boolean).join(" ");

  return (
    <div className="saint-card">
      <div className="saint-header" onClick={() => hasBody && setExpanded((e) => !e)}>
        <div className="saint-header-left">
          <span className="saint-name">{saint.title || saint.name}</span>
          {saint.feast_type && <span className={pillClass}>{saint.feast_type}</span>}
        </div>
        {hasBody && <span className="expand-icon">{expanded ? "▲" : "▼"}</span>}
      </div>
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

// ── DayDetail ───────────────────────────────────────────────────────────────
function DayDetail({ saints, readings, loading, error, year, month, day }) {
  if (!day) return null;

  const entry = saints && saints[0];
  const fastText = readings?.fast_level_desc || null;
  const tone = readings?.tone ? `Tone ${readings.tone}` : null;
  const titles = readings?.titles?.length ? readings.titles : null;
  const feasts = readings?.feasts?.length ? readings.feasts : null;
  const readingsList = readings?.readings?.length ? readings.readings : null;

  return (
    <div className="day-detail">
      <div className="day-detail-header">
        <h2>{formatGregorianDate(year, month, day)}</h2>
        {entry && entry.calendar_date && (
          <p className="cal-date-note">
            {entry.calendar_date} ({entry.calendar_system === "julian" ? "Old Style / Julian" : "Revised / Gregorian"})
          </p>
        )}
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

          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "16px" }}>
            {fastText && (
              <div className="fast-info">
                <span>🕯</span>
                <span>{fastText}</span>
              </div>
            )}
            {tone && (
              <div className="fast-info">
                <span>♪</span>
                <span>{tone}</span>
              </div>
            )}
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
                <div key={i} className="reading-item">
                  <span className="reading-ref">{r.display || `${r.book} ${r.passage}`}</span>
                  {r.desc && <span className="reading-desc">{r.desc}</span>}
                </div>
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
  const now = useMemo(() => new Date(), []);
  const [theme, setTheme] = useState(() => localStorage.getItem("oc-theme") || "dark");
  const [tradition, setTradition] = useState("serbian");
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [selectedDay, setSelectedDay] = useState(now.getDate());

  const [monthData, setMonthData] = useState({});
  const [saints, setSaints] = useState([]);
  const [readings, setReadings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const selectedDate = useMemo(
    () => toDateStr(year, month, selectedDay),
    [year, month, selectedDay]
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("oc-theme", theme);
  }, [theme]);

  const loadMonth = useCallback(async () => {
    setMonthData({});
    try {
      const data = await fetchMonthCalendar(year, month, tradition);
      setMonthData(data);
    } catch {
      // month dots are non-critical; silently ignore
    }
  }, [year, month, tradition]);

  useEffect(() => {
    loadMonth();
  }, [loadMonth]);

  const loadDay = useCallback(async () => {
    setLoading(true);
    setError("");
    setSaints([]);
    setReadings(null);
    try {
      const [saintsData, readingsData] = await Promise.allSettled([
        fetchSaints(selectedDate, [tradition]),
        fetchReadings(selectedDate, tradition),
      ]);
      if (saintsData.status === "fulfilled") setSaints(saintsData.value);
      else setError("Could not load saints.");
      if (readingsData.status === "fulfilled") setReadings(readingsData.value);
    } finally {
      setLoading(false);
    }
  }, [selectedDate, tradition]);

  useEffect(() => {
    loadDay();
  }, [loadDay]);

  function prevMonth() {
    if (month === 1) { setYear((y) => y - 1); setMonth(12); }
    else setMonth((m) => m - 1);
    setSelectedDay(null);
  }

  function nextMonth() {
    if (month === 12) { setYear((y) => y + 1); setMonth(1); }
    else setMonth((m) => m + 1);
    setSelectedDay(null);
  }

  function goToToday() {
    setYear(now.getFullYear());
    setMonth(now.getMonth() + 1);
    setSelectedDay(now.getDate());
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
              {info.label}
              <span className="tradition-calendar-badge">{info.calendar}</span>
            </button>
          ))}
        </aside>

        <main className="main">
          <div className="month-nav">
            <h2 className="month-label">{MONTH_NAMES[month - 1]} {year}</h2>
            <button className="nav-btn" onClick={prevMonth}>‹</button>
            <button className="nav-btn" onClick={nextMonth}>›</button>
            <button className="today-btn" onClick={goToToday}>Today</button>
          </div>

          <CalendarGrid
            year={year}
            month={month}
            selectedDay={selectedDay}
            onDaySelect={setSelectedDay}
            todayYear={now.getFullYear()}
            todayMonth={now.getMonth() + 1}
            todayDay={now.getDate()}
            monthData={monthData}
          />

          <DayDetail
            saints={saints}
            readings={readings}
            loading={loading}
            error={error}
            year={year}
            month={month}
            day={selectedDay}
          />

          <div className="ics-section">
            <h3>Subscribe via iCal</h3>
            <div className="ics-row">
              <code className="ics-code">{icsUrl}</code>
              <a className="btn-ghost" href={icsUrl} target="_blank" rel="noreferrer">
                Open ICS
              </a>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
