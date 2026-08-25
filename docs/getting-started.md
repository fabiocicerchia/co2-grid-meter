# Getting Started

## Prerequisites

- Python 3.10+
- A Raspberry Pi Pico 2 W + Waveshare WS-19588 e-paper panel, if you want the
  physical device path. Not required to run the dashboard against the mock.

## Setup

```sh
git clone <this repo>
cd co2-grid-meter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.dist .env  # fill in provider tokens if you have them
```

## Run

```sh
./start.sh
```

This starts the mock Pico API (`127.0.0.1:8080`) and the dashboard server
(`127.0.0.1:5000`) together. Open `http://127.0.0.1:5000/`.

To run them separately, or to point the dashboard at a real device instead of
the mock, see [docs/README.md](README.md).

## Firmware

To flash the actual Pico firmware (`pico/`), see the [top-level README](README.md#firmware-setup-references)
for Thonny/MicroPython setup references.

## Tests

```bash
pytest -q
```

## Environment highlights

- `PICO_BASE_URL` (dashboard upstream target)
- `PICO_CACHE_REFRESH_SECONDS` (mock + firmware cache TTL)
- `DEFAULT_COUNTRY`, `DEFAULT_CITY`, `DEFAULT_LAT`, `DEFAULT_LON`
- Provider auth vars (`ENTSOE_TOKEN`, `WATTTIME_*`, `ELECTRICITYMAPS_TOKEN`)
