# Kindle

An old Kindle can run the meter itself, in place of the Pico: same providers,
same recommendation, same picture as the e-ink panel, drawn full-screen. The
code is the firmware under `pico/`, unchanged, run by `kindle/run.py` under the
Kindle's Python with stand-ins for the MicroPython-only modules
(`kindle/shims/`).

Written for, and run on, a **Kindle 4 (non-touch), firmware 4.1.4**. Other models of that
era should work with `CO2_SCREEN_W`/`CO2_SCREEN_H` set (see
[Tuning](#tuning)); none has been tried.

> Just want to *look* at a Pico from a Kindle, no jailbreak? Open
> `http://<pico-ip>/kindle` in the Experimental Browser — see
> [firmware.md](firmware.md#kindle-as-a-second-display).

Every package below comes from NiLuJe's
[snapshots thread](https://www.mobileread.com/forums/showthread.php?t=225030),
except the certificate update. Use the K4 builds. A `.bin` update installs by
copying it to the root of the Kindle's USB drive, ejecting, and choosing
Menu → Settings → Menu → **Update Your Kindle**. Keep one `.bin` at the root at
a time. The K4 does not need MRPI.

## 1. Jailbreak

From `kindle-k4-jailbreak-*.tar.xz`, copy `data.tar.gz`, `ENABLE_DIAGS` and the
`diagnostic_logs` folder to the drive's root, eject, and restart the Kindle
(Menu → Settings → Menu → Restart). In Diagnostics, choose **D) Exit, Reboot or
Disable Diags**, then **R) Reboot System**. At "Are you sure?" press **left** on
the 5-way pad; the centre button only asks again. A book called **You are
Jailbroken** appears when it has worked. Then delete `data.tar.gz` and
`ENABLE_DIAGS` from the root, or the next restart goes back to Diagnostics.

The MobileRead wiki's
[Kindle 4 NT hacking page](https://wiki.mobileread.com/wiki/Kindle4NTHacking)
has the full procedure. It covers firmware 4.0.0 through 4.1.4.

## 2. Python 3

Install `Update_python3_*_k4_install.bin` from `kindle-python-*.tar.xz`. It
ships Python 3.9 as `/mnt/us/python3/bin/python3.9`, with `certifi`, which the
meter uses for current TLS certificates. `bin/start.sh` finds it there; set
`CO2_PYTHON` if yours is elsewhere.

## 3. KUAL

KUAL on the K4 is a kindlet, and needs three things, in this order:

1. **MKK**, the MobileRead Kindlet Kit: `Update_mkk-20141129-k4-ALL_install.bin`
   from `kindle-mkk-*.tar.xz`. Without it, KUAL says the Kindlet Kit is not
   installed.
1. **The certificate update**: `Update_mkk-20250419-k4-ALL_keystore-install.bin`
   from `DevCerts-20250419-KeyStore.zip`, attached to
   [NiLuJe's post in the KUAL thread](https://www.mobileread.com/forums/showthread.php?p=4506164).
   The kindlet signing certificate expired on 17 April 2025, and current KUAL
   builds are signed with its replacement. MKK ships the old one, so this has to
   go on *after* MKK. Restart the Kindle afterwards. Skipping it, or installing
   it before MKK, gives "not signed by an authorized developer".
1. **KUAL itself**: copy `KUAL-KDK-1.0.azw2` from `KUAL-*.tar.xz` into the
   drive's `documents` folder. Not the `KDK-2.0` kindlet and not the booklet
   `.bin`, which are for later models.

## 4. The meter

```sh
cp pico/settings.example.json pico/settings.json   # if you have not already
$EDITOR pico/settings.json                          # location, providers, tokens
kindle/build.sh
```

Plug the Kindle in over USB and copy `dist/kindle/extensions/` onto its drive,
creating `extensions` at the root if it is not there. Eject.

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

| Variable       | Default                         | What it is                                    |
| -------------- | ------------------------------- | --------------------------------------------- |
| `CO2_PYTHON`   | `/mnt/us/python3/bin/python3.*` | The interpreter                               |
| `CO2_SCALE`    | `3`                             | Whole-number zoom; 3 keeps the 8x8 font sharp |
| `CO2_ROTATE`   | `90`                            | `90`, `270` (other edge down) or `0`          |
| `CO2_SCREEN_W` | `600`                           | Screen width in pixels                        |
| `CO2_SCREEN_H` | `800`                           | Screen height in pixels                       |

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
