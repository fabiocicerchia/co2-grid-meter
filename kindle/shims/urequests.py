"""The slice of MicroPython's `urequests` that pico/ uses, over urllib.

`get(url, headers=, auth=(user, password), timeout=)` and a response with
`status_code`, `content`, `text`, `json()` and `close()`. An HTTP error status
comes back as a response, not an exception, as it does on the device: the
providers check `status_code` themselves.
"""

import base64
import json
import ssl
import urllib.error
import urllib.request

# The Kindle's own CA bundle dates from its last firmware; NiLuJe's Python
# ships certifi, which is current. Falls back to the system store elsewhere.
try:
    import certifi

    _TLS = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _TLS = ssl.create_default_context()


class Response:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content)

    def close(self):
        pass


def get(url, headers=None, auth=None, timeout=None):
    headers = dict(headers or {})
    # urllib's default "Python-urllib/3.x" is refused outright by some APIs
    # (the Carbon Intensity API answers 403); the device sends none at all.
    headers.setdefault("User-Agent", "co2-grid-meter")
    if auth:
        token = base64.b64encode(("%s:%s" % auth).encode()).decode()
        headers["Authorization"] = "Basic " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_TLS) as response:
            return Response(response.status, response.read())
    except urllib.error.HTTPError as error:
        return Response(error.code, error.read())
