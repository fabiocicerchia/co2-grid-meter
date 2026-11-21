"""The Kindle page: rendered server-side, so escaping is the part that matters."""

import importlib.util
import pathlib

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"
_spec = importlib.util.spec_from_file_location("pico_pages", PICO / "pages.py")
pages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pages)


def test_renders_status_with_refresh_and_no_script():
    html = pages.build_kindle_html(
        {
            "city": "London",
            "cc": "GB",
            "carbonIntensity": 123.4,
            "_provider": "ukci",
            "recommendation": {"verdict": "GO", "reason": "low", "wait_hours": 0, "next_best": "now"},
        }
    )
    assert '<meta http-equiv="refresh" content="300">' in html
    assert "123.4" in html
    assert 'class="verdict go"' in html
    assert "<script" not in html


def test_escapes_query_controlled_fields():
    html = pages.build_kindle_html({"city": "<script>x</script>", "cc": '"&'})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&quot;&amp;" in html


def test_missing_fields_render_placeholders():
    assert "--" in pages.build_kindle_html({})
