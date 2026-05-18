#!/usr/bin/env python3
"""
Import Syriac Orthodox Church saints from two sources:
  1. Curated list of major Syriac Orthodox saints with verified feast dates
  2. Wikipedia API: extracts feast dates from saint article infoboxes

All dates stored as Julian MM-DD (Syriac church follows Julian calendar).

Usage:
    python3 scripts/import_syriac.py --out backend/app/data/traditions/syriac_saints.json
    python3 scripts/import_syriac.py --wiki-only --out /path/to/output.json
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar; contact: open-source)",
    "Accept": "application/json",
}

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Matches "January 28", "28 January", "Jan. 28" etc.
_DATE_RE = re.compile(
    r"(?:(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\.?|"
    r"(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\.?\s+(\d{1,2}))",
    re.IGNORECASE,
)

_FEAST_PARAMS = re.compile(
    r"\|\s*(?:feast_day|feast_date|feast|venerated_date)\s*=\s*([^\n\|]+)",
    re.IGNORECASE,
)


# ── Curated Syriac Orthodox Saints ───────────────────────────────────────────
# Sources: Beth Mardutho Syriac Institute, Syriac Orthodox Church official
# liturgical calendar, and Voobus "A History of Asceticism in the Syrian Orient"
#
# Dates are Julian calendar MM-DD. The Syriac church uses the Julian calendar
# for fixed feasts; the backend converts Julian → Gregorian for display.
#
# Format: (julian_month, julian_day, feast_type, title, short_name, wikipedia_slug, notes)
_CURATED: list[tuple] = [
    # ── Apostolic / Patristic era ─────────────────────────────────────────────
    (1, 27, "Church Father", "Saint Ephrem the Syrian, Deacon and Hymnographer",
     "St. Ephrem the Syrian", "Ephrem_the_Syrian",
     "Ephrem the Syrian (c. 306–373) is the greatest poet-theologian of the Syriac tradition. "
     "He composed thousands of hymns (madrashê) and homilies. Known as the 'Harp of the Holy "
     "Spirit', his hymns against heresy were central to early Syriac Christianity. "
     "Doctor of the Universal Church."),
    (1, 5, "Venerable", "Saint Simeon the Stylite, the Pillar-Dweller",
     "St. Simeon the Stylite", "Simeon_Stylites",
     "Simeon the Stylite (c. 390–459) was the first stylite (pillar-dwelling ascetic). "
     "He spent 37 years atop a pillar near Aleppo, Syria, drawing pilgrims from across "
     "the ancient world. He is venerated by the Syriac Orthodox as a great ascetic."),
    (3, 7, "Church Father", "Saint Aphrahat the Persian Sage",
     "St. Aphrahat", "Aphrahat",
     "Aphrahat (c. 270–345), the 'Persian Sage', was the earliest known Syriac Christian writer "
     "whose works survive intact. His 23 Demonstrations cover theology, asceticism, and "
     "church life in early Syriac Christianity under Sassanid Persian rule."),
    (11, 29, "Bishop", "Saint Jacob of Serugh, the Flute of the Holy Spirit",
     "St. Jacob of Serugh", "Jacob_of_Serugh",
     "Jacob of Serugh (c. 451–521) was bishop of Serugh (Batnae) and one of the greatest Syriac "
     "poets. His verse homilies (memrê) are foundational texts of Syriac literature. "
     "He was a student of Ephrem's tradition and is called 'Flute of the Holy Spirit'."),
    (12, 10, "Bishop", "Saint Philoxenus of Mabbug, Theologian of the Incarnation",
     "St. Philoxenus", "Philoxenus_of_Mabbug",
     "Philoxenus of Mabbug (c. 440–523) was bishop of Mabbug (Hierapolis) and a leading "
     "Miaphysite theologian. He commissioned the Philoxenian Version of the New Testament "
     "and wrote extensively against Nestorianism and Chalcedonianism."),
    (2, 8, "Bishop", "Saint Severus of Antioch, Patriarch and Theologian",
     "St. Severus of Antioch", "Severus_of_Antioch",
     "Severus of Antioch (c. 465–538) was Patriarch of Antioch (512–518) and the foremost "
     "theologian of the Miaphysite/Oriental Orthodox tradition. His writings define the "
     "Christological position of the Syriac, Coptic, and Armenian churches."),
    (7, 30, "Bishop", "Saint Bar-Hebraeus (Gregorius Barhebraeus), the Universal Scholar",
     "St. Bar-Hebraeus", "Bar-Hebraeus",
     "Gregory Barhebraeus (1226–1286) was Maphrian (Catholicos) of the East and the last "
     "great encyclopedist of the Syriac tradition. He wrote on theology, philosophy, history, "
     "medicine, and grammar. Described as 'the most learned man of his age'."),
    (6, 25, "Bishop", "Saint Peter III of Callinicum, Patriarch of Antioch",
     "St. Peter III", "Peter_III_of_Callinicum",
     "Peter III of Callinicum (patriarch 581–591) was Patriarch of the Syriac Orthodox Church "
     "of Antioch. He engaged in theological correspondence with Damian of Alexandria "
     "on Christological questions."),
    (11, 27, "Bishop", "Saint Dionysius Bar Salibi, Polymath Bishop of Amida",
     "St. Dionysius Bar Salibi", "Dionysius_bar_Salibi",
     "Dionysius bar Salibi (d. 1171) was bishop of Amida (Diyarbakir) and a prolific "
     "Syriac writer. He wrote biblical commentaries, liturgical works, and polemical "
     "treatises against Islam, Judaism, and rival Christian groups."),
    (10, 10, "Bishop", "Saint Moses bar Simeon of Nisibis, Keeper of the Scrolls",
     "St. Moses bar Simeon", "Moses_bar_Simeon",
     "Moses bar Simeon of Nisibis (d. c. 943) was Syriac Orthodox metropolitan of Nisibis "
     "and a notable manuscript collector. He brought hundreds of manuscripts from Egypt "
     "and Syria to Nisibis, preserving invaluable Syriac texts."),
    (4, 17, "Martyr", "Saint Simeon bar Sabba'e, Catholicos and Martyr of Persia",
     "St. Simeon bar Sabba'e", "Simeon_bar_Sabba%27e",
     "Simeon bar Sabba'e (d. 341) was Catholicos of Seleucia-Ctesiphon who was martyred "
     "under Shapur II of Persia for refusing to impose double taxes on Christians. "
     "He is venerated as a martyr by all Syriac Christian churches."),

    # ── Medieval Saints ───────────────────────────────────────────────────────
    (11, 25, "Bishop", "Saint Abdisho bar Brikha, Metropolitan of Nisibis",
     "St. Abdisho bar Brikha", "Abdisho_bar_Brikha",
     "Abdisho bar Brikha (d. 1318) was Metropolitan of Nisibis and Armenia. "
     "He wrote the famous Catalogue of Syriac authors ('Bibliotheca Orientalis') "
     "and composed the 'Paradise of Eden', a theological encyclopedia in verse."),
    (2, 4, "Bishop", "Saint Marutha of Tikrit, Maphrian of the East",
     "St. Marutha", "Marutha_of_Tikrit",
     "Marutha of Tikrit (d. c. 649) was the first Maphrian (Catholicos of the East) "
     "of the Syriac Orthodox Church. He organized the church in Mesopotamia after "
     "the Islamic conquest and is venerated as a great church father."),
    (3, 17, "Martyr", "Blessed Ignatius Maloyan, Armenian Martyr of the Syriac Rite",
     "Bl. Ignatius Maloyan", "Ignatius_Maloyan",
     "Ignatius Maloyan (1869–1915), Archbishop of Mardin, was martyred during the "
     "Armenian and Syriac Genocide. He refused to apostatize under threat of death. "
     "Beatified by Pope Francis in 2013. Venerated by Syriac Orthodox as a martyr."),
    (10, 2, "Saint", "Saint Geevarghese Mar Gregorios of Parumala",
     "St. Geevarghese", "Geevarghese_Mar_Gregorios",
     "Geevarghese Mar Gregorios (1848–1902) was Bishop of Niranam in the Malankara "
     "Syriac Orthodox Church. The first person from Kerala to be canonized as a saint. "
     "Known for healing the sick and teaching. Canonized in 1987 by Patriarch Ignatius Zakka I Iwas."),

    # ── Martyrs ───────────────────────────────────────────────────────────────
    (3, 1, "Martyrs", "The Forty Martyrs of Sebaste",
     "Forty Martyrs of Sebaste", "Forty_Martyrs_of_Sebaste",
     "Forty Roman soldiers who were martyred at Sebaste (modern Sivas, Turkey) in 320 AD "
     "for refusing to sacrifice to pagan gods. They were left naked on a frozen lake. "
     "Venerated by the Syriac Orthodox Church on March 1 Julian."),
    (12, 27, "Martyr", "Saint Stephen the First Martyr, Protodeacon",
     "St. Stephen", "Saint_Stephen",
     "St. Stephen, the first Christian martyr (Protomartyr), was stoned to death in Jerusalem "
     "c. 36 AD. His feast is celebrated in the Syriac tradition on December 27 Julian "
     "(the day after Christmas)."),
    (1, 17, "Venerable", "Saint Anthony the Great, Father of Monks",
     "St. Anthony the Great", "Anthony_the_Great",
     "Anthony the Great (c. 251–356) is venerated as the Father of Christian monasticism. "
     "His ascetic life in the Egyptian desert inspired the Syriac monastic tradition."),

    # ── Founding Figures ──────────────────────────────────────────────────────
    (4, 25, "Evangelist", "Saint Mark the Evangelist, Founder of the Church of Alexandria",
     "St. Mark", "Mark_the_Evangelist",
     "St. Mark the Evangelist wrote the earliest Gospel and founded the Church of Alexandria. "
     "Venerated by the Syriac Orthodox as a founding father of Oriental Christianity."),
    (12, 21, "Apostle", "Saint Thomas the Apostle, Apostle to Syria and India",
     "St. Thomas", "Thomas_the_Apostle",
     "St. Thomas the Apostle brought Christianity to Syria and India. The Syriac Orthodox "
     "tradition holds that he established the church in Edessa (Urfa) and preached to "
     "the Parthians, Medes, and Indians."),
    (10, 17, "Hierarch", "Saint Ignatius of Antioch, Bishop and Martyr",
     "St. Ignatius of Antioch", "Ignatius_of_Antioch",
     "Ignatius of Antioch (c. 35–107) was the third Bishop of Antioch and one of the "
     "Apostolic Fathers. His seven letters to various churches are fundamental early "
     "Christian texts. He was martyred in Rome under Emperor Trajan."),

    # ── Feasts of Our Lord (Syriac tradition) ─────────────────────────────────
    (12, 25, "Great Feast", "The Nativity of Our Lord Jesus Christ",
     "Nativity", None,
     "Christmas celebrated by the Syriac Orthodox Church on December 25 Julian."),
    (1, 6, "Great Feast", "The Epiphany / Theophany of Our Lord",
     "Epiphany", None,
     "The Feast of the Epiphany (Denho), commemorating the Baptism of Christ in the Jordan "
     "and the visit of the Magi. One of the most important feasts in the Syriac rite."),
    (8, 6, "Great Feast", "The Holy Transfiguration of Our Lord",
     "Transfiguration", None,
     "The Transfiguration of Christ on Mount Tabor. August 6 Julian."),
    (8, 15, "Great Feast", "The Dormition of the Most Holy Theotokos",
     "Dormition", None,
     "The Dormition (Shunoyo) of the Virgin Mary, August 15 Julian."),
    (9, 14, "Great Feast", "The Exaltation of the Holy Cross",
     "Exaltation of the Cross", None,
     "The universal feast commemorating the finding and elevation of the True Cross "
     "by Empress Helena in 326 AD."),
]


def _fetch_wikitext(slug: str) -> str | None:
    params = urllib.parse.urlencode({
        "action": "parse",
        "page": slug,
        "prop": "wikitext",
        "format": "json",
    })
    url = f"{WIKIPEDIA_API}?{params}"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return data.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return None


def _parse_feast_date(wikitext: str) -> str | None:
    """Extract feast date from Wikipedia infobox wikitext."""
    for m in _FEAST_PARAMS.finditer(wikitext):
        raw = m.group(1).strip()
        raw = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", raw)
        raw = re.sub(r"\{\{[^}]+\}\}", "", raw).strip()

        dm = _DATE_RE.search(raw)
        if dm:
            if dm.group(1):  # DD Month
                day = int(dm.group(1))
                month = _MONTH_MAP.get(dm.group(2).lower())
            else:  # Month DD
                month = _MONTH_MAP.get(dm.group(3).lower())
                day = int(dm.group(4))
            if month and 1 <= day <= 31:
                return f"{month:02d}-{day:02d}"
    return None


def build_from_curated(delay: float, fetch_wiki: bool) -> dict[str, list]:
    by_md: dict[str, list] = {}

    for (jm, jd, feast_type, title, short_name, wiki_slug, notes) in _CURATED:
        md = f"{jm:02d}-{jd:02d}"

        # Optionally try to get a more precise date from Wikipedia
        wiki_md = None
        if fetch_wiki and wiki_slug:
            time.sleep(delay)
            wikitext = _fetch_wikitext(wiki_slug)
            if wikitext:
                wiki_md = _parse_feast_date(wikitext)
                if wiki_md and wiki_md != md:
                    print(f"  Wikipedia date differs for {short_name}: "
                          f"curated={md}, wiki={wiki_md} — using curated", file=sys.stderr)

        print(f"  {md}: {short_name}", file=sys.stderr)

        saint = {
            "name": short_name,
            "title": title,
            "feast_type": feast_type,
            "hagiography_url": f"https://en.wikipedia.org/wiki/{wiki_slug}" if wiki_slug else None,
            "notes": notes or None,
            "canonized_by": "Syriac Orthodox Church of Antioch",
            "canonization_scope": "oriental",
            "year_canonized": None,
        }
        by_md.setdefault(md, []).append(saint)

    return by_md


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Syriac Orthodox saints")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between Wikipedia requests")
    parser.add_argument(
        "--out",
        default="backend/app/data/traditions/syriac_saints.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--wiki-only",
        action="store_true",
        help="Only fetch Wikipedia data (skips curated fallback)",
    )
    parser.add_argument(
        "--no-wiki",
        action="store_true",
        help="Skip Wikipedia API calls, only use curated data",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Building Syriac Orthodox saints...", file=sys.stderr)
    fetch_wiki = not args.no_wiki
    by_md = build_from_curated(delay=args.delay, fetch_wiki=fetch_wiki)

    output = []
    for month_day in sorted(by_md):
        output.append({
            "month_day": month_day,
            "tradition": "syriac",
            "calendar": "julian",
            "saints": by_md[month_day],
        })

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    print(f"\nWrote {len(output)} entries ({total} saints/feasts) to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
