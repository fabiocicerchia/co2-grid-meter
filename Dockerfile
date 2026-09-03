# Packages the dashboard server (web/). The mock Pico (mock/) and the
# firmware (pico/) are not containerized: the mock is a local dev aid and
# the firmware runs on-device via MicroPython, not this image.
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common_config.py .
COPY config/ config/
COPY web/ web/

RUN adduser --disabled-password --uid 10001 app
USER app
# hardener: run this image with `docker run --read-only` for a read-only rootfs

EXPOSE 5000

# /status is the handler's own readiness view, so this fails when the server is
# up but not actually serving. stdlib urllib -- no curl in the image.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/status', timeout=2).status == 200 else 1)"]

ENTRYPOINT ["python3", "-m", "web.server"]
