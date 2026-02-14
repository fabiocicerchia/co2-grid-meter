"""WattTime provider for firmware."""

import time

try:
    import ubinascii
except Exception:
    ubinascii = None

try:
    import urequests as requests
except Exception:
    requests = None

import fw_config
from fw_utils import ProviderError, epoch_to_iso_z, safe_float

_watttime_disabled_until = 0


def _watttime_allowed_now():
    return time.time() >= _watttime_disabled_until


def _watttime_disable_for_a_day():
    global _watttime_disabled_until
    _watttime_disabled_until = (
        time.time() + fw_config.CONFIG.providers.watttime_cooldown_sec
    )


def _basic_auth_header(user, password):
    if not ubinascii:
        return None
    auth_raw = ("%s:%s" % (user, password)).encode()
    auth_base64 = ubinascii.b2a_base64(auth_raw).strip().decode()
    return "Basic " + auth_base64


def _watttime_login_token():
    if not requests:
        raise ProviderError("urequests not available")

    auth_header = _basic_auth_header(
        fw_config.CONFIG.providers.watttime.username,
        fw_config.CONFIG.providers.watttime.password,
    )
    if not auth_header:
        raise ProviderError("Missing ubinascii for Basic auth")

    response = None
    try:
        response = requests.get(
            fw_config.CONFIG.providers.watttime.base_url + "/login",
            headers={"Authorization": auth_header},
        )
        if response.status_code != 200:
            raise ProviderError("WattTime login HTTP %d" % response.status_code)
        token = (response.json() or {}).get("token")
        if not token:
            raise ProviderError("WattTime login missing token")
        return token
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass


def _watttime_grid_region(lat, lon, token):
    response = None
    try:
        response = requests.get(
            fw_config.CONFIG.providers.watttime.base_url + "/v2/ba-from-loc",
            headers={"Authorization": "Bearer " + token},
            params={"latitude": str(lat), "longitude": str(lon)},
        )
        if response.status_code != 200:
            raise ProviderError("WattTime region HTTP %d" % response.status_code)

        payload = response.json() or {}
        region = payload.get("ba") or payload.get("region")
        if not region:
            raise ProviderError("WattTime region missing ba")
        return region
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass


def fetch_watttime_current(lat, lon):
    if not requests:
        raise ProviderError("urequests not available")
    if not (
        fw_config.CONFIG.providers.watttime.enabled
        and fw_config.CONFIG.providers.watttime.username
        and fw_config.CONFIG.providers.watttime.password
    ):
        raise ProviderError("WattTime disabled/missing credentials")

    if not _watttime_allowed_now():
        raise ProviderError("WattTime temporarily disabled")

    token = _watttime_login_token()
    region = _watttime_grid_region(lat, lon, token)

    response = None
    try:
        response = requests.get(
            fw_config.CONFIG.providers.watttime.base_url + "/v2/index",
            headers={"Authorization": "Bearer " + token},
            params={"ba": region},
        )
        if response.status_code == 403:
            _watttime_disable_for_a_day()
            raise ProviderError("WattTime forbidden, cooling down")
        if response.status_code != 200:
            raise ProviderError("WattTime index HTTP %d" % response.status_code)

        payload = response.json() or {}
        value = safe_float(payload.get("moer"))
        if value is None:
            raise ProviderError("WattTime index missing moer")
        now_iso = epoch_to_iso_z(int(time.time()))
        return {
            "city": region,
            "history": [{"datetime": now_iso, "carbonIntensity": value}],
            "_provider": "watttime",
        }
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass
