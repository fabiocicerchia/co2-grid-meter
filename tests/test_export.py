"""The CSV and compact-JSON export shapes.

Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow the
stdlib http package for the rest of the session. Same pattern as
test_textutil.py — except this module has one bare-name import of its own, so
pico/ goes on sys.path for the load and comes straight back off.
"""

import importlib.util
import pathlib
import sys

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"


def _load():
    sys.path.insert(0, str(PICO))
    try:
        spec = importlib.util.spec_from_file_location("pico_export", PICO / "export.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PICO))


export = _load()


def window(*points):
    return {"history": [{"datetime": iso, "carbonIntensity": v} for iso, v in points]}


WINDOW = window(
    ("2026-09-01T10:00:00Z", 430),
    ("2026-09-01T11:00:00Z", 412.5),
    ("2026-09-01T12:00:00Z", 380),
)


# ---- CSV -------------------------------------------------------------------
def test_csv_has_a_documented_header_and_one_row_per_point():
    lines = export.window_csv(WINDOW).split("\r\n")
    assert lines[0] == "datetime,epoch,carbon_intensity"
    assert lines[1] == "2026-09-01T10:00:00Z,1788256800,430"
    assert lines[4] == ""  # trailing CRLF, so the file ends on a line break
    assert len(lines) == 5


def test_csv_writes_whole_numbers_without_a_trailing_zero():
    # Most readings are integers; a spreadsheet column of "430" beats "430.0".
    body = export.window_csv(WINDOW)
    assert ",430\r\n" in body
    assert ",412.5\r\n" in body


def test_csv_is_bounded_and_keeps_the_newest_rows():
    # A Pico cannot serialise an unbounded response, and the recent end is the
    # half anyone polling for automation wants.
    big = window(*[(f"2026-09-{d + 1:02d}T00:00:00Z", 400 + d) for d in range(30)])
    rows = export.window_csv(big, max_rows=5).strip().split("\r\n")
    assert len(rows) == 6  # header + 5
    assert rows[1].endswith(",425") and rows[-1].endswith(",429")


def test_csv_drops_holes_rather_than_emitting_half_a_row():
    # A row that is half blank is worse than an absent row: the consumer plots
    # it as a zero.
    ragged = {
        "history": [
            {"datetime": "2026-09-01T10:00:00Z", "carbonIntensity": 430},
            {"datetime": "2026-09-01T11:00:00Z", "carbonIntensity": None},
            {"carbonIntensity": 400},
            {"datetime": "2026-09-01T13:00:00Z", "carbonIntensity": "nonsense"},
            {"datetime": "2026-09-01T14:00:00Z", "carbonIntensity": 390},
        ]
    }
    rows = export.window_csv(ragged).strip().split("\r\n")
    assert len(rows) == 3  # header + the two usable points
    assert rows[1].endswith(",430") and rows[2].endswith(",390")


def test_csv_of_an_empty_window_is_a_header_not_an_error():
    assert export.window_csv({"history": []}) == "datetime,epoch,carbon_intensity\r\n"
    assert export.window_csv({}) == "datetime,epoch,carbon_intensity\r\n"


def test_rows_come_out_in_time_order_whatever_the_provider_did():
    scrambled = window(
        ("2026-09-01T12:00:00Z", 380),
        ("2026-09-01T10:00:00Z", 430),
        ("2026-09-01T11:00:00Z", 412),
    )
    epochs = [row[1] for row in export.history_rows(scrambled["history"])]
    assert epochs == sorted(epochs)


# ---- compact summary -------------------------------------------------------
def test_summary_is_flat_and_carries_no_history():
    summary = export.summary_from_window(
        WINDOW,
        380,
        {"verdict": "GOOD", "reason": "below the weekly median", "wait_hours": None},
        "2026-09-01T12:00:00Z",
        city="Lisbon",
        cc="PT",
        provider="electricity_maps",
        uptime_seconds=4210,
    )
    assert "history" not in summary
    assert summary["carbon_intensity"] == 380
    assert summary["unit"] == "gCO2eq/kWh"
    assert summary["verdict"] == "GOOD"
    assert summary["city"] == "Lisbon" and summary["cc"] == "PT"
    assert summary["provider"] == "electricity_maps"
    assert summary["uptime_seconds"] == 4210
    # The window's shape, which is what a rule branches on.
    assert summary["window_points"] == 3
    assert summary["window_min"] == 380 and summary["window_max"] == 430


def test_summary_survives_an_empty_window_and_a_missing_recommendation():
    summary = export.summary_from_window({}, None, None, "2026-09-01T12:00:00Z")
    assert summary["window_points"] == 0
    assert summary["window_min"] is None and summary["window_max"] is None
    assert summary["verdict"] is None and summary["wait_hours"] is None
