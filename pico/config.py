"""Simulation-side configuration helpers.

Keep this module import-cycle-free: it must not import pico services or providers.
"""

from __future__ import annotations

from typing import TypeAlias
from config.settings import MockConfig
from common_config import CONFIG as _UNIFIED_CONFIG

# Type used across the mock/pico package.
AppConfig: TypeAlias = MockConfig

# Simulation config instance extracted from the unified config.
CONFIG: MockConfig = _UNIFIED_CONFIG.mock
