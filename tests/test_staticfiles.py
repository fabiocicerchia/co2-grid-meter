"""Serving the dashboard from the Pico.

Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow the
standard library's `http` package and break every other test in the run.

Most of this file is traversal. The Pico's flash holds settings.json — Wi-Fi
password, provider tokens — and the crash dumps, on a device with no user
accounts, so a path that escapes the static root hands over all of it.
"""

import importlib.util
import io
import pathlib

_spec = importlib.util.spec_from_file_location(
    "pico_staticfiles",
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "staticfiles.py",
)
_static = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_static)

resolve = _static.resolve
content_type = _static.content_type
etag = _static.etag
not_modified = _static.not_modified
chunks = _static.chunks

ROOT = "static"


class TestResolve:
    def test_a_plain_file(self):
        assert resolve(ROOT, "/script.js") == "static/script.js"

    def test_the_root_serves_the_index(self):
        assert resolve(ROOT, "/") == "static/index.html"

    def test_a_subdirectory_is_allowed(self):
        assert resolve(ROOT, "/css/style.css") == "static/css/style.css"

    def test_a_query_string_is_not_part_of_the_path(self):
        # Cache-busting query strings are normal on assets.
        assert resolve(ROOT, "/script.js?v=3") == "static/script.js"

    def test_an_unserved_extension_is_refused(self):
        # settings.json is JSON and *is* a served type, which is exactly why
        # the traversal checks below matter more than the extension list.
        assert resolve(ROOT, "/secret.py") is None
        assert resolve(ROOT, "/id_rsa") is None


class TestTraversal:
    def test_dot_dot_is_refused(self):
        for path in (
            "/../settings.json",
            "/css/../../settings.json",
            "/..%2fsettings.json",
            "/%2e%2e/settings.json",
            "/%2e%2e%2fsettings.json",
        ):
            assert resolve(ROOT, path) is None, path

    def test_an_absolute_path_is_refused(self):
        assert resolve(ROOT, "//settings.json") is None
        assert resolve(ROOT, "/%2fsettings.json") is None

    def test_a_backslash_is_refused(self):
        # A separator on some hosts, and invisible to a check that only knows
        # about "/".
        assert resolve(ROOT, "/..\\settings.json") is None
        assert resolve(ROOT, "/css\\..\\..\\settings.json") is None

    def test_a_path_not_starting_with_a_slash_is_refused(self):
        assert resolve(ROOT, "script.js") is None
        assert resolve(ROOT, "") is None
        assert resolve(ROOT, None) is None

    def test_the_settings_file_cannot_be_reached_by_any_of_these(self):
        # The single assertion that matters: no accepted path escapes the root.
        for path in (
            "/../settings.json",
            "/./../settings.json",
            "/a/../../settings.json",
            "/%2e%2e%2f%2e%2e%2fsettings.json",
        ):
            got = resolve(ROOT, path)
            assert got is None or got.startswith("static/"), (path, got)


class TestContentTypes:
    def test_the_four_shipped_assets(self):
        assert content_type("index.html").startswith("text/html")
        assert content_type("style.css").startswith("text/css")
        assert content_type("script.js").startswith("text/javascript")
        assert content_type("graph.html").startswith("text/html")

    def test_case_is_ignored(self):
        assert content_type("INDEX.HTML").startswith("text/html")

    def test_an_unknown_extension_has_none(self):
        assert content_type("x.exe") is None
        assert content_type("noextension") is None


class TestConditionalGet:
    def test_an_etag_changes_with_size_or_mtime(self):
        base = etag(100, 200)
        assert etag(100, 200) == base
        assert etag(101, 200) != base
        assert etag(100, 201) != base

    def test_an_etag_is_quoted(self):
        assert etag(1, 2).startswith('"') and etag(1, 2).endswith('"')

    def test_matching_etag_is_not_modified(self):
        tag = etag(4643, 1_700_000_000)
        assert not_modified(tag, tag)

    def test_a_weak_validator_still_matches(self):
        tag = etag(1, 2)
        assert not_modified("W/" + tag, tag)

    def test_a_list_of_candidates_matches(self):
        tag = etag(1, 2)
        assert not_modified(f'"other", {tag}', tag)

    def test_a_wildcard_matches(self):
        assert not_modified("*", etag(1, 2))

    def test_a_different_etag_does_not(self):
        assert not not_modified(etag(1, 2), etag(3, 4))

    def test_no_header_does_not(self):
        assert not not_modified("", etag(1, 2))
        assert not not_modified(None, etag(1, 2))


class TestStreaming:
    def test_a_file_is_yielded_in_pieces(self):
        data = b"x" * 3000
        got = list(chunks(io.BytesIO(data), size=1024))
        assert len(got) == 3  # 1024 + 1024 + 952
        assert b"".join(got) == data
        assert max(len(block) for block in got) <= 1024

    def test_an_empty_file_yields_nothing(self):
        assert list(chunks(io.BytesIO(b""))) == []


def test_the_shipped_assets_fit_a_pico():
    """The size budget the issue asks the build to state.

    A Pico W has 2 MB of flash with roughly 800 KB free after MicroPython and
    this firmware. The dashboard is four files; if it ever stops fitting, this
    is where that is noticed.
    """
    web = pathlib.Path(__file__).resolve().parents[1] / "web" / "static"
    total = sum(f.stat().st_size for f in web.iterdir() if f.is_file())
    assert total < 200 * 1024, f"web/static is {total / 1024:.0f} KB — too big to flash"
