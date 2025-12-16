import React, { useMemo, useState } from "react";
import { buildIcsUrl, fetchNameDays, fetchSaints } from "./api";
import { TRADITIONS } from "./traditions";

const todayIso = () => new Date().toISOString().slice(0, 10);

export default function App() {
  const [selectedDate, setSelectedDate] = useState(todayIso());
  const [selectedTraditions, setSelectedTraditions] = useState(Object.keys(TRADITIONS));
  const [saints, setSaints] = useState([]);
  const [nameDayContacts, setNameDayContacts] = useState('[{"full_name":"Andrew Example"}]');
  const [nameDayResults, setNameDayResults] = useState([]);
  const [icsDays, setIcsDays] = useState(365);
  const [icsTradition, setIcsTradition] = useState("serbian");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const icsLink = useMemo(() => buildIcsUrl(icsTradition, selectedDate, icsDays), [icsTradition, selectedDate, icsDays]);

  async function loadSaints() {
    setError("");
    setLoading(true);
    try {
      const data = await fetchSaints(selectedDate, selectedTraditions);
      setSaints(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadNameDays() {
    setError("");
    setLoading(true);
    try {
      const contacts = JSON.parse(nameDayContacts || "[]");
      const data = await fetchNameDays(selectedDate, selectedTraditions, contacts);
      setNameDayResults(data.matches || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleTradition(key) {
    setSelectedTraditions((prev) =>
      prev.includes(key) ? prev.filter((t) => t !== key) : [...prev, key]
    );
  }

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">orthodox-calendar</p>
          <h1>Discover today’s saints and name-days</h1>
          <p className="lede">
            Pull daily saints across Orthodox traditions, subscribe via iCal, and notify friends on their name-day.
          </p>
          <div className="hero-actions">
            <button onClick={loadSaints} className="primary">
              View saints of the day
            </button>
            <a className="ghost" href={icsLink} target="_blank" rel="noreferrer">
              Subscribe via ICS
            </a>
          </div>
        </div>
        <div className="card">
          <p className="card-title">Date</p>
          <input type="date" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} />
          <p className="card-title">Traditions</p>
          <div className="chips">
            {Object.entries(TRADITIONS).map(([key, label]) => (
              <button
                key={key}
                className={`chip ${selectedTraditions.includes(key) ? "active" : ""}`}
                onClick={() => toggleTradition(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Saints & Feasts</p>
            <h2>What is celebrated</h2>
          </div>
          <button onClick={loadSaints} disabled={loading} className="secondary">
            Refresh
          </button>
        </div>
        {loading && <p>Loading…</p>}
        {!loading && saints.length === 0 && <p>No entries found for this date/tradition set.</p>}
        <div className="grid">
          {saints.map((entry) => (
            <div key={`${entry.tradition}-${entry.calendar_date}`} className="card">
              <p className="eyebrow">{entry.tradition}</p>
              <h3>{entry.calendar_date}</h3>
              <ul className="saint-list">
                {entry.saints.map((saint) => (
                  <li key={saint.name}>
                    <div className="saint-title">
                      <span>{saint.title || saint.name}</span>
                      {saint.feast_type && <small className="pill">{saint.feast_type}</small>}
                    </div>
                    {saint.hagiography_url && (
                      <a href={saint.hagiography_url} target="_blank" rel="noreferrer">
                        Hagiography
                      </a>
                    )}
                  </li>
                ))}
              </ul>
              {entry.notes && <p className="note">{entry.notes}</p>}
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Name-day checker</p>
            <h2>Find friends to congratulate</h2>
          </div>
          <button onClick={loadNameDays} disabled={loading} className="secondary">
            Check contacts
          </button>
        </div>
        <div className="grid two">
          <div className="card">
            <p className="card-title">Contacts JSON</p>
            <p className="note">Provide objects with `full_name` (and optional `source`).</p>
            <textarea value={nameDayContacts} onChange={(e) => setNameDayContacts(e.target.value)} rows={8} />
          </div>
          <div className="card">
            <p className="card-title">Matches</p>
            {nameDayResults.length === 0 && <p>No matches yet.</p>}
            <ul className="match-list">
              {nameDayResults.map((match) => (
                <li key={`${match.contact.full_name}-${match.saint.name}`}>
                  <div className="saint-title">
                    <span>{match.contact.full_name}</span>
                    <small className="pill">{match.tradition}</small>
                  </div>
                  <p className="note">
                    Name-day: {match.saint.title || match.saint.name} ({match.calendar_system})
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">ICS subscription</p>
            <h2>Add to your calendar</h2>
          </div>
        </div>
        <div className="card">
          <div className="ics-form">
            <label>
              Tradition
              <select value={icsTradition} onChange={(e) => setIcsTradition(e.target.value)}>
                {Object.entries(TRADITIONS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Start date
              <input type="date" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} />
            </label>
            <label>
              Days
              <input type="number" min={1} max={730} value={icsDays} onChange={(e) => setIcsDays(e.target.value)} />
            </label>
            <div className="ics-link">
              <p className="note">Subscribe with this link:</p>
              <code>{icsLink}</code>
              <a className="ghost" href={icsLink} target="_blank" rel="noreferrer">
                Open ICS
              </a>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
