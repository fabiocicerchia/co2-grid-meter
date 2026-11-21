#!/bin/sh
PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
PIDFILE="/tmp/co2meter.pid"

# Normally a key press stops the meter, since KUAL is not running while it is.
# This is for a shell (ssh, or a --once run that never stopped the framework).
# Killing the meter lets start.sh restore the screensaver and the framework.
[ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null
