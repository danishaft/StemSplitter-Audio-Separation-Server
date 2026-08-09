FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 postgresql-client tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system stemsplitter \
    && useradd --system --gid stemsplitter --home-dir /app stemsplitter

WORKDIR /app
COPY pyproject.toml requirements.lock README.md ./
RUN python -m pip install --require-hashes --no-deps -r requirements.lock

COPY scripts ./scripts
COPY splitter ./splitter

COPY audio_api.py ./
COPY migrations ./migrations
COPY models ./models
RUN mkdir -p /app/jobs /app/uploads \
    && chown -R stemsplitter:stemsplitter /app

USER stemsplitter
ENTRYPOINT ["/usr/bin/tini", "--"]


FROM runtime AS api

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/live', timeout=3)"]
CMD ["python", "-m", "scripts.run_api"]


FROM runtime AS queue-worker

CMD ["python", "-m", "scripts.run_rq_worker"]


FROM runtime AS maintenance-worker

CMD ["python", "-m", "scripts.run_maintenance_worker"]


FROM runtime AS migrate

CMD ["python", "-m", "scripts.apply_migrations"]
