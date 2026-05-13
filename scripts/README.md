# Data Import Scripts

## import_orthocal.py — Byzantine traditions (Julian + Revised)

Fetches all 366 days of saint data from orthocal.info.

```bash
# Byzantine Julian (Serbian, Russian, Jerusalem, Georgian)
python3 scripts/import_orthocal.py \
    --calendar julian \
    --data-key oca \
    --out backend/app/data/oca_julian.json

# Byzantine Revised (Greek, Bulgarian, Romanian, Antioch, Alexandria)
python3 scripts/import_orthocal.py \
    --calendar revised \
    --data-key oca \
    --out backend/app/data/oca_revised.json
```

The `revised` option calls orthocal.info's `gregorian` endpoint because that is
how the source exposes New Calendar fixed feasts, but generated entries are
written with `"calendar": "revised"` to match the app's data model.

The resulting files can be used directly or as base datasets. Tradition-specific overlays go in `backend/app/data/traditions/`.

## Tradition-specific overlays

Place JSON files in `backend/app/data/traditions/`. Any `*.json` file in that directory is auto-loaded. Format matches `saints_sample.json`.

## Sources by tradition

| Tradition | Calendar | Primary Source |
|-----------|----------|----------------|
| Serbian, Russian, Jerusalem, Georgian | Julian | orthocal.info/api/julian/ |
| Greek, Bulgarian, Romanian, Antioch, Alexandria | Revised | orthocal.info/api/gregorian/ |
| Coptic/Oriental | Coptic ≈ Julian | st-takla.org/Synaxarium/ |
| Armenian Apostolic | Julian | armenianchurch.us |
| Ethiopian Tewahedo | Ethiopian ≈ Julian | Ethiopian Synaxarium (Geez) |

## Adding tradition-specific saints

Edit the appropriate file in `backend/app/data/traditions/`. Fields:
- `canonized_by`: Full name of canonizing church
- `canonization_scope`: `"universal"` | `"pan-orthodox"` | `"local"` | `"oriental"`
- `year_canonized`: Year of formal canonization
