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

## Deploy dengan Docker Compose + PostgreSQL (VPS)

`docker-compose.yml` di repo ini menjalankan dua service: `web` (aplikasi)
dan `db` (PostgreSQL, dengan volume persist). Ini setup yang dipakai untuk
deploy ke VPS sewaan — bukan pengganti jalur SQLite/Railway di atas,
melainkan opsi tambahan di sampingnya.

1. Salin `.env.example` ke `.env` di server VPS:

```bash
cp .env.example .env
```

2. Generate password Postgres yang kuat SEKALI, lalu isi `POSTGRES_PASSWORD`
   (dan `SESSION_SECRET_KEY`) di `.env` dengan hasilnya — jangan pernah
   pakai contoh seperti "postgres"/"password123":

```bash
openssl rand -base64 24
# atau kalau openssl tidak ada:
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

3. `.env` sudah masuk `.gitignore` — kredensial di dalamnya tidak pernah
   ter-commit ke git.

4. Build dan jalankan:

```bash
docker compose up --build
```

Saat container `web` start, migrasi skema dijalankan otomatis lewat
`alembic upgrade head` sebelum `uvicorn` start — tabel dibuat sesuai
`app/models/db_models.py` versi terbaru, database Postgres mulai kosong
(sesuai prinsip "start from zero" project ini) lalu terisi data referensi
(akun Superadmin, aturan mapping jurnal) lewat seed normal aplikasi.

5. Restart/redeploy tanpa `-v` (mis. `docker compose down && docker compose
   up`, atau `docker compose restart`) TIDAK menghapus data — volume
   `postgres-data` persist di luar siklus hidup container. Hanya
   `docker compose down -v` yang menghapusnya.

## Notes

- By default the app uses SQLite and stores data in `app/data`.
- If `SESSION_SECRET_KEY` is not set, the app uses a demo secret key.
- The app listens on port `8000` by default.
- Forgot-password emails are sent via a **Mailtrap sandbox** by default (see
  `.env.example`'s `SMTP_*` variables) — this is a testing sandbox, so reset
  links do NOT arrive in a real recipient's inbox, only in the Mailtrap web
  UI. This is intentional, not a bug. Point `SMTP_*` at a real provider
  before going live.
