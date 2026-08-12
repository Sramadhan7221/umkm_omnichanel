FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docs ./docs

# SQLite file lives here — mount a Railway volume at this path if you want
# data to survive redeploys; otherwise the app auto-reseeds mock data on
# startup, which is fine for a demo.
RUN mkdir -p /app/data
ENV DATA_DIR=/app/data

# Railway injects $PORT at runtime; default 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
