#!/usr/bin/env python3
"""
Import Ethiopian Orthodox Tewahedo Church saints and feasts.

Sources (combined):
  1. ethiopianorthodox.org/english/calendar.html  — official English feast list
  2. Curated Ge'ez synaxarium: major saints with verified Ethiopian calendar dates

The Ethiopian (Ge'ez) calendar uses 13 months derived from the Alexandrian/
Coptic calendar. Each month starts on a fixed Gregorian date:
  Meskerem 1 = Sep 11, Tikimt 1 = Oct 11, Hidar 1 = Nov 10, etc.

Dates are stored as Gregorian MM-DD so the backend looks them up directly
(tradition calendar = GREGORIAN in config.py).

Usage:
    python3 scripts/import_ethiopian.py --out backend/app/data/traditions/ethiopian_saints.json
    python3 scripts/import_ethiopian.py --scrape-only --out /path/to/output.json
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

CALENDAR_URL = "https://ethiopianorthodox.org/english/calendar.html"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# Ethiopian months with their Gregorian start dates (non-leap year)
# Verified against: Tahsas 29 = Jan 7, Tir 11 = Jan 19 (from official site)
_ETH_MONTHS: dict[str, tuple[int, int]] = {
    "Meskerem": (9, 11),
    "Tikimt":   (10, 11),
    "Hidar":    (11, 10),
    "Tahsas":   (12, 10),
    "Tir":      (1, 9),
    "Ter":      (1, 9),     # attested variant spelling used by ethiopianorthodox.org
    "Yekatit":  (2, 8),
    "Megabit":  (3, 10),
    "Miyazya":  (4, 9),
    "Ginbot":   (5, 9),
    "Sene":     (6, 8),
    "Hamle":    (7, 8),
    "Nehase":   (8, 7),
    "Nehassie": (8, 7),     # attested variant spelling used by ethiopianorthodox.org
    # NOTE: Pagume entries must use day <= 5 (6 in Ethiopian leap years only).
    # Pagume 6 maps to Sep 11 = Meskerem 1 of the next year (collision avoided
    # because day 6 only exists in a leap year where Meskerem 1 is Sep 12).
    "Pagume":   (9, 6),
}

# Regex to find Ethiopian date patterns: "Tahsas 29 E.C. (7 January)"
_ETH_DATE_RE = re.compile(
    r"(Meskerem|Tikimt|Hidar|Tahsas|Tir|Ter|Yekatit|Megabit|Miyazya|Ginbot|Sene|Hamle|Nehase|Nehassie|Pagume)"
    r"\s+(\d+)\s*E\.?C\.?\s*\(([^)]+)\)",
    re.IGNORECASE,
)


def eth_to_gregorian_md(month_name: str, day: int) -> str:
    """Convert Ethiopian calendar month + day to Gregorian MM-DD."""
    for k, (m, d) in _ETH_MONTHS.items():
        if k.lower() == month_name.lower():
            # Use a non-leap reference year for month arithmetic (2024 is a leap year)
            start = date(2023, m, d)
            result = start + timedelta(days=day - 1)
            return result.strftime("%m-%d")
    raise ValueError(f"Unknown Ethiopian month: {month_name}")


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def scrape_official_site() -> list[dict]:
    """Scrape ethiopianorthodox.org for feast dates."""
    try:
        html = _fetch_text(CALENDAR_URL)
    except Exception as exc:
        print(f"  Warning: could not fetch official site: {exc}", file=sys.stderr)
        return []

    text = _strip_tags(html)
    entries = []
    seen_md: set[str] = set()

    for m in _ETH_DATE_RE.finditer(text):
        eth_month = m.group(1)
        eth_day = int(m.group(2))
        gregorian_text = m.group(3).strip()

        try:
            md = eth_to_gregorian_md(eth_month, eth_day)
        except ValueError:
            continue

        if md in seen_md:
            continue
        seen_md.add(md)

        # Extract feast name from surrounding context
        start = max(0, m.start() - 200)
        context = text[start:m.start()].strip()
        # Last non-empty line before the date
        lines = [l.strip() for l in context.split("\n") if l.strip()]
        name = lines[-1] if lines else gregorian_text

        name = re.sub(r"\s+", " ", name).strip()
        if len(name) < 4 or len(name) > 120:
            name = f"Ethiopian feast ({eth_month} {eth_day})"

        entries.append({
            "month_day": md,
            "eth_date": f"{eth_month} {eth_day}",
            "name": name,
        })
        print(f"  {md} ({eth_month} {eth_day}): {name[:60]}", file=sys.stderr)

    return entries


# ── Curated Ge'ez synaxarium ──────────────────────────────────────────────────
# Sources: Ethiopian Orthodox Tewahedo Church official publications,
# Budge's "The Book of the Saints of the Ethiopian Church" (1928),
# and verified Wikipedia entries for individual saints.
#
# Format: (eth_month, eth_day, feast_type, title, short_name, notes)
#
# Monthly commemorations of St. Mary (21st of each month), St. Michael (12th),
# St. Gabriel (22nd) etc. are included as their primary annual feast only
# (first month occurrence) to avoid 12 duplicate entries per saint.
_CURATED: list[tuple] = [
    # ── Feasts of Our Lord ────────────────────────────────────────────────────
    ("Tahsas", 29, "Great Feast", "The Nativity of Our Lord Jesus Christ (Lidat)", "Nativity",
     "Christmas in the Ethiopian Orthodox Church, celebrated on Tahsas 29 (January 7 Gregorian)."),
    ("Tir", 11, "Great Feast", "Feast of the Epiphany / Theophany (Timket)", "Timket",
     "Ethiopian Epiphany (Timket), the most spectacular Ethiopian feast. Celebrates the Baptism "
     "of Christ in the Jordan."),
    ("Megabit", 21, "Great Feast", "Feast of the Annunciation (Lidata le-Mariam)", "Annunciation",
     "The Annunciation of the Archangel Gabriel to the Virgin Mary."),
    ("Hamle", 13, "Great Feast", "Feast of the Transfiguration (Buhe)", "Transfiguration",
     "The Transfiguration of Our Lord, celebrated as Buhe in Ethiopia. Children sing "
     "songs and carry torches the eve before."),
    ("Meskerem", 17, "Great Feast", "Finding of the True Cross (Meskel)", "Meskel",
     "Meskel celebrates the finding of the True Cross by Empress Helena. Enormous bonfires "
     "(Demera) are lit throughout Ethiopia the eve of Meskel."),
    ("Tahsas", 8, "Feast", "Feast of the Conception of Our Lady (Lideta le-Mariam)", "Lideta",
     "Feast of the Conception of the Blessed Virgin Mary."),

    # ── Feasts of the Blessed Virgin Mary ────────────────────────────────────
    ("Hidar", 21, "Great Feast", "Feast of Our Lady of Zion (Hidar Tsion)", "Lady of Zion",
     "The most important Marian feast in Ethiopia, celebrating Our Lady of Zion at Axum. "
     "A tabot (ark) replica is paraded through the streets."),
    ("Nehase", 16, "Great Feast", "Feast of the Assumption of the Blessed Virgin Mary", "Assumption",
     "Ethiopian celebration of the Dormition and Assumption of the Virgin Mary."),
    ("Ginbot", 21, "Feast", "Monthly Feast of St. Mary (Ginbot)", "St. Mary",
     "Monthly commemoration of the Blessed Virgin Mary (21st of Ginbot = June 1 Gregorian)."),
    ("Yekatit", 16, "Feast", "Feast of the Presentation of Our Lord (Timkat Mariam)", "Presentation",
     "The Presentation of the Child Jesus in the Temple."),

    # ── St. Michael the Archangel ─────────────────────────────────────────────
    ("Tir", 12, "Feast", "Monthly Feast of St. Michael the Archangel", "St. Michael",
     "St. Michael is commemorated on the 12th of every Ethiopian month. "
     "The Tir (January) feast is the principal annual commemoration."),
    ("Hidar", 12, "Feast", "Feast of the Consecration of St. Michael's Church", "St. Michael (Hidar)",
     "Annual feast of St. Michael celebrated in Hidar (November)."),

    # ── St. Gabriel the Archangel ─────────────────────────────────────────────
    ("Hidar", 22, "Feast", "Feast of St. Gabriel the Archangel (Hidar)", "St. Gabriel",
     "St. Gabriel is commemorated on the 22nd of each Ethiopian month. "
     "The Hidar 22 feast is his principal annual celebration."),

    # ── The Nine Saints (Tsatew Qiddusan) ────────────────────────────────────
    ("Hamle", 17, "Saints", "The Nine Saints (Tsatew Qiddusan), Missionaries to Ethiopia", "The Nine Saints",
     "The Nine Saints (5th century) were missionaries from Syria, Constantinople, and Rome "
     "who came to Ethiopia after the Council of Chalcedon. They founded monasteries and "
     "translated the Bible into Ge'ez."),

    # ── Major Ethiopian Saints ────────────────────────────────────────────────
    ("Ginbot", 11, "Saint", "Saint Yared the Hymnographer, Father of Ethiopian Sacred Music",
     "St. Yared",
     "Saint Yared (505–571 AD) composed the three modes of Ethiopian liturgical chant: "
     "Ge'ez (joyful), Ezel (mourning), and Araray (ordinary time). Tradition says three birds "
     "from Paradise taught him the divine melodies. His work is still used unchanged today."),
    ("Nehase", 24, "Venerable", "Saint Tekle Haymanot of Debre Libanos, Pillar of Ethiopian Monasticism",
     "St. Tekle Haymanot",
     "The greatest Ethiopian saint, Abba Tekle Haymanot (c. 1215–1313) founded Ethiopian "
     "monasticism at Debre Asbo (Debre Libanos). He is depicted with one leg and six wings, "
     "symbolizing that he stood in prayer for 22 years, one leg falling off after 7 years."),
    ("Sene", 12, "Righteous", "Saint Lalibela, Righteous King and Builder of the Rock-Hewn Churches",
     "St. Lalibela",
     "King Lalibela (c. 1181–1221) commissioned eleven rock-hewn monolithic churches in Roha "
     "(now Lalibela), a UNESCO World Heritage Site. He intended the site as a New Jerusalem "
     "for Ethiopian Christians who could not travel to the Holy Land."),
    ("Megabit", 9, "Saint", "Saint Gebre Menfes Qiddus (Abbo), the Hermit Saint of Ethiopia",
     "St. Gebre Menfes Qiddus",
     "Known as Abbo, Gebre Menfes Qiddus (14th century) is one of the most beloved Ethiopian "
     "saints. He lived as an ascetic in the wilderness, sharing food with wild animals. "
     "He is depicted surrounded by lions and leopards."),
    ("Sene", 5, "Saint", "Saint Samuel of Waldebba, Founder of Waldebba Monastery",
     "St. Samuel of Waldebba",
     "Samuel of Waldebba (14th century) founded the famous Waldebba Monastery in northern "
     "Ethiopia. Known for his strict ascetic life and miraculous healings."),
    ("Tir", 4, "Hierarch", "Saint Frumentius (Abba Salama), Apostle to Ethiopia",
     "St. Frumentius",
     "Frumentius (c. 300–360 AD) was the first bishop of Axum and the Apostle of Ethiopia. "
     "A Syrian Christian from Tyre, he converted King Ezana and established Christianity "
     "in Ethiopia. He was consecrated by St. Athanasius of Alexandria."),
    ("Meskerem", 30, "Saint", "Saint Ewostatewos (Eustathius) of Ethiopia, Monastic Reformer",
     "St. Ewostatewos",
     "Ewostatewos (c. 1273–1352) was an Ethiopian monk who insisted on Sabbath observance "
     "and reformed Ethiopian monasticism. He spent his last years in exile in Egypt and Armenia. "
     "The Ewostathian monastic movement shaped Ethiopian Christianity."),
    ("Tikimt", 26, "Saint", "Saint Zara Yaqob (Emperor Zara Yaqob), Defender of the Faith",
     "Emperor Zara Yaqob",
     "Emperor Zara Yaqob (r. 1434–1468) defended Ethiopian Christianity, commissioned "
     "theological writings, and standardized the Ethiopian church calendar. He enforced "
     "strict observance of Marian feasts and church reforms."),
    ("Yekatit", 7, "Martyrs", "Holy Martyrs of Debre Damo Monastery",
     "Martyrs of Debre Damo",
     "The monks of Debre Damo monastery who were martyred during the invasion of "
     "Ahmad ibn Ibrahim al-Ghazi (Gragn) in the 16th century."),
    ("Miyazya", 27, "Saint", "Saint Abba Guba, Desert Father of the Scetis (Ethiopia)",
     "St. Abba Guba",
     "One of the Desert Fathers venerated in the Ethiopian church."),
    ("Hamle", 1, "Saint", "Saint Abba Libanos, One of the Nine Saints",
     "St. Abba Libanos",
     "Abba Libanos is one of the Nine Saints who came from Rome to Ethiopia in the 5th century. "
     "He founded Debre Libanos in Tigray (distinct from Debre Libanos of Tekle Haymanot)."),
    ("Hidar", 1, "Feast", "Feast of the Holy Covenant (Kidana Mehret) of Our Lady",
     "Kidana Mehret",
     "The Covenant of Mercy — Our Lady's promise to intercede for Ethiopia. "
     "One of the most celebrated Marian feasts in the Ethiopian church."),
    ("Tahsas", 5, "Martyrs", "The Holy Martyrs of Nagran (Arabia Felix)",
     "Martyrs of Nagran",
     "Christians of Nagran (Yemen) martyred by the Jewish-Yemenite king Dhu Nuwas "
     "in 523 AD for refusing to apostatize. Ethiopia's Emperor Kaleb later invaded "
     "Yemen to avenge them. Commemorated in the Ethiopian synaxarium."),
    ("Tikimt", 3, "Saint", "Saint Abba Gerima (Isaac), One of the Nine Saints",
     "St. Abba Gerima",
     "Abba Gerima (Isaac) was one of the Nine Saints from Rome. He founded Debre Gerima "
     "monastery in Tigray, one of the oldest monasteries in Ethiopia."),
    ("Megabit", 15, "Venerable", "Saint Abba Betre Mariam of Lake Tana",
     "St. Abba Betre Mariam",
     "Abba Betre Mariam is a venerated Ethiopian monastic saint associated with the "
     "monasteries of Lake Tana."),
    ("Sene", 24, "Saint", "Saint Abba Yohannes of Debre Bizen Monastery",
     "St. Abba Yohannes",
     "Abba Yohannes founded Debre Bizen monastery in Eritrea in the 14th century. "
     "It remains one of the most important monasteries of the Ethiopian Orthodox Church."),
    ("Hamle", 25, "Martyrs", "Holy Seven Sleepers of Ephesus",
     "Seven Sleepers",
     "The Seven Sleepers (Seba Wedikat) are commemorated in the Ethiopian synaxarium. "
     "Seven young men who fled Decius's persecution and miraculously slept 300 years "
     "in a cave near Ephesus."),
    ("Nehase", 1, "Saint", "Saint Abba Libanos the Younger of Debre Libanos",
     "St. Abba Libanos (Younger)",
     "A later saint of Debre Libanos monastery, venerated for his holiness."),
    ("Pagume", 5, "Feast", "Feast of John the Baptist (Ye-Yohannes Lidat)", "St. John the Baptist",
     "Ethiopian celebration of the birth of St. John the Baptist in Pagume (the 13th short month)."),

    # ── Apostles and Early Martyrs ─────────────────────────────────────────────
    ("Miyazya", 14, "Apostle", "Feast of the Holy Apostles Philip and James the Less",
     "Apostles Philip and James",
     "Ethiopian commemoration of the Holy Apostles Philip and James (the Less)."),
    ("Sene", 29, "Apostles", "Feast of the Holy Apostles Peter and Paul",
     "Apostles Peter and Paul",
     "Ethiopian commemoration of the Holy Apostles Peter and Paul, martyred in Rome."),
    ("Hamle", 12, "Apostle", "Feast of the Apostle Thomas",
     "Apostle Thomas",
     "Ethiopian commemoration of St. Thomas the Apostle who brought Christianity to India."),
    ("Nehase", 9, "Hierarch", "Saint Athanasius of Alexandria, Defender of Orthodoxy",
     "St. Athanasius",
     "St. Athanasius the Great (296–373), Archbishop of Alexandria, defended the "
     "Nicene Creed against Arianism. As Patriarch of Alexandria he consecrated "
     "Frumentius as the first Bishop of Ethiopia."),
    ("Tir", 22, "Hierarch", "Saint Cyril of Alexandria, Pillar of the Faith",
     "St. Cyril of Alexandria",
     "St. Cyril of Alexandria (376–444) defended the title Theotokos (God-bearer) for the "
     "Virgin Mary at the Council of Ephesus (431). Venerated by the Ethiopian church as "
     "Pillar of the Faith."),
    ("Tikimt", 13, "Hierarch", "Saint Dioscorus of Alexandria, Fifth Pope of Alexandria",
     "St. Dioscorus",
     "Dioscorus I was the fifth Pope of Alexandria (444–451) who upheld Cyril's theology "
     "at the Council of Chalcedon but was deposed and exiled by the Chalcedonian majority. "
     "Venerated as a saint by the Oriental Orthodox churches."),
]


def build_curated() -> list[dict]:
    entries: list[dict] = []

    for eth_month, eth_day, feast_type, title, short_name, notes in _CURATED:
        try:
            md = eth_to_gregorian_md(eth_month, eth_day)
        except ValueError as e:
            print(f"  Warning: {e}", file=sys.stderr)
            continue

        saint = {
            "name": short_name,
            "title": title,
            "feast_type": feast_type,
            "hagiography_url": None,
            "notes": notes if notes else None,
            "canonized_by": "Ethiopian Orthodox Tewahedo Church",
            "canonization_scope": "oriental",
            "year_canonized": None,
        }
        entries.append({
            "month_day": md,
            "eth_date": f"{eth_month} {eth_day}",
            "saint": saint,
        })
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Ethiopian Orthodox saints")
    parser.add_argument(
        "--out",
        default="backend/app/data/traditions/ethiopian_saints.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Only scrape official site, skip curated list",
    )
    parser.add_argument(
        "--curated-only",
        action="store_true",
        help="Only use curated list, skip web scraping",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    by_month_day: dict[str, list] = {}

    # 1. Curated synaxarium
    if not args.scrape_only:
        print("Building curated Ethiopian saints...", file=sys.stderr)
        curated = build_curated()
        for entry in curated:
            md = entry["month_day"]
            by_month_day.setdefault(md, []).append(entry["saint"])
        print(f"  {len(curated)} curated entries", file=sys.stderr)

    # 2. Official site scrape (supplements curated list)
    if not args.curated_only:
        print("Scraping ethiopianorthodox.org...", file=sys.stderr)
        scraped = scrape_official_site()
        for entry in scraped:
            md = entry["month_day"]
            name = entry["name"]
            # Avoid duplicating entries already in curated list
            existing_titles = {s["title"].lower() for s in by_month_day.get(md, [])}
            if name.lower() in existing_titles:
                continue
            saint = {
                "name": name,
                "title": name,
                "feast_type": "Feast",
                "hagiography_url": None,
                "notes": f"Ethiopian calendar: {entry['eth_date']}",
                "canonized_by": "Ethiopian Orthodox Tewahedo Church",
                "canonization_scope": "oriental",
                "year_canonized": None,
            }
            by_month_day.setdefault(md, []).append(saint)
        print(f"  {len(scraped)} scraped entries (after dedup with curated)", file=sys.stderr)

    output = []
    for month_day in sorted(by_month_day):
        output.append({
            "month_day": month_day,
            "tradition": "ethiopian",
            "calendar": "gregorian",
            "saints": by_month_day[month_day],
        })

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    print(f"\nWrote {len(output)} entries ({total} saints/feasts) to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
