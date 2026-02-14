"""Utility helpers shared across firmware modules.

Implementation lives in :mod:`sim.pico.fw_shared` so the simulator and firmware
stay consistent.
"""

from pico.fw_shared import (  # noqa: F401
    ProviderError,
    clamp,
    epoch_to_iso_z,
    floor_hour_epoch,
    fmt_hhmm_local,
    iso_z_to_epoch,
    safe_float,
    url_decode,
)
