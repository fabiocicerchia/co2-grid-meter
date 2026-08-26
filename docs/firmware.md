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
