FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data APP_HOST=0.0.0.0 APP_PORT=8000
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser \
    && mkdir /data && chown appuser:appuser /data
COPY requirements.txt .
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then \
      PIP_CERT=/run/secrets/pip_ca pip install --no-cache-dir --disable-pip-version-check -r requirements.txt; \
    else pip install --no-cache-dir --disable-pip-version-check -r requirements.txt; fi
COPY --chown=appuser:appuser app ./app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["python", "-m", "app"]
