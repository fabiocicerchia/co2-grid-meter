"""The OTA flow, including the cases that only matter when they go wrong.

Every test runs against a real temp filesystem — the module is deliberately
plain `os` calls so it behaves the same under CPython and MicroPython.

Loaded by path, NOT by putting pico/ on sys.path for the session: pico/http.py
would shadow the stdlib http package. Same pattern as test_export.py.
"""

import hashlib
import importlib.util
import os
import pathlib
import sys

import pytest

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"


def _load():
    sys.path.insert(0, str(PICO))
    try:
        spec = importlib.util.spec_from_file_location("pico_ota", PICO / "ota.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["pico_ota"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PICO))


ota = _load()


@pytest.fixture
def device(tmp_path, monkeypatch):
    """A device's flat filesystem, with the current firmware already on it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("VERSION = 1\n")
    (tmp_path / "app.py").write_text("OLD\n")
    return tmp_path


def manifest_for(files):
    return {
        name: {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}
        for name, body in files.items()
    }


def stage_all(files):
    for name, body in files.items():
        ota.stage(name, [body])


NEW = {b"main.py": b"", b"app.py": b""}  # placeholder, replaced below
NEW = {"main.py": b"VERSION = 2\n", "app.py": b"NEW\n"}


# --- the happy path ---------------------------------------------------------


def test_a_verified_update_replaces_the_firmware_and_arms_the_marker(device):
    ota.begin(manifest_for(NEW))
    stage_all(NEW)
    assert ota.activate() == ["app.py", "main.py"]

    assert (device / "main.py").read_bytes() == b"VERSION = 2\n"
    assert ota.read_state()["stage"] == "pending"
    # The previous firmware is kept until the new one proves itself.
    assert (device / "ota/backup/main.py").read_bytes() == b"VERSION = 1\n"


def test_reaching_the_serving_loop_disarms_the_marker_and_frees_the_backup(device):
    ota.begin(manifest_for(NEW))
    stage_all(NEW)
    ota.activate()

    assert ota.boot_check() == "trying"
    assert ota.mark_healthy() is True
    assert ota.read_state()["stage"] == "idle"
    assert not (device / "ota/backup/main.py").exists(), "flash is the budget here"
    # Nothing to disarm the second time.
    assert ota.mark_healthy() is False


# --- the update that must not happen ---------------------------------------


def test_a_corrupt_file_is_discarded_at_staging(device):
    ota.begin(manifest_for(NEW))
    with pytest.raises(ota.OtaError) as e:
        ota.stage("main.py", [b"VERSION = 2\n", b"corrupted tail"])
    assert "failed verification" in str(e.value)
    assert not (device / "ota/staging/main.py").exists()
    assert not (device / "ota/staging/main.py.part").exists()


def test_a_partial_update_never_activates(device):
    """Three files of five would leave a device running two firmwares."""
    ota.begin(manifest_for(NEW))
    ota.stage("main.py", [NEW["main.py"]])  # app.py never staged
    with pytest.raises(ota.OtaError) as e:
        ota.activate()
    assert "app.py was never staged" in str(e.value)
    assert (device / "main.py").read_bytes() == b"VERSION = 1\n", "untouched"


def test_the_recovery_code_is_never_updated_over_the_air(device):
    for name in ("boot.py", "ota.py"):
        with pytest.raises(ota.OtaError) as e:
            ota.begin({name: {"sha256": "x", "size": 1}})
        assert "never updated over the air" in str(e.value)


def test_an_update_cannot_write_outside_the_flat_filesystem(device):
    with pytest.raises(ota.OtaError):
        ota.begin({"../evil.py": {"sha256": "x", "size": 1}})


# --- rollback ---------------------------------------------------------------


def test_firmware_that_never_gets_healthy_is_rolled_back(device):
    """The deliberately broken image the issue asks for: it activates, and then
    never reaches the serving loop, so mark_healthy() is never called."""
    ota.begin(manifest_for(NEW))
    stage_all(NEW)
    ota.activate()
    assert (device / "main.py").read_bytes() == b"VERSION = 2\n"

    outcomes = [ota.boot_check() for _ in range(ota.MAX_BOOT_ATTEMPTS + 1)]
    assert outcomes == ["trying"] * ota.MAX_BOOT_ATTEMPTS + ["rolled-back"]

    assert (device / "main.py").read_bytes() == b"VERSION = 1\n"
    assert (device / "app.py").read_bytes() == b"OLD\n"
    assert ota.read_state()["stage"] == "rolled_back"


def test_a_healthy_boot_stops_the_attempt_count_growing(device):
    ota.begin(manifest_for(NEW))
    stage_all(NEW)
    ota.activate()
    ota.boot_check()
    ota.mark_healthy()
    # Every later boot is an ordinary one.
    assert ota.boot_check() == "idle"
    assert (device / "main.py").read_bytes() == b"VERSION = 2\n"


def test_rollback_removes_a_file_the_update_added(device):
    added = {"newmod.py": b"ADDED\n"}
    ota.begin(manifest_for(added))
    stage_all(added)
    ota.activate()
    assert (device / "newmod.py").exists()

    for _ in range(ota.MAX_BOOT_ATTEMPTS + 1):
        ota.boot_check()
    assert not (device / "newmod.py").exists(), "there was nothing to restore"


def test_rollback_is_safe_to_run_twice(device):
    ota.begin(manifest_for(NEW))
    stage_all(NEW)
    ota.activate()
    ota.rollback()
    ota.rollback()
    assert (device / "main.py").read_bytes() == b"VERSION = 1\n"


# --- power loss -------------------------------------------------------------


def test_power_loss_mid_write_leaves_the_live_file_intact(device):
    """Writes land in `<name>.new` and are renamed over the target, so an
    interrupted copy cannot leave the device without a main.py."""
    ota.begin(manifest_for(NEW))
    stage_all(NEW)

    real_replace = ota._replace
    cut = {"n": 0}

    def die_on_second_replace(src, dst):
        cut["n"] += 1
        if cut["n"] == 2:  # state file is the first; die replacing main.py
            raise KeyboardInterrupt("power loss")
        real_replace(src, dst)

    ota._replace = die_on_second_replace
    try:
        with pytest.raises(KeyboardInterrupt):
            ota.activate()
    finally:
        ota._replace = real_replace

    assert (device / "main.py").read_bytes() in (b"VERSION = 1\n", b"VERSION = 2\n")
    assert (device / "main.py").exists(), "the device still has firmware to boot"
    # And the marker was already armed, so the next boot knows to watch.
    assert ota.read_state()["stage"] == "pending"


def test_power_loss_before_activation_leaves_an_unarmed_device(device):
    ota.begin(manifest_for(NEW))
    ota.stage("main.py", [NEW["main.py"]])
    # Reset here: nothing was replaced, so nothing needs undoing.
    assert ota.boot_check() == "idle"
    assert (device / "main.py").read_bytes() == b"VERSION = 1\n"


def test_a_truncated_state_file_reads_as_no_update_in_flight(device):
    ota._mkdirs(ota.OTA_DIR)
    (device / "ota/state.json").write_text('{"stage": "pen')
    assert ota.read_state() == {"stage": "idle"}
    assert ota.boot_check() == "idle"


def test_a_leftover_part_file_is_cleared_by_the_next_begin(device):
    ota._mkdirs(ota.STAGING_DIR)
    (device / "ota/staging/main.py.part").write_bytes(b"half a download")
    ota.begin(manifest_for(NEW))
    assert os.listdir(ota.STAGING_DIR) == []


def test_status_reports_what_an_update_did(device):
    assert ota.status()["stage"] == "idle"
    ota.begin(manifest_for(NEW))
    stage_all(NEW)
    ota.activate()
    ota.boot_check()
    assert ota.status() == {
        "stage": "pending",
        "attempts": 1,
        "files": ["app.py", "main.py"],
    }
