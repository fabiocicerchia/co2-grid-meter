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

## The ENTSO-E response

ENTSO-E answers with an A75 XML document that is 95% `<Point>` elements. The
firmware used to run all of it through `xmltok`, a general tokenizer that emits
an event per tag, attribute and text node — `pico/config.py` carried a
`super slow due to XML response` note about it, and on a Pico it stalls the
refresh loop.

Nothing here needs a general parser. Six fields are read — `psrType`, `start`,
`end`, `resolution`, `position`, `quantity` — and each is a text node in a tag
with no attributes, so `pico/providers/entsoe_parse.py` scans for those
directly with `str.find` (a C-level search in MicroPython) and skips everything
else without tokenising it.

Measured on CPython 3.13 against a representative day — 4 production types,
15-minute resolution, 25 KB, 384 points, mean of five runs:

| | parse time | peak heap |
|---|---:|---:|
| `xmltok` tokenize | 9.29 ms | 102.2 KB |
| field scan | **2.64 ms** | **30.2 KB** |

3.5x faster and 3.4x less peak memory. The device figures will differ — a Pico
is far slower in absolute terms, and the gap should *widen*, since `str.find`
is native there while the tokenizer's per-character loop is interpreted — but
the ratio is the part this change controls.

**What it gives up**, stated plainly: this is not an XML parser. It would be
wrong on a document using attributes on those six tags, CDATA, or a comment
containing one of the six names. ENTSO-E's A75 is machine-generated from a
fixed schema and uses none of them, and the scanner fails closed — it yields
nothing rather than something wrong. The tests cover namespaced tags,
attributes on structural tags, comments, self-closing tags, truncated
documents, a non-numeric quantity and an HTML error page.
