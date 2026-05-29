#!/usr/bin/env python3
"""
sync-neobyzantine.py — Update neobyzantine_hagiographies.json with actor slugs and URLs
exported from neobyzantine-org via `php artisan game:export`.

Usage:
    python scripts/sync-neobyzantine.py --input /path/to/saints-links.json [--dry-run]

Workflow:
  1. neobyzantine-org: php artisan game:export  → exports/saints-links.json
  2. Copy saints-links.json here (or pass path with --input)
  3. Run this script → updates backend/app/data/neobyzantine_hagiographies.json
  4. Commit the updated hagiographies JSON in a PR
"""

import argparse
import json
import sys
from pathlib import Path

HAGIO_PATH = Path(__file__).parent.parent / 'backend' / 'app' / 'data' / 'neobyzantine_hagiographies.json'


def load_json(path: Path) -> dict | list:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path: Path, data: list) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def normalize_name(name: str) -> str:
    """Simple normalization for matching saint names across sources."""
    return name.lower().strip().replace('  ', ' ')


def build_links_index(links: list[dict]) -> dict[str, dict]:
    """Build a name → link dict from saints-links.json entries."""
    index: dict[str, dict] = {}
    for link in links:
        key = normalize_name(link.get('actor_name', ''))
        if key:
            index[key] = link
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description='Sync neobyzantine.org actor links into hagiographies JSON.')
    parser.add_argument('--input', required=True, help='Path to saints-links.json exported from neobyzantine-org')
    parser.add_argument('--dry-run', action='store_true', help='Print changes without writing')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'ERROR: Input file not found: {input_path}', file=sys.stderr)
        sys.exit(1)

    saints_links_raw = load_json(input_path)
    if isinstance(saints_links_raw, dict):
        links = saints_links_raw.get('links', [])
    else:
        links = saints_links_raw

    links_index = build_links_index(links)
    print(f'Loaded {len(links_index)} actor-saint links from {input_path.name}')

    hagio_data = load_json(HAGIO_PATH)
    if not isinstance(hagio_data, list):
        print(f'ERROR: {HAGIO_PATH} is not a JSON array', file=sys.stderr)
        sys.exit(1)

    updated_count = 0

    for entry in hagio_data:
        for saint in entry.get('saints', []):
            name_key = normalize_name(saint.get('name', ''))
            match = links_index.get(name_key)
            if not match:
                continue

            changed = False
            nb_url = match.get('neobyzantine_url')
            nb_slug = match.get('actor_slug')

            if nb_url and saint.get('neobyzantine_url') != nb_url:
                saint['neobyzantine_url'] = nb_url
                changed = True
            if nb_slug and saint.get('neobyzantine_actor_slug') != nb_slug:
                saint['neobyzantine_actor_slug'] = nb_slug
                changed = True

            if changed:
                updated_count += 1
                print(f'  ✓ {saint["name"]} → {nb_url}')

    print(f'\n{updated_count} saint(s) updated.')

    if args.dry_run:
        print('(dry run — no file written)')
        return

    save_json(HAGIO_PATH, hagio_data)
    print(f'Written: {HAGIO_PATH}')


if __name__ == '__main__':
    main()
