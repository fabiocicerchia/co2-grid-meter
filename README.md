# CO₂ Grid Meter

A local-first project that helps you decide **when to run energy-hungry appliances** by tracking grid carbon intensity for your region.

## What you get

- `/status` endpoint with current intensity and a run/wait recommendation.
- `/em/window` endpoint with recent history.
- `/em/window-overlay` endpoint with week-shifted overlay data used for recommendations.
- Web dashboard (`web/static/*`) with trend chart, LED meter, and auto refresh controls.
- Firmware path for Pico W + e-ink display.

## Project components

- `mock/mock_pico.py`: local Pico-compatible HTTP server.
- `mock/handler.py`: request routing for `/status`, `/em/window`, `/em/window-overlay`.
- `web/server.py` + `web/handler.py`: dashboard static server and `/api/*` proxy to Pico/mock Pico.
- `pico/firmware/*`: firmware HTTP endpoints, provider calls, recommendations, e-ink rendering.

## Caching and API pressure reduction

Both the mock server and firmware now use a **TTL cache** for endpoint payloads to reduce upstream API calls.

- Env var: `PICO_CACHE_REFRESH_SECONDS`
- Default: `3600` seconds (1 hour)

Example:

```bash
export PICO_CACHE_REFRESH_SECONDS=900  # refresh every 15 minutes
```

## Provider selection order

Provider fallback order remains:

1. UK Carbon Intensity (`GB/UK`)
2. WattTime (if enabled + credentials)
3. ENTSO-E (if token + mapped region)
4. Electricity Maps (if enabled + token)
5. Simulated fallback (`PICO_ALLOW_SIM_FALLBACK=1`)


## Hardware needed

For the firmware/e-ink hardware path, use:

- **Raspberry Pi Pico 2 W**
- **Waveshare WS-19588** tri-color e-paper display module

## Firmware setup references

If you are new to Pico/MicroPython setup, these guides are useful:

- Thonny IDE: https://thonny.org/
- Raspberry Pi Pico getting started (step 3): https://projects.raspberrypi.org/en/projects/getting-started-with-the-pico/3
- Waveshare Pico ePaper Python guide: https://www.waveshare.com/wiki/Pico-ePaper-7.5#Python
- Video guide: https://www.youtube.com/watch?v=9YvWT8bNllU

Firmware display driver behavior is aligned with Waveshare's Pico demo command sequence for the 2.13" B V4/WS-19588 panel to reduce compatibility issues with vendor examples.


## Single-file firmware bundle

If you want a copy/paste firmware script, use:

- `pico/firmware/pico_firmware_all_in_one.py`

This file is an all-in-one bundle of the firmware runtime (config, providers, HTTP handlers, display driver, and main loop) intended for direct deployment to Pico.


## Deploy to Pico with rshell

```bash
python -m venv .venv
pip install rshell
rshell
cd /pyboard
cp -r /home/fabio/Documents/proj/pico/lib ./
cp /home/fabio/Documents/proj/pico/main.py ./
```

## Troubleshooting serial logs

```bash
sudo screen /dev/ttyACM0 115200
```

OR

```bash
picocom -b 115200 /dev/ttyACM0
```

Example output:

```text





Terminal ready
[2021-01-01 00:00:06] WiFi: connected 192.168.178.136
(2026, 2, 18, 20, 43, 27, 2, 49)
[2026-02-18 20:43:27] Pico running: http://192.168.178.136:8080
[2026-02-18 20:43:27] Clearing e-ink
[2026-02-18 20:44:34] Finished clearing
[2026-02-18 20:44:57] Fetching data
[2026-02-18 20:44:57] Making request
[2026-02-18 20:45:26] Provider request made
[2026-02-18 20:45:26] Processing data
[2026-02-18 20:46:34] Processing data done
[2026-02-18 20:46:34] Provider used: entsoe
[2026-02-18 20:46:34] Making request
[2026-02-18 20:46:36] Provider request made
[2026-02-18 20:46:36] Processing data
[2026-02-18 20:47:53] Processing data done
[2026-02-18 20:47:53] Provider used: entsoe
[2026-02-18 20:47:53] Finished fetching data
```

## Run locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run mock Pico:

```bash
python -m mock.mock_pico
```

Run dashboard server:

```bash
python -m web.server
```

Open:

- Dashboard: `http://127.0.0.1:5000/`
- Mock Pico status: `http://127.0.0.1:8080/status`

## Tests

```bash
pytest -q
```

## Environment highlights

- `PICO_BASE_URL` (dashboard upstream target)
- `PICO_CACHE_REFRESH_SECONDS` (mock + firmware cache TTL)
- `DEFAULT_COUNTRY`, `DEFAULT_CITY`, `DEFAULT_LAT`, `DEFAULT_LON`
- Provider auth vars (`ENTSOE_TOKEN`, `WATTTIME_*`, `ELECTRICITYMAPS_TOKEN`)

