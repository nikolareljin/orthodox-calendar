# Dev Workflows

## Prereqs
- Git submodule: `git submodule update --init --recursive` (for `script-helpers`).
- Host tooling: `python3`, `npm`, `docker` (for container workflows).

## Scripts (repo root)
- `./build` — install backend venv deps and build frontend bundle (host).
- `./run` — start backend (uvicorn) + frontend dev server (host); stops on Ctrl+C.
- `./start [-b]` — start Docker Compose stack (`-b` rebuilds images); `./stop` tears it down.

## Backend quick commands
```bash
cd orthodox-calendar/backend
source .venv/bin/activate  # after ./build
uvicorn app.main:app --reload
python3 -m py_compile $(find app -name '*.py')  # syntax check
```

## Frontend quick commands
```bash
cd orthodox-calendar/frontend
npm install
npm run dev
npm run build
```

## Data
- Place JSON files matching `app/data/saints_sample.json` under `backend/app/data/` or point `ORTHODOX_CALENDAR_DATA_PATH` to your dataset (multiple files are merged).

## Docker
- Compose file at repo root; backend on `:8000`, frontend on `:4173`, data bind-mounted from `backend/app/data`.
