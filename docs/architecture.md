# Architecture

## Overview

The project has three deployable pieces that share the same config schema
(`config/settings.py`, unified via `common_config.py`):

- **Firmware** (`pico/`) — runs on the Pico W itself (MicroPython). Serves
  `/status`, `/em/window`, `/em/window-overlay`, `/system-info` and `/html/*`
  over a raw socket HTTP server, fetches grid data from providers, computes a
  run/wait recommendation, and renders it to the e-ink display.
- **Mock Pico** (`mock/`) — a desktop stand-in for the firmware's HTTP API,
  used for local development of the dashboard without hardware.
- **Dashboard** (`web/`) — serves the static dashboard UI and proxies
  `/api/*` calls to either the mock or a real Pico (`PICO_BASE_URL`).

## Components

- `pico/http.py` — request routing and the socket server loop.
- `pico/app.py` — endpoint handlers, geo resolution, status/window/overlay
  assembly, e-ink render scheduling.
- `pico/providers/*` — one module per data source (UK Carbon Intensity,
  WattTime, ENTSO-E, Electricity Maps, simulated fallback), tried in that
  order via `pico/fw_providers.py`.
- `pico/recommendation.py` — turns current intensity + a week-shifted
  overlay into a GO/WAIT verdict.
- `pico/ttl_cache.py` — TTL cache in front of provider calls, shared by
  firmware and mock, to avoid hammering upstream APIs on a Pico's limited
  RAM/bandwidth.
- `pico/display.py` — e-ink drawing primitives (panels, graph, LEDs, icons).
- `web/handler.py` — static asset serving + `/api/*` → Pico proxy with retry.
- `mock/handler.py` — same endpoint shapes as the firmware, backed by
  `pico/providers/simulated_provider.py` instead of real APIs.

## Data flow

```
[provider APIs] -> pico/providers -> pico/app.py (cache, recommend) -> pico/http.py -> device / browser
                                                                              ^
                                                          web/handler.py proxies /api/* here
```

The dashboard never talks to provider APIs directly — it only ever proxies to
a Pico (real or mock), which is the single point that resolves geo, calls
providers, and caches.

## Decisions

- **Flat MicroPython imports.** `pico/*.py` modules import each other by bare
  module name (e.g. `from config import CONFIG`) because that's how files get
  laid out on the Pico's flat filesystem once deployed. This is why `pico/`
  isn't unit-tested the same way as `web/`/`mock/` — those flat imports don't
  resolve as a normal Python package on desktop.
- **TTL cache, not a database.** State only needs to live for the cache
  window; a dict-based cache keeps the firmware's memory footprint small and
  avoids flash writes for anything not explicitly logged.
