"""Reading the six fields ENTSO-E's A75 document actually carries here.

The previous path ran the whole response through `xmltok`, a general XML
tokenizer, which emits an event for every tag, attribute and text node in a
document that is mostly `<Point><position>N</position><quantity>x</quantity>`
repeated a few thousand times. On a Pico that is a stalled refresh loop, and
`pico/config.py` said as much in a TODO.

Nothing here needs a general parser. Six fields are consumed — psrType, start,
end, resolution, position, quantity — and every one of them is a text node
inside a tag with no attributes. So this scans for those six tags directly with
`str.find`, which is a C-level search in MicroPython, and yields them in
document order. Everything else in the document is skipped without being
tokenised at all.

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


def iter_events(text):
    """Yield ("open"|"close", tag) and ("text", tag, value) in document order.

    One pass, no allocation per tag beyond the values themselves. Unknown tags
    are skipped: the scan jumps from one interesting `<` to the next rather
    than walking the characters between them.
    """
    n = len(text)
    i = 0
    while i < n:
        lt = text.find("<", i)
        if lt < 0:
            return
        gt = text.find(">", lt + 1)
        if gt < 0:
            return
        raw = text[lt + 1 : gt]
        i = gt + 1

        if not raw or raw[0] in "?!":
            continue  # declaration, comment, doctype

        closing = raw[0] == "/"
        if closing:
            raw = raw[1:]
        # Self-closing tags carry no text, and no field this reads is ever one.
        self_closing = raw.endswith("/")
        if self_closing:
            raw = raw[:-1]

        # Strip attributes and any namespace prefix.
        space = raw.find(" ")
        if space >= 0:
            raw = raw[:space]
        colon = raw.rfind(":")
        if colon >= 0:
            raw = raw[colon + 1 :]

        if raw in STRUCTURE:
            if self_closing:
                continue
            yield ("close" if closing else "open", raw)
            continue

        if closing or raw not in FIELDS:
            continue

        # A field: its text runs to the next "<".
        end = text.find("<", i)
        if end < 0:
            return
        value = text[i:end].strip()
        i = end
        if value:
            yield ("text", raw, value)


def parse_series(text):
    """Group the events into series -> periods -> points.

    Returns a list of dicts:
        {"psr": "B01", "start": "...", "end": "...",
         "resolution": "PT60M", "points": [(position, quantity), ...]}

    The shape the caller already worked in, so the state machine around it does
    not change — only what feeds it.
    """
    series = []
    current = None
    period = None
    position = None
    quantity = None

    for event in iter_events(text):
        kind = event[0]
        if kind == "open":
            tag = event[1]
            if tag == "TimeSeries":
                current = {"psr": None, "periods": []}
                series.append(current)
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
    return series
