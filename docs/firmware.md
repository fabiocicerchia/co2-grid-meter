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
directly with `bytes.find` (a C-level search in MicroPython) and skips
everything else without tokenising it.

**It reads off the socket, not out of a string.** This is the part that decides
whether the device works at all. A 60-hour window over a zone publishing at
PT15M is a 180-250 KB response and a Pico W has 264 KB of SRAM *in total*, so
the body can never exist whole in memory. The scan runs over a sliding window
filled in `CHUNK`-sized reads, and `iter_series` yields each TimeSeries as its
closing tag arrives, so `entsoe.py` folds it into the hourly buckets and drops
it. Peak is one window plus one series — flat in the size of the response.

Measured on CPython 3.13, mean of five runs, against the window `app.py`
actually requests (48h back + 12h forward) for a zone publishing twelve
production types at 15-minute resolution — a 184 KB document, 2880 points:

| | parse time | peak heap |
|---|---:|---:|
| `xmltok` tokenize | 101.5 ms | 2.4 KB |
| field scan, whole body in a string | **17.9 ms** | 510.2 KB |
| field scan, streamed | **29.0 ms** | **19.5 KB** |

`xmltok` was slow but frugal — it streamed. Reading the body into a string to
scan it is the fastest of the three and does not fit on the board by a factor
of three, which is the trap: the tokenizer was the visible problem and the
buffering was the load-bearing part nobody had to think about. Streaming the
scan keeps a 3.5x speedup over `xmltok` and stays inside a few tens of KB. It
costs more than `xmltok`'s 2.4 KB because one series' points are held at a
time rather than folded point by point; at 19.5 KB against ~100-160 KB of
usable heap that is affordable, and it keeps the caller's loop unchanged.

The device figures will differ — a Pico is far slower in absolute terms, and
the speed gap should *widen*, since `find` is native there while the
tokenizer's per-character loop is interpreted. The memory figures are the ones
that transfer most directly: a response of N bytes is N bytes on either
runtime.

**What it gives up**, stated plainly: this is not an XML parser. It would be
wrong on a document using attributes on those six tags, CDATA, or a comment
containing one of the six names. ENTSO-E's A75 is machine-generated from a
fixed schema and uses none of them, and the scanner fails closed — it yields
nothing rather than something wrong. The tests cover namespaced tags,
attributes on structural tags, comments, self-closing tags, truncated
documents, a non-numeric quantity, an HTML error page, a value split across
two socket reads, and that peak memory does not track document size.
