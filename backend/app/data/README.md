# Data sources

- `saints_sample.json` is a small demo slice. To load a full Synaxarion/Octoechos dataset, drop one or more `.json` files in this directory or point `ORTHODOX_CALENDAR_DATA_PATH` to a directory/file containing entries that match the sample schema.
- Multiple files are merged; tradition strings must align with `app/config.py`.
- Movable feasts tied to Pascha should be precomputed to fixed calendar dates for each year or generated upstream before ingestion.
