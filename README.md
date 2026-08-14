# umkm_omni_web

FastAPI + SQLite + Jinja2 rebuild of the Order Inbox demo. This repository
runs as a single process with no external database or worker processes, so
it is easy to run locally on Ubuntu, Windows, and macOS.

## Prerequisites

- Python 3.11 installed
- `pip` available
- `git` installed if cloning the repo
- Run commands from the `umkm_omni_web` folder

## Install dependencies

From the `umkm_omni_web` folder:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> On Linux/macOS, if `python` points to Python 2, use `python3` instead.

## Run the app locally

From the `umkm_omni_web` folder:

```bash
uvicorn app.main:app --reload
```

Then open:

- http://localhost:8000/order_inbox

The app auto-seeds mock orders on first startup. Use **Sync Mock Orders** to
fetch more sample data.

## Ubuntu

1. Open a terminal.
2. Install Python 3.11 if not already installed.
3. Change to the project folder:

```bash
cd /path/to/umkm-apps/umkm_omni_web
```

4. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

5. Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

6. Start the server:

```bash
uvicorn app.main:app --reload
```

## Windows

1. Open PowerShell.
2. Change to the project folder:

```powershell
cd C:\Users\srama\Claude\Projects\umkm-apps\umkm_omni_web
```

3. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\venv\Scripts\activate
```

4. Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

5. Start the server:

```powershell
uvicorn app.main:app --reload
```

6. Migrasi data:
rm data/umkm_omni.db      # atau: del data\umkm_omni.db di Windows
uvicorn app.main:app --reload

## macOS

1. Open Terminal.
2. Change to the project folder:

```bash
cd /path/to/umkm-apps/umkm_omni_web
```

3. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

4. Install dependencies:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

5. Start the server:

```bash
uvicorn app.main:app --reload
```

## Docker (alternative)

If you prefer Docker, build and run from the `umkm_omni_web` folder:

```bash
docker compose up --build
```

## Notes

- By default the app uses SQLite and stores data in `app/data`.
- If `SESSION_SECRET_KEY` is not set, the app uses a demo secret key.
- The app listens on port `8000` by default.
