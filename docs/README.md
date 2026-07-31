# Dashboard + Mock Pico notes

- [Getting Started](getting-started.md) — setup and first run.
- [Architecture](architecture.md) — components and data flow.

This repository ships two local services:

- Mock Pico API (`python -m mock.mock_pico`) on `127.0.0.1:8080`
- Dashboard server (`python -m web.server`) on `127.0.0.1:5000`

The dashboard reads from `/api/*`, which proxies to `PICO_BASE_URL`.

## Quick start

```bash
pip install -r requirements.txt
python -m mock.mock_pico
python -m web.server
```

Open `http://127.0.0.1:5000/`.

## Refresh/cache behavior

To reduce provider/API pressure, mock Pico and firmware responses are cached.

- `PICO_CACHE_REFRESH_SECONDS` controls TTL.
- Default is `3600` seconds (1 hour).

Example:

```bash
export PICO_CACHE_REFRESH_SECONDS=1800
```

## Useful endpoints

- `http://127.0.0.1:8080/status`
- `http://127.0.0.1:8080/em/window?back_hours=48`
- `http://127.0.0.1:8080/em/window-overlay`
