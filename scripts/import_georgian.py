#!/usr/bin/env python3
"""
Import Georgian Orthodox Church saints.

Sources:
  - Georgian Orthodox and Apostolic Church official calendar
  - Wikipedia: https://en.wikipedia.org/wiki/Category:Georgian_saints
  - Beth Mardutho & various Orthodox hagiographical sources

Georgian church uses the Julian calendar; feast dates are Julian MM-DD.
Leap year dates (Feb 29) stored as 02-29.

Usage:
    python3 scripts/import_georgian.py \
        --out backend/app/data/traditions/georgian_saints.json
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

WIKI_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {"User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"}

# (julian_month, julian_day, feast_type, name, hagiography_slug, notes)
_CURATED = [
    # Major Georgian feasts — confirmed Julian calendar dates
    (1, 14, "Equal-to-Apostles", "Saint Nino, Enlightener of Georgia",
     "Nino", "Apostle to Georgia (4th c.), converted King Mirian III and Queen Nana"),
    (1, 8, "Martyr", "Abo of Tiflis",
     "Abo_of_Tiflis", "Arab Christian martyr, patron saint of Tbilisi (786)"),
    (1, 26, "Righteous", "David the Builder, King of Georgia",
     "David_IV_of_Georgia", "King of Georgia (1073–1125), rebuilder of the Georgian church and state"),
    (5, 1, "Righteous", "Queen Tamar of Georgia",
     "Tamar_of_Georgia", "Queen of Georgia (1160–1213), canonized Equal-to-Apostles in some traditions"),
    (5, 7, "Venerable", "Ioane of Zedazeni",
     "John_of_Zedazeni", "Leader of the Thirteen Assyrian Fathers who Christianized Georgia (6th c.)"),
    (5, 9, "Venerable", "Shio of Mgvime",
     "Shio_of_Mgvime", "One of the Thirteen Assyrian Fathers, hermit monk (6th c.)"),
    (6, 7, "Venerable", "David Garejeli",
     "David_of_Gareji", "One of the Thirteen Assyrian Fathers, founded the Gareji monastery complex (6th c.)"),
    (6, 24, "Venerable", "Giorgi Mtacmideli (of the Holy Mountain)",
     "George_the_Hagiorite", "Georgian monk on Mount Athos, translated Georgian liturgical texts (1009–1065)"),
    (7, 17, "Venerable", "Nino of Cappadocia",
     "Nino", "Patron saint of Georgia — second feast day"),
    (9, 2, "Venerable", "Arsen Ikaltoeli",
     "Arsen_Ikaltoeli", "Georgian scholar-monk, founder of Ikalto Academy (12th c.)"),
    (10, 5, "Venerable", "Grigol Khandzteli",
     "Gregory_of_Khandzta", "Georgian monastic reformer, founded Khandzta monastery in Tao (759–861)"),
    (12, 5, "Venerable", "Saba Asveli",
     "Saba_Asveli", "Georgian holy bishop, one of the Thirteen Assyrian Fathers (6th c.)"),
    # Thirteen Assyrian (Syrian) Fathers — feast as a group
    (5, 7, "Venerable", "The Thirteen Assyrian Fathers",
     "Thirteen_Syrian_Fathers", "Thirteen monks from Syria/Mesopotamia who evangelized Georgia (6th c.)"),
    # Georgian Martyrs
    (8, 2, "Martyr", "Razhden the Protomartyr",
     "Razhden_the_Protomartyr", "First martyr of Georgia, a Persian prince converted to Christianity (457)"),
    (8, 7, "Martyr", "Queen Ketevan the Martyr",
     "Ketevan_the_Martyr", "Georgian queen martyred in Persia under Shah Abbas I (1624)"),
    (11, 13, "Martyr", "The 6000 Martyrs of Tbilisi",
     "Six_thousand_martyrs_of_Tbilisi", "Christians martyred by Shah Abbas I (1624)"),
    (10, 28, "Martyr", "Dimitri Tavdadebuli (Self-Sacrificer)",
     "Demetre_I_of_Georgia", "King Demetrius I of Georgia, sacrificed himself to save the people (1130–1156)"),
    # Georgian Monastics and Scholars
    (3, 20, "Venerable", "Ilarion the Georgian",
     "Hilarion_the_Georgian", "Georgian monk on Mount Olympus and Mount Athos (9th–10th c.)"),
    (6, 14, "Venerable", "Ekvtime the Enlightener",
     "Euthymius_the_Hagiorite", "Georgian monk of Mount Athos, translated Georgian Gospels (955–1028)"),
    (1, 20, "Hierarch", "Catholicos-Patriarch Kirion II",
     "Kirion_II", "Georgian Catholicos-Patriarch, martyred 1918"),
    (6, 28, "Venerable", "Gabriel Urgebadze",
     "Gabriel_Urgebadze", "Georgian hieromonk, fool-for-Christ, canonized 2012"),
    # Holy Icons and Feasts
    (8, 16, "Saint", "Feast of the Svetitskhoveli (Life-Giving Pillar)",
     "Mtskheta", "Commemoration of the robe of Christ kept in Mtskheta cathedral"),
    (10, 14, "Saint", "Feast of the Nikozi Icon of the Mother of God",
     "Nikozi", "Georgian diocesan feast of the miraculous Nikozi icon"),
    # New Martyrs
    (11, 7, "New Martyr", "New Martyrs of Georgia (Soviet Era)",
     "Georgian_New_Martyrs", "Georgian clergy and faithful martyred under Soviet persecution (1921–1953)"),
]


def _wiki_url(slug: str) -> str:
    return f"https://en.wikipedia.org/wiki/{urllib.parse.quote(slug)}"


def _fetch_wiki_feast(slug: str, delay: float = 0.5) -> str | None:
    """Try to find feast date from Wikipedia wikitext."""
    time.sleep(delay)
    try:
        params = {"action": "parse", "page": slug.replace("_", " "), "prop": "wikitext", "format": "json"}
        url = WIKI_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Georgian Orthodox saints")
    parser.add_argument("--out", default="backend/app/data/traditions/georgian_saints.json")
    parser.add_argument("--no-wiki", action="store_true", help="Skip Wikipedia URL fetching")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    by_md: dict[str, list] = {}

    for month, day, feast_type, name, wiki_slug, notes in _CURATED:
        md = f"{month:02d}-{day:02d}"
        hagio_url = _wiki_url(wiki_slug) if wiki_slug else None

        saint = {
            "name": name,
            "title": name,
            "feast_type": feast_type,
            "hagiography_url": hagio_url,
            "notes": notes,
            "canonized_by": "Georgian Orthodox and Apostolic Church",
            "canonization_scope": "local",
            "year_canonized": None,
        }
        by_md.setdefault(md, []).append(saint)
        print(f"  {md}: {name[:70]}", file=sys.stderr)

    # Also scrape Wikipedia category for additional saints
    if not args.no_wiki:
        print("\nFetching Wikipedia category: Royal saints from Georgia (country)...", file=sys.stderr)
        try:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": "Category:Royal saints from Georgia (country)",
                "cmtype": "page",
                "cmlimit": "500",
                "format": "json",
            }
            url = WIKI_API + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            titles = [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
            print(f"  Found {len(titles)} pages", file=sys.stderr)

            # Check which are already in curated list
            curated_names = {name.lower() for _, _, _, name, _, _ in _CURATED}

            _MONTH_MAP = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
            }
            _FEAST_PARAMS = re.compile(
                r"\|\s*(?:feast_day|feast_date|feast|venerated_date)\s*=\s*([^\n|}{]+)", re.IGNORECASE)
            _DATE_RE = re.compile(
                r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|"
                r"september|october|november|december)"
                r"|(january|february|march|april|may|june|july|august|"
                r"september|october|november|december)\s+(\d{1,2})",
                re.IGNORECASE,
            )

            for title in titles:
                if title.lower() in curated_names:
                    continue
                time.sleep(0.5)
                wikitext = _fetch_wiki_feast(title, delay=0) or ""
                if not wikitext:
                    continue
                md = None
                for m in _FEAST_PARAMS.finditer(wikitext):
                    raw = m.group(1).strip()
                    raw = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]|]+)\]\]", r"\1", raw)
                    raw = re.sub(r"\{\{[^}]+\}\}", "", raw).strip()
                    dm = _DATE_RE.search(raw)
                    if dm:
                        if dm.group(1):
                            d, mo = int(dm.group(1)), _MONTH_MAP.get(dm.group(2).lower())
                        else:
                            mo, d = _MONTH_MAP.get(dm.group(3).lower()), int(dm.group(4))
                        if mo and 1 <= d <= 31:
                            md = f"{mo:02d}-{d:02d}"
                            break
                if md:
                    slug = title.replace(" ", "_")
                    saint = {
                        "name": title,
                        "title": title,
                        "feast_type": "Righteous",
                        "hagiography_url": _wiki_url(slug),
                        "notes": None,
                        "canonized_by": "Georgian Orthodox and Apostolic Church",
                        "canonization_scope": "local",
                        "year_canonized": None,
                    }
                    by_md.setdefault(md, []).append(saint)
                    print(f"  {md}: {title[:70]} [wiki]", file=sys.stderr)
                else:
                    print(f"  SKIP (no feast date): {title}", file=sys.stderr)
        except Exception as exc:
            print(f"  WARNING: category fetch failed: {exc}", file=sys.stderr)

    output = [
        {
            "month_day": md,
            "tradition": "georgian",
            "calendar": "julian",
            "saints": saints_list,
        }
        for md, saints_list in sorted(by_md.items())
    ]

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    print(f"\nWrote {len(output)} entries ({total} saints) to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
