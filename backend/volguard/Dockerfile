FROM python:3.11-slim

LABEL maintainer="Fintelligence"
LABEL description="Volguard Intelligence Edition — Options trading for Indian markets"
LABEL version="6.0.0"

# Build deps for numpy/scipy/arch (C extensions) + psycopg2 (PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY volguard_v6_final.py .
COPY seed_journal.py .
COPY subscriptions.py .
COPY push_notifications.py .
COPY auth_utils.py .
COPY db_utils.py .

RUN mkdir -p /app/logs

ENV LOG_FILE=/app/logs/volguard.log
ENV PORT=8000
ENV HOST=0.0.0.0
ENV TZ=Asia/Kolkata

RUN useradd -m -u 1000 volguard && chown -R volguard:volguard /app
USER volguard

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

CMD ["sh", "-c", "uvicorn volguard_v6_final:app --host ${HOST} --port ${PORT} --log-level info --workers 1"]
