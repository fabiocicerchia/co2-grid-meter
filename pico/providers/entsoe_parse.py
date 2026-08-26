"""Reading the six fields ENTSO-E's A75 document actually carries here.

The original path ran the whole response through `xmltok`, a general XML
tokenizer, which emits an event for every tag, attribute and text node in a
document that is mostly `<Point><position>N</position><quantity>x</quantity>`
repeated a few thousand times. On a Pico that is a stalled refresh loop, and
`pico/config.py` said as much in a TODO.

Nothing here needs a general parser. Six fields are consumed — psrType, start,
end, resolution, position, quantity — and every one of them is a text node
inside a tag with no attributes. So this scans for those six tags directly with
`find`, which is a C-level search in MicroPython, and yields them in document
order. Everything else in the document is skipped without being tokenised.

**The document is never held whole.** That is the constraint the CPU win has to
respect, not a detail: a 60-hour window over a zone that publishes at PT15M is
a 180-250 KB response, and a Pico W has 264 KB of SRAM in total. So the scan
runs over a sliding window fed from the socket in `CHUNK`-sized reads, and
`iter_series` yields each TimeSeries as its closing tag arrives, so the caller
can fold it into its hourly buckets and let it go. Peak memory is one window
plus one series, not one document plus a parse tree of it.

The scan works in bytes rather than str for the same reason: decoding the
stream chunk by chunk can split a multi-byte character across a read boundary,
and only the short values that are actually yielded need to be text at all.

What is given up, stated plainly: this is not an XML parser and would be wrong
on a document that used attributes on these tags, CDATA, or comments containing
one of the six names. ENTSO-E's A75 uses none of those — it is machine-
generated from a fixed schema — and the parser fails closed by yielding
nothing rather than yielding something wrong.

No MicroPython-only imports, so it is testable under CPython.
"""

# The only tags whose text is read. Ordered longest-first so a scan for
# `position` cannot match inside `positions` — none exists today, but the cost
# of the ordering is nothing and the cost of being wrong is a silent misparse.
FIELDS = ("resolution", "quantity", "position", "psrType", "start", "end")

# Structural tags, needed only to know which TimeSeries/Period a field belongs
# to. Their text is never read.
STRUCTURE = ("TimeSeries", "Period", "Point")

_FIELDS = tuple(name.encode() for name in FIELDS)
_STRUCTURE = tuple(name.encode() for name in STRUCTURE)

# Socket read size. Small enough that the window stays cheap, large enough that
# a 200 KB response is not 200k syscalls.
CHUNK = 512

# No tag or field value in an A75 comes close to this. A span longer than it
# means the document is not what this expects, and the scan stops rather than
# growing the window to hold whatever it is.
MAX_SPAN = 8192


class _Cursor:
    """A sliding window over a byte stream.

    Bytes are pulled in chunks, scanned, and dropped once the cursor has passed
    them, so the peak is the window rather than the document. Accepts a str or
    bytes too, which is what the tests use and what a caller falls back to when
    the response object has no readable `raw`.
    """

    def __init__(self, source, chunk=CHUNK):
        self._read = getattr(source, "read", None)
        self._chunk = chunk
        self._pos = 0
        if self._read is None:
            self._buf = source.encode() if isinstance(source, str) else source or b""
            self._eof = True
        else:
            self._buf = b""
            self._eof = False

    def _more(self):
        """Pull another chunk onto the window. False once the stream is done."""
        if self._eof:
            return False
        block = self._read(self._chunk)
        if not block:
            self._eof = True
            return False
        self._buf += block.encode() if isinstance(block, str) else block
        return True

    def find(self, needle, start=None):
        """Index of `needle` at or after `start`, reading more as required.

        -1 means the stream ended first, or that the span grew past MAX_SPAN
        without a match — both of which end the scan.
        """
        at = self._pos if start is None else start
        while True:
            found = self._buf.find(needle, at)
            if found >= 0:
                return found
            if len(self._buf) - at > MAX_SPAN:
                return -1
            if not self._more():
                return -1

    def slice(self, start, end):
        return self._buf[start:end]

    @property
    def pos(self):
        return self._pos

    def seek(self, index):
        """Advance the cursor, compacting the window behind it.

        Indices taken before a seek are invalid after one — every caller here
        seeks last, once it is done with the slice it took.
        """
        self._pos = index
        if self._pos > self._chunk:
            self._buf = self._buf[self._pos :]
            self._pos = 0


def _text(raw):
    """A short ASCII value to str, without assuming the bytes decode."""
    try:
        return raw.decode().strip()
    except Exception:
        return ""


def iter_events(source):
    """Yield ("open"|"close", tag) and ("text", tag, value) in document order.

    One pass. Unknown tags are skipped: the scan jumps from one interesting
    `<` to the next rather than walking the characters between them.
    """
    cur = _Cursor(source)
    while True:
        lt = cur.find(b"<")
        if lt < 0:
            return
        gt = cur.find(b">", lt + 1)
        if gt < 0:
            return
        raw = cur.slice(lt + 1, gt)
        cur.seek(gt + 1)

        if not raw or raw[0:1] in (b"?", b"!"):
            continue  # declaration, comment, doctype

        closing = raw[0:1] == b"/"
        if closing:
            raw = raw[1:]
        # Self-closing tags carry no text, and no field this reads is ever one.
        self_closing = raw.endswith(b"/")
        if self_closing:
            raw = raw[:-1]

        # Strip attributes and any namespace prefix.
        space = raw.find(b" ")
        if space >= 0:
            raw = raw[:space]
        colon = raw.rfind(b":")
        if colon >= 0:
            raw = raw[colon + 1 :]

        if raw in _STRUCTURE:
            if self_closing:
                continue
            yield ("close" if closing else "open", raw.decode())
            continue

        if closing or raw not in _FIELDS:
            continue

        # A field: its text runs to the next "<".
        end = cur.find(b"<")
        if end < 0:
            return
        value = _text(cur.slice(cur.pos, end))
        cur.seek(end)
        if value:
            yield ("text", raw.decode(), value)


def iter_series(source):
    """Yield each TimeSeries as its closing tag arrives.

    Each is a dict:
        {"psr": "B01",
         "periods": [{"start": ..., "end": ..., "resolution": ...,
                      "points": [(position, quantity), ...]}]}

    Yielded rather than collected so the caller can fold a series into its
    buckets and drop it. Holding all of them was the whole memory problem.
    """
    current = None
    period = None
    position = None
    quantity = None

    for event in iter_events(source):
        kind = event[0]
        if kind == "open":
            tag = event[1]
            if tag == "TimeSeries":
                current = {"psr": None, "periods": []}
            elif tag == "Period" and current is not None:
                period = {"start": None, "end": None, "resolution": None, "points": []}
                current["periods"].append(period)
            elif tag == "Point":
                position = quantity = None
        elif kind == "close":
            tag = event[1]
            if tag == "Point" and period is not None:
                if position is not None and quantity is not None:
                    period["points"].append((position, quantity))
                position = quantity = None
            elif tag == "Period":
                period = None
            elif tag == "TimeSeries":
                if current is not None:
                    yield current
                current = None
        else:
            _, tag, value = event
            if tag == "psrType" and current is not None:
                current["psr"] = value
            elif period is not None:
                if tag == "start" and period["start"] is None:
                    period["start"] = value
                elif tag == "end" and period["end"] is None:
                    period["end"] = value
                elif tag == "resolution":
                    period["resolution"] = value
                elif tag == "position":
                    try:
                        position = int(value)
                    except ValueError:
                        position = None
                elif tag == "quantity":
                    try:
                        quantity = float(value)
                    except ValueError:
                        quantity = None

    # A truncated document — the connection dropped mid-series — still yields
    # what was read, which is a partial curve rather than none at all.
    if current is not None:
        yield current


def parse_series(source):
    """Every series at once. Convenience for the tests; the firmware streams.

    Materialises the whole parse tree, so a caller on the device should use
    `iter_series` instead — see the module docstring for what that costs.
    """
    return list(iter_series(source))
