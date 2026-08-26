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

## Device settings

Wi-Fi credentials and provider tokens are **not** in source. `pico/config.py`
holds defaults that describe the shape of the configuration; the device's own
values live in `settings.json` on its filesystem, which is gitignored.

```sh
cp pico/settings.example.json settings.json   # then fill it in, then copy to the Pico
```

Anything omitted keeps the default. The overlay is applied at import, so every
module that does `from config import CONFIG` sees the device's values.

**A missing required value fails at startup, by name.** Falling back silently
produces a device that boots, connects to nothing and shows a dummy reading —
which reads as a broken provider rather than an empty password. All missing
values are listed in one error, because someone setting up a fresh device wants
the whole list at once.

**Only enabled providers need credentials.** The keyless ci-api needs no token;
demanding one would be a fallback of a different kind.

**An unknown setting is an error naming it.** A typo is the usual cause, and a
device that ignores half its configuration without saying which half is the
worst of the available outcomes.

The desktop side is unchanged: `config/settings.py` still reads environment
variables, and remains the source of truth there.

## Boot diagnostics

Startup used to log the IP and nothing else, which is the least useful subset:
grid intensity is derived from where the device thinks it is, so a wrong number
is far more often a wrong geolocation than a wrong provider.

The boot log now carries the whole interface and the resolved location:

```
WiFi: connected 192.168.1.50 netmask 255.255.255.0 gateway 192.168.1.1 dns 1.1.1.1
Network: ip 192.168.1.50 netmask 255.255.255.0 gateway 192.168.1.1 dns 1.1.1.1
Location: Berlin, Germany (DE)
ISP: Telekom
```

The same data is on `/status` under `diagnostics`.

The ISP is there for a specific failure: an IP-based lookup resolves to the
ISP's egress, so a device behind a VPN or a CGNAT gateway is priced against the
wrong grid, and the ISP name is the fastest way to see it.

**Location is coarse on purpose.** City, region and country are logged;
latitude and longitude are not, in the log or on the status endpoint. Logs get
pasted into issue reports, and a precise coordinate is a home address. The
exact figures still reach the grid lookup — they simply do not pass through the
diagnostics path, which is built from the interface and the geo payload alone
and has no access to config, so no key can reach a log line through it.

A failed geolocation lookup is a warning: the device serves on the configured
defaults rather than refusing to boot.

## Uptime

`/status` carries `uptime_seconds`, and the boot sequence logs a readable form
(`Uptime at start of serving: 3d 4h 12m`) once the network is up.

It is counted from `time.ticks_ms()`, not the wall clock. The RTC starts unset
and only gets a value if Wi-Fi came up and `set_time()` ran — which is exactly
the path that has failed when you are trying to work out whether the device is
wedged or freshly rebooted.

That counter wraps roughly every 12.4 days, comfortably inside the uptimes this
is meant to report, so elapsed time is accumulated from `ticks_diff` deltas
rather than subtracted from a boot value. Anything that samples it more often
than the wrap period keeps it accurate; `/status` and the display tick both do,
by a wide margin.
