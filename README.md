
# Grid CO₂ Meter (Rome)

Raspberry Pi project that:
- Reads grid carbon intensity
- Stores history locally (SQLite)
- Shows recommendation (RUN NOW / WAIT)
- Displays 48h graph + last-week overlay
- Drives a 12‑LED meter (4 green, 4 yellow, 4 red)
- Supports Waveshare e‑ink display
- Provides a local web dashboard

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ELECTRICITYMAPS_TOKEN="YOUR_TOKEN"
python poller.py
```

Dashboard:
http://localhost:8080

## Hardware
- Raspberry Pi
- 12 LEDs
- 12× 330Ω resistors
- Breadboard + jumper wires
- Optional Waveshare e‑ink display
