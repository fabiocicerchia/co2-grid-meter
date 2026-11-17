#!/bin/sh
PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
PIDFILE="/tmp/co2meter.pid"

[ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null
rm -f "$PIDFILE"
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
# The home screen redraws on the next key press.
eips -c
