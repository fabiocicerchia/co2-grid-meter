# Kindle

An old Kindle can run the meter itself, in place of the Pico: same providers,
same recommendation, same picture as the e-ink panel, drawn full-screen. The
code is the firmware under `pico/`, unchanged, run by `kindle/run.py` under the
Kindle's Python with stand-ins for the MicroPython-only modules
(`kindle/shims/`).

Written for the **Kindle 4 (non-touch), firmware 4.1.4**. Other models of that
era should work with `CO2_SCREEN_W`/`CO2_SCREEN_H` set (see
[Tuning](#tuning)); none has been tried.

> Just want to *look* at a Pico from a Kindle, no jailbreak? Open
> `http://<pico-ip>/kindle` in the Experimental Browser — see
> [firmware.md](firmware.md#kindle-as-a-second-display).

## 1. Jailbreak

Follow the MobileRead wiki's
[Kindle 4 NT hacking page](https://wiki.mobileread.com/wiki/Kindle4NTHacking).
The K4 jailbreak covers firmware 4.0.0 through 4.1.4. When it has worked, a
book called **You are Jailbroken** appears on the home screen.

Get the files from NiLuJe's
[snapshots thread](https://www.mobileread.com/forums/showthread.php?t=225030),
the one source for all three of these steps. Use the K4 builds.

## 2. MRPI and KUAL

From the same thread, install **MRPI** (the package installer) and **KUAL**
(the launcher this extension adds a menu to). Their READMEs cover the K4.

## 3. Python 3

Install NiLuJe's **Python** package through MRPI. It ships Python 3.9 for the
K4, with `certifi`, which the meter uses for current TLS certificates. It lands
in `/mnt/us/python3`; if yours is elsewhere, set `CO2_PYTHON` in
`bin/start.sh`.

## 4. The meter

```sh
cp pico/settings.example.json pico/settings.json   # if you have not already
$EDITOR pico/settings.json                          # location, providers, tokens
kindle/build.sh
```

Plug the Kindle in over USB and copy `dist/kindle/extensions/` onto its drive,
merging with the `extensions` folder KUAL created. Eject.

The `wifi` block in `settings.json` must be filled in to pass the startup check,
but the Kindle never uses it: join your network from the Kindle's own settings.

Set `display.render_min_interval_sec` to 300 or more. Every render is a full
e-ink refresh, the black flash included, and a minute apart that is both
distracting and the battery.

## 5. Run it

KUAL → **CO2 Grid Meter**:

- **Test (one render)** fetches, draws once and stops. Start here: it takes up
  to a couple of minutes, and on failure writes a line on screen and the
  details to `co2meter.log`.
- **Start** runs it in the background and keeps the screensaver off.
- **Stop** ends it and lets the screensaver back.

The picture is turned a quarter, so the panel's long side runs down the
Kindle's: stand it on its right edge. Keep it on the charger; with the
screensaver off and Wi-Fi on, a K4 lasts days, not weeks.

Pressing a button brings the Kindle's own screen back over the reading until
the next render.

## Tuning

Environment variables, set at the top of `bin/start.sh`:

| Variable       | Default                       | What it is                                    |
| -------------- | ----------------------------- | --------------------------------------------- |
| `CO2_PYTHON`   | `/mnt/us/python3/bin/python3` | The interpreter                               |
| `CO2_SCALE`    | `3`                           | Whole-number zoom; 3 keeps the 8x8 font sharp |
| `CO2_ROTATE`   | `90`                          | `90`, `270` (other edge down) or `0`          |
| `CO2_SCREEN_W` | `600`                         | Screen width in pixels                        |
| `CO2_SCREEN_H` | `800`                         | Screen height in pixels                       |

## Trying it on a desktop

```sh
cd somewhere-with-a-settings.json
CO2_EIPS= CO2_PNG=/tmp/co2.png python3 path/to/kindle/run.py --once
```

`CO2_EIPS=` empty skips the screen and only writes the PNG.

## How it differs from the Pico

- No HTTP server: the Kindle is the display, nothing calls it.
- The clock: the Pico keeps local time in its RTC and the firmware is written
  around that. `run.py` takes the time from NTP (a retired Kindle's own clock
  can be days out) and makes `time.time()` and `localtime()` read local
  wall-clock time the same way.
- Red becomes dark grey: e-ink has no red, and the warning panel's white text
  must still read on it.
