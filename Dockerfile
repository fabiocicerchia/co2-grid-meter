# Packages the dashboard server (web/). The mock Pico (mock/) and the
# firmware (pico/) are not containerized: the mock is a local dev aid and
# the firmware runs on-device via MicroPython, not this image.
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common_config.py .
COPY config/ config/
COPY web/ web/

RUN adduser --disabled-password --uid 10001 app
USER app

EXPOSE 5000
ENTRYPOINT ["python3", "-m", "web.server"]
