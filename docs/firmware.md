# Firmware and hardware setup

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

## Language

The dashboard resolved `data-i18n` keys already; the panel did not, so the half
of the product a non-English speaker actually looks at was English only.

```python
CONFIG.ui.language = "it"  # or via settings.json once that lands
```

Shipping `en` and `it`, the same pair the dashboard has — a test asserts the two
halves have not drifted to different sets.

**A missing key renders the English default, never blank.** A blank line on an
e-ink panel is indistinguishable from a broken refresh, and the panel is the
only output some installs have. An unknown key renders the key itself, which is
a poor label but a visible and searchable one. A locale whose placeholders do
not match — a dropped `%d` — renders the English form rather than raising, so
the reading still reaches the panel.

**An unknown language falls back to English and says so** in the log, because a
device silently ignoring its own configuration looks like a broken translation
rather than a typo in one line.

**Memory: 592 bytes for both locales**, roughly 296 bytes each, against the tens
of KB of heap a Pico W has left after this firmware. A test holds the whole
table under 4 KB and each locale under 1 KB, which is what keeps that true as
locales are added.

**Length is checked, not trusted.** The smallest supported panel is 122 px, or
about 20 characters at the built-in font, and an overflowing translation is
clipped silently — so the test renders each string with its placeholders filled
and asserts it fits.
