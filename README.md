# CO₂ Grid Meter

[![CI](https://github.com/fabiocicerchia/co2-grid-meter/actions/workflows/code-quality.yml/badge.svg)](https://github.com/fabiocicerchia/co2-grid-meter/actions/workflows/code-quality.yml)
[![Security](https://github.com/fabiocicerchia/co2-grid-meter/actions/workflows/security.yml/badge.svg)](https://github.com/fabiocicerchia/co2-grid-meter/actions/workflows/security.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocicerchia/co2-grid-meter/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocicerchia/co2-grid-meter)
[![CI carbon](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/fabiocicerchia/co2-grid-meter/gh-pages/badge.json)](.github/workflows/carbon-badge.yml)

A local-first project that helps you decide **when to run energy-hungry appliances** by tracking grid carbon intensity for your region.

## What you get

- `/status` endpoint with current intensity, a run/wait recommendation and the
  firmware's uptime in seconds.
- `/em/window` endpoint with recent history.
- `/em/window-overlay` endpoint with week-shifted overlay data used for recommendations.
- Web dashboard (`web/static/*`) with trend chart, LED meter, and auto refresh controls.
- Firmware path for Pico W + e-ink display.

## Hardware needed

For the firmware/e-ink hardware path, use:

- **Raspberry Pi Pico 2 W**
- **Waveshare WS-19588** tri-color e-paper display module

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

## Install

```sh
git clone https://github.com/fabiocicerchia/co2-grid-meter.git
cd co2-grid-meter
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```sh
./start.sh          # serves the dashboard and the grid poller
```

Flashing the Pico W is covered in [`docs/firmware.md`](docs/firmware.md).

## Documentation

Full docs live in [`docs/`](docs/). Runnable examples live in [`examples/`](examples/).

## Support

Need help implementing this? [Get in touch](https://fabiocicerchia.it/contact).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please don't open a public issue.

## License

[MIT](LICENSE) © 2026 Fabio Cicerchia
