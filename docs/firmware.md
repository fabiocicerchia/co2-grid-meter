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

## Serving the dashboard from the device

For an offline install the Pico can serve the dashboard itself, instead of
needing the desktop server running somewhere:

```json
{ "web": { "serve_static": true, "static_root": "static" } }
```

Then copy `web/static/*` to `static/` on the device. **Off by default** — an
existing deployment must not start serving files because it was upgraded, and a
device without the assets copied over would answer 404 for every page.

The four files are ~24 KB against roughly 800 KB free on a Pico W after
MicroPython and this firmware, so the budget is not close. A test asserts they
stay under 200 KB, which is where it would first become a question.

Static paths are tried before the JSON routes but fall through when the file
does not exist, so enabling this cannot shadow `/status` or `/em/window`.

**Files are streamed in 1 KB chunks**, never read whole: a 15 KB script in a
variable is a memory failure on a device with tens of KB of heap, and it would
hold the refresh loop for the length of the read.

**Conditional GET**: each response carries an ETag built from size and mtime,
and a matching `If-None-Match` gets a 304 with no body. A reload of an
unchanged asset becomes a header exchange, and the radio is the most expensive
thing on the board.

**On path traversal.** The device's flash holds `settings.json` — Wi-Fi
password, provider tokens — and the crash dumps, with no user accounts between
a request and any of it. `..`, absolute paths, backslashes and percent-encoded
separators are all refused *before* anything opens a file, decoding first so
`%2e%2e%2f` cannot slip past a check that only reads the raw URL. Every refusal
returns the same 404 as a missing file, so a probe learns nothing about what
exists.
