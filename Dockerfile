FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docs ./docs
COPY alembic.ini .

# SQLite file lives here — mount a Railway volume at this path if you want
# data to survive redeploys; otherwise the app auto-reseeds mock data on
# startup, which is fine for a demo.
RUN mkdir -p /app/data
ENV DATA_DIR=/app/data

# Railway injects $PORT at runtime; default 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Postgres (Customer Request 2 Epic N): run pending Alembic migrations
# before uvicorn starts, so the app never boots against an un-migrated
# schema. SQLite (Railway's current default, DATABASE_URL unset or
# "sqlite://...") skips Alembic entirely and keeps booting straight to
# uvicorn — its schema is handled by app/main.py's lifespan instead (see
# app/database.py's run_lightweight_migrations comment). Running `alembic
# upgrade head` unconditionally here would break existing SQLite
# deployments: their tables were created by create_all(), not Alembic, so
# there is no alembic_version history for Alembic to reconcile against.
CMD ["sh", "-c", "case \"$DATABASE_URL\" in ''|sqlite*) exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} ;; *) alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} ;; esac"]
