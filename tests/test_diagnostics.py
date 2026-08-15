"""Boot diagnostics: what gets logged, and what must never be.

Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow the
standard library's `http` package and break every other test in the run.
"""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "pico_diagnostics",
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "diagnostics.py",
)
_diag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_diag)

network_summary = _diag.network_summary
geo_summary = _diag.geo_summary
format_location = _diag.format_location
boot_lines = _diag.boot_lines

# The two payload shapes in play: ipwho.is on the device, ip-api.com in the mock.
IPWHO = {
    "ip": "203.0.113.9",
    "success": True,
    "city": "Berlin",
    "region": "Berlin",
    "country": "Germany",
    "country_code": "DE",
    "latitude": 52.52,
    "longitude": 13.405,
    "connection": {"asn": 3320, "org": "Deutsche Telekom AG", "isp": "Telekom"},
}

IPAPI = {
    "status": "success",
    "city": "Lisbon",
    "regionName": "Lisbon",
    "country": "Portugal",
    "countryCode": "PT",
    "lat": 38.7,
    "lon": -9.14,
    "isp": "MEO",
}


class TestNetworkSummary:
    def test_reads_the_whole_ifconfig(self):
        got = network_summary(
            ("192.168.1.50", "255.255.255.0", "192.168.1.1", "1.1.1.1")
        )
        assert got == {
            "ip": "192.168.1.50",
            "netmask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "dns": "1.1.1.1",
        }

    def test_a_short_or_missing_tuple_is_blank_not_an_error(self):
        # A port that returns fewer fields must not take the boot down.
        assert network_summary(("10.0.0.2",))["gateway"] == ""
        assert network_summary(())["ip"] == ""
        assert network_summary(None)["ip"] == ""


class TestGeoSummary:
    def test_no_coordinates_survive_either_payload(self):
        for payload in (IPWHO, IPAPI):
            summary = geo_summary(payload)
            flat = repr(summary)
            assert "52.52" not in flat and "13.405" not in flat
            assert "38.7" not in flat and "-9.14" not in flat
            assert "latitude" not in summary and "lat" not in summary

    def test_reads_both_provider_spellings(self):
        assert geo_summary(IPWHO)["region"] == "Berlin"
        assert geo_summary(IPAPI)["region"] == "Lisbon"
        assert geo_summary(IPWHO)["country_code"] == "DE"
        assert geo_summary(IPAPI)["country_code"] == "PT"

    def test_isp_is_found_whether_nested_or_flat(self):
        assert geo_summary(IPWHO)["isp"] == "Telekom"
        assert geo_summary(IPAPI)["isp"] == "MEO"

    def test_an_empty_or_junk_payload_is_empty_not_an_error(self):
        for junk in ({}, None, {"city": ""}, "not a dict"):
            assert geo_summary(junk)["city"] == ""


class TestFormatting:
    def test_full_location(self):
        assert format_location(geo_summary(IPAPI)) == "Lisbon, Portugal (PT)"

    def test_a_repeated_region_is_not_printed_twice(self):
        # ipwho.is gives city == region for city-states; "Berlin, Berlin,
        # Germany" reads like a bug.
        assert format_location(geo_summary(IPWHO)) == "Berlin, Germany (DE)"

    def test_partial_data_prints_what_is_known(self):
        assert format_location({"country_code": "FR"}) == "FR"
        assert format_location({"city": "Oslo"}) == "Oslo"

    def test_nothing_known_says_so(self):
        assert format_location({}) == "unknown"
        assert format_location(None) == "unknown"


class TestBootLines:
    def test_covers_what_the_issue_asked_for(self):
        net = network_summary(
            ("192.168.1.50", "255.255.255.0", "192.168.1.1", "1.1.1.1")
        )
        lines = boot_lines(net, geo_summary(IPWHO))
        joined = "\n".join(lines)
        assert "192.168.1.50" in joined
        assert "255.255.255.0" in joined and "192.168.1.1" in joined
        assert "Berlin, Germany (DE)" in joined
        assert "Telekom" in joined

    def test_never_logs_a_coordinate(self):
        joined = "\n".join(boot_lines(network_summary(()), geo_summary(IPWHO)))
        assert "52.52" not in joined and "13.405" not in joined

    def test_missing_pieces_degrade_to_placeholders(self):
        # No network, no geo: still one readable line each, no exception.
        lines = boot_lines({}, {})
        assert lines[0].startswith("Network: ip ?")
        assert lines[1] == "Location: unknown"

    def test_isp_line_is_omitted_when_unknown(self):
        assert not any(
            line.startswith("ISP:") for line in boot_lines({}, {"city": "Oslo"})
        )
