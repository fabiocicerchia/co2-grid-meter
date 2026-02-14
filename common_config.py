"""Unified application runtime configuration initialization."""

from __future__ import annotations

import os
from dataclasses import MISSING, fields, is_dataclass
from typing import Any, get_args, get_origin
from config import UnifiedConfig


def _to_bool(raw_value: str) -> bool:
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_value(raw_value: str, target_type):
    origin = get_origin(target_type)
    normalized_type = get_args(target_type)[
        0] if origin is not None else target_type

    converters = {
        bool: _to_bool,
        int: int,
        float: float,
    }
    return converters.get(normalized_type, str)(raw_value)


def _env_for_field(
    field_name: str,
    current_path: tuple[str, ...],
    env_overrides: dict[str, str] | None,
    metadata_env: str | None,
):
    if not env_overrides:
        return metadata_env

    joined_path = ".".join((*current_path, field_name))
    return (
        env_overrides.get(joined_path) or env_overrides.get(
            field_name) or metadata_env
    )


def _default_for_field(item):
    if item.default is not MISSING:
        return item.default
    if item.default_factory is not MISSING:  # type: ignore[attr-defined]
        return item.default_factory()  # type: ignore[misc]
    raise ValueError(f"Missing required config field: {item.name}")


def _value_for_field(item, field_type, current_path, env_overrides):
    env_name = _env_for_field(
        item.name,
        current_path,
        env_overrides,
        item.metadata.get("env"),
    )
    if env_name and env_name in os.environ:
        return _coerce_value(os.environ[env_name], field_type)
    return _default_for_field(item)


def _build_dataclass(
    dataclass_type,
    env_overrides: dict[str, str] | None = None,
    current_path: tuple[str, ...] = (),
):
    values: dict[str, Any] = {}
    env_overrides = env_overrides or {}

    for item in fields(dataclass_type):
        field_type = item.type
        if is_dataclass(field_type):
            values[item.name] = _build_dataclass(
                field_type,
                env_overrides,
                (*current_path, item.name),
            )
        else:
            try:
                values[item.name] = _value_for_field(
                    item,
                    field_type,
                    current_path,
                    env_overrides,
                )
            except ValueError as error:
                raise ValueError(
                    f"Missing required config field: {dataclass_type.__name__}.{item.name}"
                ) from error

    return dataclass_type(**values)


def load_config() -> UnifiedConfig:
    env_overrides = {
        "firmware.defaults.country": "DEFAULT_CC",
        "firmware.defaults.city": "DEFAULT_CITY",
        "firmware.defaults.latitude": "DEFAULT_LAT",
        "firmware.defaults.longitude": "DEFAULT_LON",
        "firmware.providers.electricity_maps.enabled": "EM_ENABLED",
        "firmware.providers.electricity_maps.token": "EM_TOKEN",
        "firmware.providers.electricity_maps.base_url": "EM_BASE",
        "firmware.providers.watttime.username": "WATTTIME_USERNAME",
        "firmware.providers.watttime.password": "WATTTIME_PASSWORD",
        "firmware.providers.watttime.base_url": "WT_BASE",
    }
    return _build_dataclass(UnifiedConfig, env_overrides)


CONFIG = load_config()
