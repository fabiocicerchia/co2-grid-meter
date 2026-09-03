"""Runs before main.py, and is never replaced by an update.

MicroPython executes boot.py first, which makes it the only place a rollback
can live: whatever undoes a bad update has to be older than the update it is
undoing. `ota.PROTECTED` refuses to stage this file or ota.py for exactly that
reason.

It does one thing and cannot fail loudly. A device that has just taken a bad
update is already in trouble; a boot script that raises on the way to fixing it
would be the second failure.
"""

try:
    import ota

    outcome = ota.boot_check()
    if outcome == "rolled-back":
        print("OTA: new firmware never reached the serving loop — rolled back")
    elif outcome == "trying":
        print(
            "OTA: booting new firmware, attempt %s" % ota.read_state().get("attempts")
        )
# Broad on purpose: boot must continue whatever happens.
except Exception as error:
    # No ota.py, an unreadable state file, a filesystem that will not stat:
    # none of them are a reason to refuse to boot the firmware that is there.
    print("OTA: boot check skipped (%s)" % error)
