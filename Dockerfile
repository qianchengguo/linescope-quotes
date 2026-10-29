FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LINESCOPE_DB=/app/data/linescope.sqlite3
COPY pyproject.toml README.md LICENSE logging.json ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home appuser && mkdir /app/data && chown appuser:appuser /app/data
USER appuser
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=3)"
CMD ["python", "-m", "uvicorn", "linescope.app:app", "--host", "0.0.0.0", "--port", "8765", "--no-access-log", "--log-config", "logging.json"]
