"""Configuration schema classes shared across application layers."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LocationDefaults:
    country: str = field(default="IT", metadata={"env": "DEFAULT_COUNTRY"})
    city: str = field(default="Rome", metadata={"env": "DEFAULT_CITY"})
    latitude: float = field(default=41.9028, metadata={"env": "DEFAULT_LAT"})
    longitude: float = field(default=12.4964, metadata={"env": "DEFAULT_LON"})


@dataclass(frozen=True)
class EntsoeSettings:
    token: str = field(default="", metadata={"env": "ENTSOE_TOKEN"})
    base_url: str = field(
        default="https://web-api.tp.entsoe.eu/api", metadata={"env": "ENTSOE_BASE"}
    )
    area_override: str = field(default="", metadata={"env": "ENTSOE_AREA"})


@dataclass(frozen=True)
class ElectricityMapsSettings:
    enabled: bool = field(default=False, metadata={
                          "env": "EM_ENABLED"})
    token: str = field(default="", metadata={"env": "ELECTRICITYMAPS_TOKEN"})
    base_url: str = field(
        default="https://api.electricitymap.org",
        metadata={"env": "ELECTRICITYMAPS_BASE"},
    )


@dataclass(frozen=True)
class WattTimeSettings:
    enabled: bool = field(default=False, metadata={
                          "env": "WT_ENABLED"})
    username: str = field(default="", metadata={"env": "WATTTIME_USERNAME"})
    password: str = field(default="", metadata={"env": "WATTTIME_PASSWORD"})
    signal: str = field(default="co2_moer", metadata={
                        "env": "WATTTIME_SIGNAL"})
    region_override: str = field(
        default="", metadata={"env": "WATTTIME_REGION"})
    region_by_country: bool = field(
        default=True, metadata={"env": "WATTTIME_REGION_BY_COUNTRY"}
    )
    base_url: str = field(
        default="https://api.watttime.org", metadata={"env": "WATTTIME_BASE"}
    )


@dataclass(frozen=True)
class SimProviderSettings:
    electricity_maps: ElectricityMapsSettings = field(
        default_factory=ElectricityMapsSettings
    )
    entsoe: EntsoeSettings = field(default_factory=EntsoeSettings)
    watttime: WattTimeSettings = field(default_factory=WattTimeSettings)
    allow_fallback: bool = field(
        default=True, metadata={"env": "PICO_ALLOW_SIM_FALLBACK"}
    )


@dataclass(frozen=True)
class SimServerSettings:
    host: str = field(default="127.0.0.1", metadata={"env": "HOST"})
    port: int = field(default=8080, metadata={"env": "PICO_PORT"})


@dataclass(frozen=True)
class MockConfig:
    server: SimServerSettings
    defaults: LocationDefaults
    providers: SimProviderSettings
    cache_refresh_seconds: int = field(
        default=3600, metadata={"env": "PICO_CACHE_REFRESH_SECONDS"}
    )

    @property
    def host(self):
        return self.server.host

    @property
    def port(self):
        return self.server.port


@dataclass(frozen=True)
class WebUpstreamSettings:
    pico_base_url: str = field(
        default="http://127.0.0.1:8080", metadata={"env": "PICO_BASE_URL"}
    )
    request_timeout_seconds: int = field(
        default=15, metadata={"env": "PICO_REQUEST_TIMEOUT_SEC"}
    )
    max_retries: int = field(default=3, metadata={
                             "env": "PICO_REQUEST_RETRIES"})


@dataclass(frozen=True)
class WebServerSettings:
    port: int = field(default=5000, metadata={"env": "WEB_PORT"})


@dataclass(frozen=True)
class WebLoggingSettings:
    level: str = field(default="INFO", metadata={"env": "LOG_LEVEL"})


@dataclass(frozen=True)
class WebConfig:
    upstream: WebUpstreamSettings
    server: WebServerSettings
    logging: WebLoggingSettings

    @property
    def port(self):
        return self.server.port


@dataclass(frozen=True)
class FirmwareWifiSettings:
    ssid: str = field(default="YOUR_WIFI_SSID", metadata={"env": "WIFI_SSID"})
    password: str = field(default="YOUR_WIFI_PASSWORD",
                          metadata={"env": "WIFI_PASS"})


@dataclass(frozen=True)
class FirmwareProviderSettings:
    ukci_enabled: bool = field(default=True, metadata={"env": "UKCI_ENABLED"})
    electricity_maps: ElectricityMapsSettings = field(
        default_factory=ElectricityMapsSettings)
    watttime: WattTimeSettings = field(default_factory=WattTimeSettings)
    watttime_cooldown_sec: int = field(
        default=24 * 3600, metadata={"env": "WT_COOLDOWN_SEC"}
    )


@dataclass(frozen=True)
class FirmwareTimelineSettings:
    back_hours_default: int = field(
        default=48, metadata={"env": "BACK_HOURS_DEFAULT"})
    past_hours: int = field(default=36, metadata={"env": "PAST_HOURS"})
    future_hours: int = field(default=12, metadata={"env": "FUTURE_HOURS"})
    lookahead_hours: int = field(
        default=12, metadata={"env": "LOOKAHEAD_HOURS"})


@dataclass(frozen=True)
class FirmwareThresholdSettings:
    green_percentile_max: float = field(
        default=0.33, metadata={"env": "P_GREEN_MAX"})
    yellow_percentile_max: float = field(
        default=0.66, metadata={"env": "P_YELLOW_MAX"})


@dataclass(frozen=True)
class FirmwareServerSettings:
    host: str = field(default="0.0.0.0", metadata={"env": "HOST"})
    port: int = field(default=8080, metadata={"env": "PICO_PORT"})


@dataclass(frozen=True)
class FirmwareDisplaySettings:
    render_min_interval_sec: int = field(
        default=60, metadata={"env": "RENDER_MIN_INTERVAL_SEC"}
    )


@dataclass(frozen=True)
class FirmwareConfig:
    wifi: FirmwareWifiSettings
    defaults: LocationDefaults
    providers: FirmwareProviderSettings
    timeline: FirmwareTimelineSettings
    thresholds: FirmwareThresholdSettings
    server: FirmwareServerSettings
    display: FirmwareDisplaySettings
    cache_refresh_seconds: int = field(
        default=3600, metadata={"env": "PICO_CACHE_REFRESH_SECONDS"}
    )


@dataclass(frozen=True)
class UnifiedConfig:
    mock: MockConfig
    web: WebConfig
    firmware: FirmwareConfig
