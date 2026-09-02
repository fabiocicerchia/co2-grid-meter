"""Staged, checksum-verified firmware updates with automatic rollback.

WHY THIS EXISTS: updating meant reflashing by hand, and a bad write bricked the
device until somebody could reach it. This is the smallest thing that makes an
update survivable on hardware you cannot walk to.

Single slot, not A/B. A Pico W's flash budget does not stretch to two copies of
the firmware, so the safety comes from ordering rather than from redundancy:

    stage → verify → back up → replace → boot marker → healthy | rollback

Five rules, each of which is a failure this design has to survive:

  * NOTHING IS ACTIVATED UNTIL EVERY FILE VERIFIES. A half-downloaded update
    that replaced three files of five would leave a device running a mixture of
    two firmwares, which is worse than not updating.
  * THE LIVE FILE IS NEVER REMOVED BEFORE ITS REPLACEMENT EXISTS. Writes go to
    `<name>.new` and are renamed over the target. Power loss mid-write leaves a
    stray `.new` and an untouched live file.
  * THE BOOT MARKER IS WRITTEN BEFORE THE FIRST BOOT ON NEW FIRMWARE, and only
    cleared once that firmware reaches its serving loop. A device that reboots
    three times without getting there rolls itself back.
  * boot.py AND THIS MODULE ARE NEVER UPDATED. The recovery code cannot be the
    thing that got half-written — if it were, a failed update would take the
    only mechanism that could undo it.
  * STATE IS WRITTEN ATOMICALLY, via a temp file and a rename, because a
    truncated state file is a device that does not know whether it is mid-update.

"Healthy" means the firmware imported, read its settings, brought up the
network and reached the serving loop. Deliberately *not* "fetched a reading":
tying rollback to a provider being reachable would roll back perfectly good
firmware during an upstream outage.
"""

import os

try:  # MicroPython
    from uhashlib import sha256
except ImportError:  # CPython, for the tests
    from hashlib import sha256

try:
    import ujson as json
except ImportError:
    import json


OTA_DIR = "ota"
STAGING_DIR = OTA_DIR + "/staging"
BACKUP_DIR = OTA_DIR + "/backup"
STATE_PATH = OTA_DIR + "/state.json"

# Three boots on new firmware without reaching the serving loop is a bad image.
# One would roll back on a single unlucky reset; ten would leave a device in a
# reboot loop for minutes before helping.
MAX_BOOT_ATTEMPTS = 3

# Never replaced by an update: whatever runs the rollback has to be older than
# the update it is undoing.
PROTECTED = ("boot.py", "ota.py")

CHUNK = 512


class OtaError(Exception):
    pass


# ---- filesystem helpers, written for MicroPython's os module ---------------


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _mkdirs(path):
    parts = path.split("/")
    grown = ""
    for part in parts:
        if not part:
            continue
        grown = part if not grown else grown + "/" + part
        if not _exists(grown):
            try:
                os.mkdir(grown)
            except OSError:
                pass


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _replace(src, dst):
    """Rename src over dst, as atomically as the filesystem allows.

    littlefs (the Pico's default) replaces on rename. FAT does not, so the
    fallback removes first — which opens a window where neither file exists.
    That window is precisely what the boot marker and the backup are for.
    """
    try:
        os.rename(src, dst)
        return
    except OSError:
        _remove(dst)
        os.rename(src, dst)


def _copy(src, dst):
    with open(src, "rb") as fin, open(dst + ".new", "wb") as fout:
        while True:
            block = fin.read(CHUNK)
            if not block:
                break
            fout.write(block)
    _replace(dst + ".new", dst)


def digest_of(path):
    """Hex sha256 of a file, read in chunks — the whole firmware does not fit
    in RAM twice on this device."""
    h = sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return _hex(h.digest())


def _hex(raw):
    # MicroPython's ubinascii.hexlify returns bytes and is not always present;
    # this is short enough not to be worth the import.
    return "".join("%02x" % b for b in raw)


# ---- state ----------------------------------------------------------------


def read_state():
    try:
        with open(STATE_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        # No update in flight, or a state file that did not survive a power
        # loss. Both mean "running whatever is on flash", which is safe.
        return {"stage": "idle"}


def write_state(state):
    _mkdirs(OTA_DIR)
    with open(STATE_PATH + ".new", "w") as fh:
        json.dump(state, fh)
    _replace(STATE_PATH + ".new", STATE_PATH)


# ---- staging --------------------------------------------------------------


def begin(manifest):
    """Start an update. `manifest` is {filename: {"sha256": hex, "size": n}}.

    Clears staging first, so a `.part` left by an interrupted download is never
    mistaken for a complete file.
    """
    for name in manifest:
        if name in PROTECTED:
            raise OtaError("%s is never updated over the air" % name)
        if "/" in name:
            raise OtaError("%s: updates are flat files, not paths" % name)
    _mkdirs(STAGING_DIR)
    for name in os.listdir(STAGING_DIR):
        _remove(STAGING_DIR + "/" + name)
    write_state({"stage": "staging", "manifest": manifest})
    return manifest


def stage(name, chunks):
    """Write one file into staging, verifying it before it counts as staged.

    Written to `<name>.part` and renamed only once the digest matches, so an
    interrupted transfer leaves something that verify() will not accept.
    """
    state = read_state()
    manifest = state.get("manifest") or {}
    if name not in manifest:
        raise OtaError("%s is not in the manifest" % name)

    _mkdirs(STAGING_DIR)
    part = STAGING_DIR + "/" + name + ".part"
    h = sha256()
    written = 0
    with open(part, "wb") as fh:
        for chunk in chunks:
            fh.write(chunk)
            h.update(chunk)
            written += len(chunk)

    want = manifest[name]
    if _hex(h.digest()) != want.get("sha256") or written != want.get("size"):
        _remove(part)
        raise OtaError("%s failed verification and was discarded" % name)
    _replace(part, STAGING_DIR + "/" + name)
    return written


def verify():
    """Every file in the manifest, present and correct. Returns the names."""
    state = read_state()
    manifest = state.get("manifest") or {}
    if not manifest:
        raise OtaError("no update staged")
    for name, want in manifest.items():
        path = STAGING_DIR + "/" + name
        if not _exists(path):
            raise OtaError("%s was never staged" % name)
        if digest_of(path) != want.get("sha256"):
            raise OtaError("%s does not match its manifest digest" % name)
    return sorted(manifest)


# ---- activation and rollback ----------------------------------------------


def activate():
    """Back up the live files, replace them, and arm the boot marker.

    The marker is written *before* the first file is replaced. A power loss
    anywhere in this function therefore leaves a device whose next boot knows
    an update was in progress, and which rolls back if it cannot get healthy.
    """
    names = verify()
    _mkdirs(BACKUP_DIR)

    write_state({"stage": "pending", "files": names, "attempts": 0})

    replaced = []
    for name in names:
        if _exists(name):
            _copy(name, BACKUP_DIR + "/" + name)
        else:
            # A file the update adds has no backup; rollback deletes it.
            _remove(BACKUP_DIR + "/" + name)
        _copy(STAGING_DIR + "/" + name, name)
        replaced.append(name)
    return replaced


def rollback():
    """Put back what activate() replaced. Safe to call twice."""
    state = read_state()
    restored = []
    for name in state.get("files") or []:
        backup = BACKUP_DIR + "/" + name
        if _exists(backup):
            _copy(backup, name)
            restored.append(name)
        else:
            # It was a file the update added; removing it is the undo.
            _remove(name)
    write_state({"stage": "rolled_back", "files": state.get("files") or []})
    return restored


def boot_check():
    """Called from boot.py, before the new firmware gets a chance to run.

    Returns one of "idle", "trying" or "rolled-back". The count is written
    before the firmware is given control, so a device that resets during boot
    still burns an attempt — otherwise a crash-on-import loops forever.
    """
    state = read_state()
    if state.get("stage") != "pending":
        return "idle"

    attempts = int(state.get("attempts") or 0) + 1
    if attempts > MAX_BOOT_ATTEMPTS:
        rollback()
        return "rolled-back"

    state["attempts"] = attempts
    write_state(state)
    return "trying"


def mark_healthy():
    """The new firmware reached its serving loop. Disarm and drop the backup."""
    state = read_state()
    if state.get("stage") != "pending":
        return False
    for name in state.get("files") or []:
        _remove(BACKUP_DIR + "/" + name)
    write_state({"stage": "idle", "files": state.get("files") or []})
    return True


def status():
    """What an update did, for /status — an update that rolled back silently
    is the one you find out about weeks later."""
    state = read_state()
    return {
        "stage": state.get("stage", "idle"),
        "attempts": state.get("attempts", 0),
        "files": state.get("files") or [],
    }
