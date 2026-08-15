"""The text helpers lifted out of `pico/utils.py`.

Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow the
standard library's `http` package and break every other test in the run — the
same reason test_timeutil.py loads its module this way.

These were two `# TODO: Use library` blocks. There is no library to use on a
Pico — no `datetime`, no `urllib.parse` — so they are tested instead.
"""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "pico_textutil",
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "textutil.py",
)
_textutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_textutil)

iso_z_to_epoch = _textutil.iso_z_to_epoch
urlencode_simple = _textutil.urlencode_simple
_quote = _textutil._quote
_to_str = _textutil._to_str


class TestIsoToEpoch:
    def test_utc_z(self):
        # 2026-01-01T00:00:00Z is 1767225600 in any correct implementation.
        assert iso_z_to_epoch("2026-01-01T00:00:00Z") == 1767225600

    def test_fractional_seconds_are_dropped_not_rejected(self):
        # Electricity Maps sends these; before, a payload could parse as None.
        assert iso_z_to_epoch("2026-01-01T00:00:00.000Z") == 1767225600

    def test_positive_offset_is_subtracted(self):
        # 01:00+01:00 is midnight UTC.
        assert iso_z_to_epoch("2026-01-01T01:00:00+01:00") == 1767225600

    def test_negative_offset_is_added(self):
        # 19:00-05:00 the previous day is midnight UTC.
        assert iso_z_to_epoch("2025-12-31T19:00:00-05:00") == 1767225600

    def test_minutes_in_the_offset_count(self):
        assert iso_z_to_epoch("2026-01-01T05:30:00+05:30") == 1767225600

    def test_missing_seconds_default_to_zero(self):
        assert iso_z_to_epoch("2026-01-01T00:00Z") == 1767225600

    def test_garbage_is_none_rather_than_an_exception(self):
        # A provider that returns nonsense must not take the refresh loop down.
        for bad in ("", None, "not a timestamp", "2026-13-45T99:99:99Z"):
            assert iso_z_to_epoch(bad) is None


class TestQuoting:
    def test_escapes_what_would_change_a_query_string(self):
        assert _quote("a b") == "a%20b"
        assert _quote("a&b") == "a%26b"
        assert _quote("a=b") == "a%3Db"
        assert _quote("a+b") == "a%2Bb"
        assert _quote("a?b") == "a%3Fb"
        assert _quote("a#b") == "a%23b"

    def test_percent_is_escaped_first_so_it_is_not_double_encoded(self):
        # If "%" ran after " ", "a b" would become "a%2520b".
        assert _quote("100%") == "100%25"
        assert _quote("a %20 b") == "a%20%2520%20b"

    def test_bytes_and_none_are_coerced(self):
        assert _quote(b"a b") == "a%20b"
        assert _to_str(None) == ""
        assert _to_str(42) == "42"

    def test_undecodable_bytes_do_not_raise(self):
        assert isinstance(_to_str(b"\xff\xfe"), str)


class TestUrlencode:
    def test_pairs_are_joined_and_both_sides_escaped(self):
        assert urlencode_simple({"a b": "c&d"}) == "a%20b=c%26d"

    def test_order_follows_the_mapping(self):
        # Dicts preserve insertion order, and provider URLs are compared in
        # tests elsewhere, so the order must not depend on hashing.
        assert urlencode_simple({"z": 1, "a": 2}) == "z=1&a=2"

    def test_empty_mapping_is_an_empty_string(self):
        assert urlencode_simple({}) == ""
