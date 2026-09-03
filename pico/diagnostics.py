"""What the firmware says about itself at boot.

Boot logged the IP and nothing else, which is the least useful subset: grid
intensity is derived from *where the device thinks it is*, so a wrong reading
is far more often a wrong geolocation than a wrong provider. The ISP matters
for the same reason — an IP-based lookup resolves to the ISP's egress, so a
device behind a VPN or a CGNAT gateway is priced against the wrong grid, and
the ISP name is the fastest way to see that has happened.

Two rules the shape of this module exists to enforce:

**Coarse location only.** City, region and country go in a log line; latitude
and longitude do not. A log is copied into issue reports and pastebins, and a
precise coordinate is a home address. The existing auto-geo line printed exact
coordinates, which this removes.

**Nothing from config.** These summaries are built from the network interface
and the geo payload only, so there is no path by which an API key reaches a log
line — the safest way to keep a credential out of the logs is for the code that
writes them to have no access to one.

No MicroPython-only imports, so it is testable under CPython, like timeutil.
"""

# ifconfig() returns (ip, netmask, gateway, dns) on every port that has it.
_IFCONFIG_FIELDS = ("ip", "netmask", "gateway", "dns")

# ipwho.is spells these one way and ip-api.com another; both are accepted so
# the mock and the device agree without a second code path.
_CITY_KEYS = ("city",)
_REGION_KEYS = ("region", "regionName", "region_name")
_COUNTRY_KEYS = ("country", "country_name")
_CC_KEYS = ("country_code", "countryCode")
_ISP_KEYS = ("isp", "org", "organization", "as")


def _first(payload, keys):
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        # ipwho.is nests the ISP under "connection".
        if isinstance(value, dict):
            inner = _first(value, keys)
            if inner:
                return inner
    return ""


def network_summary(ifconfig):
    """(ip, netmask, gateway, dns) -> a dict, tolerating a short tuple."""
    values = list(ifconfig or ())
    return {
        field: (
            values[i].strip() if i < len(values) and isinstance(values[i], str) else ""
        )
        for i, field in enumerate(_IFCONFIG_FIELDS)
    }


def geo_summary(payload):
    """The parts of an IP-geolocation payload that are safe to print.

    Deliberately no latitude or longitude. The caller still gets those from the
    payload for the actual grid lookup; they simply never reach a log line or
    the status endpoint through here.
    """
    payload = payload if isinstance(payload, dict) else {}
    connection = payload.get("connection")
    isp = _first(payload, _ISP_KEYS)
    if not isp and isinstance(connection, dict):
        isp = _first(connection, _ISP_KEYS)
    return {
        "city": _first(payload, _CITY_KEYS),
        "region": _first(payload, _REGION_KEYS),
        "country": _first(payload, _COUNTRY_KEYS),
        "country_code": _first(payload, _CC_KEYS).upper(),
        "isp": isp,
    }


def _unique(values):
    """The non-empty values, first occurrence only.

    A region repeated as the city ("Berlin, Berlin") reads like a bug, so the
    duplicate is dropped rather than printed twice.
    """
    seen, ordered = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def format_location(geo):
    """`Berlin, Berlin, Germany (DE)` — as much as is known, nothing invented."""
    geo = geo or {}
    text = ", ".join(
        _unique(geo.get(key) or "" for key in ("city", "region", "country"))
    )
    cc = geo.get("country_code") or ""
    if cc and cc not in text:
        text = ("%s (%s)" % (text, cc)) if text else cc
    return text or "unknown"


def boot_lines(net, geo, uptime_text=""):
    """The lines to log at startup, in the order they are most useful."""
    net = net or {}
    lines = [
        "Network: ip %s netmask %s gateway %s dns %s"
        % (
            net.get("ip") or "?",
            net.get("netmask") or "?",
            net.get("gateway") or "?",
            net.get("dns") or "?",
        )
    ]
    lines.append("Location: %s" % format_location(geo))
    isp = (geo or {}).get("isp")
    if isp:
        # Worth its own line: an unexpected ISP here is the usual explanation
        # for a location that looks wrong.
        lines.append("ISP: %s" % isp)
    if uptime_text:
        lines.append("Uptime: %s" % uptime_text)
    return lines
