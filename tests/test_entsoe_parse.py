"""The ENTSO-E field scanner that replaced the xmltok tokenizer.

Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow the
standard library's `http` package and break every other test in the run.
"""

import importlib.util
import io
import pathlib
import random
import tracemalloc

_spec = importlib.util.spec_from_file_location(
    "pico_entsoe_parse",
    pathlib.Path(__file__).resolve().parents[1]
    / "pico"
    / "providers"
    / "entsoe_parse.py",
)
_parse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_parse)

parse_series = _parse.parse_series
iter_events = _parse.iter_events
iter_series = _parse.iter_series

# A trimmed A75, in the shape ENTSO-E actually sends: a default namespace, a
# nested MktPSRType, and one Period per TimeSeries.
DOC = """<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <mRID>abc</mRID>
  <TimeSeries>
    <mRID>1</mRID>
    <MktPSRType><psrType>B01</psrType></MktPSRType>
    <Period>
      <timeInterval><start>2026-08-15T00:00Z</start><end>2026-08-15T02:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><quantity>1000</quantity></Point>
      <Point><position>2</position><quantity>1200.5</quantity></Point>
    </Period>
  </TimeSeries>
  <TimeSeries>
    <mRID>2</mRID>
    <MktPSRType><psrType>B16</psrType></MktPSRType>
    <Period>
      <timeInterval><start>2026-08-15T00:00Z</start><end>2026-08-15T02:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><quantity>500</quantity></Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""


class TestParsing:
    def test_series_psr_and_points(self):
        series = parse_series(DOC)
        assert len(series) == 2
        assert [s["psr"] for s in series] == ["B01", "B16"]
        assert series[0]["periods"][0]["points"] == [(1, 1000.0), (2, 1200.5)]
        assert series[1]["periods"][0]["points"] == [(1, 500.0)]

    def test_period_interval_and_resolution(self):
        period = parse_series(DOC)[0]["periods"][0]
        assert period["start"] == "2026-08-15T00:00Z"
        assert period["end"] == "2026-08-15T02:00Z"
        assert period["resolution"] == "PT60M"

    def test_the_document_mrid_is_not_mistaken_for_a_field(self):
        # <mRID> appears at document level and inside every TimeSeries; none of
        # it is read, and it must not disturb the grouping.
        assert all(s["psr"] is not None for s in parse_series(DOC))

    def test_namespaced_tags(self):
        doc = DOC.replace("<TimeSeries>", "<ns:TimeSeries>").replace(
            "</TimeSeries>", "</ns:TimeSeries>"
        )
        assert len(parse_series(doc)) == 2

    def test_attributes_on_structural_tags(self):
        doc = DOC.replace("<Period>", '<Period id="p1">')
        assert parse_series(doc)[0]["periods"][0]["points"]

    def test_several_periods_in_one_series(self):
        doc = DOC.replace(
            "    </Period>\n  </TimeSeries>\n  <TimeSeries>",
            "    </Period>\n    <Period>"
            "<timeInterval><start>2026-08-15T02:00Z</start><end>2026-08-15T03:00Z</end></timeInterval>"
            "<resolution>PT60M</resolution>"
            "<Point><position>1</position><quantity>7</quantity></Point>"
            "</Period>\n  </TimeSeries>\n  <TimeSeries>",
            1,
        )
        assert len(parse_series(doc)[0]["periods"]) == 2


class TestRobustness:
    def test_an_empty_or_truncated_document_yields_nothing_rather_than_raising(self):
        assert parse_series("") == []
        assert parse_series("<GL_MarketDocument><TimeSeries><MktPSRType>") == [
            {"psr": None, "periods": []}
        ]

    def test_a_non_numeric_quantity_drops_the_point_not_the_document(self):
        doc = DOC.replace("<quantity>1000</quantity>", "<quantity>n/a</quantity>")
        points = parse_series(doc)[0]["periods"][0]["points"]
        assert points == [(2, 1200.5)]

    def test_comments_and_declarations_are_skipped(self):
        doc = DOC.replace("<mRID>abc</mRID>", "<!-- a comment --><mRID>abc</mRID>")
        assert len(parse_series(doc)) == 2

    def test_self_closing_tags_do_not_open_a_scope(self):
        doc = DOC.replace("<mRID>abc</mRID>", "<Reason/>")
        assert len(parse_series(doc)) == 2

    def test_not_xml_at_all(self):
        assert parse_series("<html><body>gateway timeout</body></html>") == []


def build_document(series=4, points=96):
    """A representative response: four production types, a day of 15-min points.

    `series` may exceed the four codes; they cycle. A real zone publishes ten
    to fifteen, and the memory tests need to vary the count independently of
    the points in each.
    """
    random.seed(7)
    codes = ("B01", "B04", "B16", "B19")
    parts = ['<?xml version="1.0"?>', "<GL_MarketDocument>"]
    for index in range(series):
        psr = codes[index % len(codes)]
        parts.append("<TimeSeries><mRID>1</mRID>")
        parts.append(f"<MktPSRType><psrType>{psr}</psrType></MktPSRType>")
        parts.append(
            "<Period><timeInterval><start>2026-08-15T00:00Z</start>"
            "<end>2026-08-16T00:00Z</end></timeInterval><resolution>PT15M</resolution>"
        )
        for pos in range(1, points + 1):
            parts.append(
                f"<Point><position>{pos}</position>"
                f"<quantity>{random.randint(100, 9000)}</quantity></Point>"
            )
        parts.append("</Period></TimeSeries>")
    parts.append("</GL_MarketDocument>")
    return "\n".join(parts)


def test_a_full_day_parses_completely():
    """The shape that was slow: ~25 KB, 384 points."""
    doc = build_document()
    series = parse_series(doc)
    assert len(series) == 4
    assert sum(len(p["points"]) for s in series for p in s["periods"]) == 384
    # Every quantity survived as a number, which is what the bucket fill needs.
    assert all(
        isinstance(q, float)
        for s in series
        for p in s["periods"]
        for _, q in p["points"]
    )


class TestStreaming:
    """The document must never be held whole.

    A 60-hour window over a zone publishing at PT15M is a 180-250 KB response
    and the board has 264 KB of SRAM in total, so reading the body into a
    string before parsing it is the difference between working and an
    allocation failure. These pin the property, not the implementation.
    """

    def test_a_stream_and_a_string_agree(self):
        doc = build_document()
        assert parse_series(io.BytesIO(doc.encode())) == parse_series(doc)

    def test_series_arrive_before_the_document_has_been_read(self):
        # The point of iter_series: the first TimeSeries is usable while the
        # rest of the response is still on the socket. If this ever buffers
        # the whole body first, the read position would be at EOF here.
        doc = build_document(series=4, points=96)
        raw = doc.encode()
        stream = io.BytesIO(raw)
        first = next(iter_series(stream))
        assert first["psr"] == "B01"
        assert stream.tell() < len(raw), "whole document was read before yielding"

    def test_peak_memory_does_not_track_document_size(self):
        # Points per series are held constant and only the number of series
        # varies, because that is the actual claim: one series is live at a
        # time, so a document with sixteen times as many costs the same.
        def peak(series, points):
            raw = build_document(series, points).encode()
            stream = io.BytesIO(raw)
            tracemalloc.start()
            for _ in iter_series(stream):
                pass
            _, high = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return len(raw), high

        _, small = peak(2, 96)
        size, large = peak(32, 96)
        # 16x the document, same peak. Anything that buffered the body would
        # show the ratio instead.
        assert large < small * 2, f"peak grew with the document: {small} -> {large}"
        # And the absolute claim the device depends on: the window is a small
        # fraction of the response, not a copy of it.
        assert large < size // 4, (
            f"peak {large} is not small against a {size} byte body"
        )

    def test_a_stream_that_stops_mid_document_yields_what_was_read(self):
        # A dropped connection is a partial curve, not an exception and not a
        # silent empty result.
        doc = build_document(series=4, points=96)
        truncated = doc.encode()[: len(doc) // 2]
        got = parse_series(io.BytesIO(truncated))
        assert 0 < len(got) < 4
        assert got[0]["periods"][0]["points"]

    def test_a_value_split_across_two_reads_is_not_corrupted(self):
        # The scan refills mid-token whenever a value straddles a chunk
        # boundary; a one-byte reader forces that on every single token.
        class Dribble:
            def __init__(self, data):
                self.data, self.i = data, 0

            def read(self, n):
                block = self.data[self.i : self.i + 1]
                self.i += len(block)
                return block

        doc = build_document(series=2, points=8)
        assert parse_series(Dribble(doc.encode())) == parse_series(doc)
