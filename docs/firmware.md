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
