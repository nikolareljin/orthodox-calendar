const configuredApiBase = import.meta.env.VITE_API_BASE;
const API_BASE = configuredApiBase !== undefined
  ? configuredApiBase
  : import.meta.env.DEV
    ? "http://localhost:8000"
    : "";

export async function fetchSaints(date, traditions) {
  const params = new URLSearchParams();
  if (date) params.append("day", date);
  (traditions || []).forEach((t) => params.append("traditions", t));

  const res = await fetch(`${API_BASE}/api/v1/saints?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch saints");
  return res.json();
}

export async function fetchNameDays(date, traditions, contacts) {
  const payload = {
    date,
    traditions: traditions && traditions.length ? traditions : undefined,
    contacts,
  };
  const res = await fetch(`${API_BASE}/api/v1/name-days`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || "Failed to fetch name days");
  }
  return res.json();
}

export async function fetchMonthCalendar(year, month, tradition) {
  const params = new URLSearchParams({ year, month, tradition });
  const res = await fetch(`${API_BASE}/api/v1/calendar?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch month calendar");
  return res.json();
}

export async function fetchReadings(date, tradition) {
  const params = new URLSearchParams();
  if (date) params.append("day", date);
  if (tradition) params.append("tradition", tradition);

  const res = await fetch(`${API_BASE}/api/v1/readings?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch readings");
  return res.json();
}

export async function fetchMoonPhase(date) {
  const params = new URLSearchParams({ day: date });
  const res = await fetch(`${API_BASE}/api/v1/moon-phase?${params}`);
  if (!res.ok) return null;
  return res.json();
}

export async function fetchMovableFeasts(year) {
  const res = await fetch(`${API_BASE}/api/v1/movable-feasts?year=${year}`);
  if (!res.ok) return null;
  return res.json();
}

export function buildIcsUrl(tradition, start, days) {
  const params = new URLSearchParams();
  if (tradition) params.append("tradition", tradition);
  if (start) params.append("start", start);
  if (days) params.append("days", days);
  return `${API_BASE}/api/v1/saints.ics?${params.toString()}`;
}
