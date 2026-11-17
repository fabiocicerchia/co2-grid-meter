#!/bin/sh
# Started from KUAL. Runs the meter in the background and keeps the screen
# awake; bin/stop.sh undoes both. Output goes to co2meter.log next to this
# folder, which is the first place to look when the screen shows nothing.

DIR="$(cd "$(dirname "$0")/.." && pwd)"
PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
LOG="$DIR/co2meter.log"
PIDFILE="/tmp/co2meter.pid"

# NiLuJe's Python 3 package installs here (MRPI). Override if yours differs.
PYTHON="${CO2_PYTHON:-/mnt/us/python3/bin/python3}"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"
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
nohup "$PYTHON" run.py >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
