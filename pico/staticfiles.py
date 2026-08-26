"""Serving the dashboard's own files from the Pico, for an offline install.

The dashboard otherwise needs the desktop server running somewhere. On a device
that is already an HTTP server, that is a second machine for no reason — so the
same `web/static` files can be copied to the Pico and served from it.

The whole of this module is the part that is easy to get wrong: mapping a URL
to a file. Two rules it exists to enforce.

**A request can only reach the static root.** `..`, an absolute path, a
backslash, a percent-encoded separator — all rejected before anything touches
the filesystem. The Pico's flash holds `settings.json` (Wi-Fi password, provider
tokens) and the crash dumps, and a traversal bug on a device with no user
accounts hands over all of it.

**Files are streamed, not read.** A 15 KB script read into a variable on a
device with tens of KB of usable heap is a memory failure during a page load;
worse, it stalls the refresh loop while it happens. The reader yields chunks so
the socket drains as it goes.

No MicroPython-only imports, so this is testable under CPython.
"""

# Only what the dashboard actually ships. An unknown extension is refused
# rather than served as octet-stream: this directory holds four files, and
# anything else appearing in it is a mistake worth noticing.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
}

DEFAULT_FILE = "index.html"

# Read size. Small enough that one chunk cannot exhaust the heap, large enough
# that a 15 KB file is not 1500 socket writes.
CHUNK = 1024


def content_type(name):
    """MIME type for a filename, or None if the extension is not served."""
    dot = name.rfind(".")
    if dot < 0:
        return None
    return CONTENT_TYPES.get(name[dot:].lower())


def _unquote(text):
    """Minimal percent-decoding, so an encoded traversal cannot slip past.

    The check has to run on what the filesystem would see, not on what the URL
    looks like: `%2e%2e%2f` is `../` by the time anything opens it.
    """
    out, i = [], 0
    while i < len(text):
        if text[i] == "%" and i + 2 < len(text):
            try:
                out.append(chr(int(text[i + 1 : i + 3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        out.append(text[i])
        i += 1
    return "".join(out)


def resolve(root, url_path):
    """Map a URL path to a file under `root`, or None if it must not be served.

    None covers every refusal — traversal, an unserved extension, an absolute
    path — because the caller's only correct response to all of them is the
    same 404. Distinguishing them in the response would confirm which files
    exist to whoever is probing.
    """
    path = _unquote(url_path or "")
    path = path.split("?", 1)[0].split("#", 1)[0]

    if not path.startswith("/"):
        return None
    path = path[1:]
    if path == "" or path.endswith("/"):
        path += DEFAULT_FILE

    # Backslashes are separators on some hosts and would otherwise sneak past
    # a check that only knows about "/".
    if "\\" in path or path.startswith("/"):
        return None

    parts = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None  # refused outright rather than resolved and re-checked
        parts.append(part)
    if not parts:
        return None

    name = parts[-1]
    if content_type(name) is None:
        return None
    return root.rstrip("/") + "/" + "/".join(parts)


def etag(size, mtime):
    """A weak validator from what a Pico can cheaply know about a file.

    No hashing: the device has no spare cycles for it during a page load, and
    size+mtime changes for any edit that matters here. Quoted because an ETag
    that is not is silently ignored by some clients.
    """
    return '"%x-%x"' % (int(size), int(mtime))


def not_modified(request_etag, current_etag):
    """Whether a conditional GET can be answered with 304.

    Handles the `W/` prefix and a list of candidates, which is what a browser
    actually sends after a reload.
    """
    if not request_etag or not current_etag:
        return False
    for candidate in request_etag.split(","):
        candidate = candidate.strip()
        # Not str.removeprefix: MicroPython does not implement it, and this
        # module runs on the device. The tests run under CPython, where it
        # exists, so the failure would only ever have shown up on hardware.
        candidate = candidate.removeprefix("W/")
        if candidate == "*" or candidate == current_etag:
            return True
    return False


def chunks(fileobj, size=CHUNK):
    """Yield a file in pieces, so a 15 KB asset never exists in memory at once."""
    while True:
        block = fileobj.read(size)
        if not block:
            return
        yield block
