#!/bin/sh
# Started from KUAL. Runs the meter with the Kindle's own UI (the framework)
# stopped, so its status bar cannot draw over the reading, and the screensaver
# held off. Any key ends the meter and brings the framework back.
# Output goes to co2meter.log next to this folder, which is the first place to
# look when the screen shows nothing.

DIR="$(cd "$(dirname "$0")/.." && pwd)"
PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
LOG="$DIR/co2meter.log"
PIDFILE="/tmp/co2meter.pid"

# NiLuJe's Python 3 package installs a versioned binary (python3.9 on the K4)
# in /mnt/us/python3/bin. Override with CO2_PYTHON if yours differs.
PYTHON="${CO2_PYTHON:-}"
if [ -z "$PYTHON" ]; then
    for candidate in /mnt/us/python3/bin/python3.* /mnt/us/python3/bin/python3 /usr/bin/python3; do
        case "$candidate" in *-config) continue ;; esac
        [ -e "$candidate" ] && PYTHON="$candidate" && break
    done
fi
if [ -z "$PYTHON" ]; then
    eips 2 38 "co2meter: python3 not found, see docs/kindle.md"
    exit 1
fi

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    eips 2 38 "co2meter: already running"
    exit 0
fi

lipc-set-prop com.lab126.wifid enable 1 2>/dev/null
# Without this the screensaver replaces the reading after ten minutes.
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

cd "$DIR" || exit 1
if [ "$1" = "--once" ]; then
    "$PYTHON" run.py --once >>"$LOG" 2>&1 || eips 2 38 "co2meter: test failed, see co2meter.log"
    exit 0
fi

if [ "$1" != "--detached" ]; then
    # Out of KUAL's process tree first: stopping the framework stops KUAL, and
    # anything still attached to it goes too.
    if command -v setsid >/dev/null 2>&1; then
        setsid "$0" --detached </dev/null >>"$LOG" 2>&1 &
    else
        nohup "$0" --detached </dev/null >>"$LOG" 2>&1 &
    fi
    exit 0
fi

FRAMEWORK=/etc/init.d/framework
[ -x "$FRAMEWORK" ] && "$FRAMEWORK" stop
"$PYTHON" run.py &
echo $! >"$PIDFILE"
wait $!
rm -f "$PIDFILE"
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
[ -x "$FRAMEWORK" ] && "$FRAMEWORK" start
