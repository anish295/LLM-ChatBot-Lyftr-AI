# syntax=docker/dockerfile:1.7
# ---------- builder: resolve and install dependencies into a venv ----------
FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
# pip/setuptools/wheel are build-time only, so they are removed from the venv the runtime copies.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt \
 && (/opt/venv/bin/python -m pip uninstall -y -q pip setuptools wheel || true) \
 && find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} + \
 && find /opt/venv -type d -name "tests" -path "*site-packages/*" -prune -exec rm -rf {} +

# ---------- runtime: slim image, non-root, only the venv + app code ----------
FROM python:3.11-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DATABASE_URL=sqlite:////data/app.db \
    CACHE_DIR=/data/llm_cache \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    LITELLM_LOG=ERROR
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data/llm_cache \
 && chown -R app:app /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app app ./app
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)" || exit 1
# exec -> uvicorn is PID 1 and receives SIGTERM for a graceful shutdown.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 20 --no-access-log"]
