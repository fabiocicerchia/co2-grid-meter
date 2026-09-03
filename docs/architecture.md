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
  assembly and the provider cache.
- `pico/fw_render.py` — what the e-ink shows and when: the periodic refresh,
  the placeholder screen, and the 60-hour timeline the two series are sampled
  onto. Apart from `app.py` because it turns app's answers into a picture
  rather than producing them.
- `pico/providers/*` — one module per data source (UK Carbon Intensity,
  Carbon Intensity API, WattTime, ENTSO-E, Electricity Maps, CO2Signal,
  simulated fallback), tried in that order via `pico/fw_providers.py`.
  Sources that publish only a current value (CO2Signal) extend
  `SampledProvider`, which polls on a cooldown and keeps its own rolling store
  on flash — the device needs a curve to rank hours against, and those APIs
  answer "what is it now" and nothing else.
- `pico/ci_api_parse.py` — payload handling for the Carbon Intensity API,
  kept free of MicroPython imports so it is unit-tested under CPython.
- `pico/recommendation.py` — turns current intensity + a week-shifted
  overlay into a GO/WAIT verdict.
- `pico/ttl_cache.py` — TTL cache in front of provider calls, shared by
  firmware and mock, to avoid hammering upstream APIs on a Pico's limited
  RAM/bandwidth.
- `pico/display.py` — e-ink drawing primitives (panels, LEDs, icons, text).
- `pico/fw_graph.py` — the intensity plot: axes, series, percentile bands and
  day ticks. Apart from `display.py` because the primitives change when the
  panel does and this changes when the timeline does.
- `web/handler.py` — static asset serving + `/api/*` → Pico proxy with retry.
- `mock/handler.py` — same endpoint shapes as the firmware, backed by
  `pico/providers/simulated_provider.py` instead of real APIs.

## Data flow

```
[provider APIs] -> pico/providers -> pico/app.py (cache, recommend) -> pico/http.py -> browser
                                                  \-> pico/fw_render.py -> pico/display.py -> e-ink
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

## Project components

- `mock/mock_pico.py`: local Pico-compatible HTTP server.
- `mock/handler.py`: request routing for `/status`, `/em/window`, `/em/window-overlay`.
- `web/server.py` + `web/handler.py`: dashboard static server and `/api/*` proxy to Pico/mock Pico.
- `pico/firmware/*`: firmware HTTP endpoints, provider calls, recommendations, e-ink rendering.

## Caching and API pressure reduction

Both the mock server and firmware now use a **TTL cache** for endpoint payloads to reduce upstream API calls.

- Env var: `PICO_CACHE_REFRESH_SECONDS`
- Default: `3600` seconds (1 hour)

Example:

```bash
export PICO_CACHE_REFRESH_SECONDS=900  # refresh every 15 minutes
```

## Provider selection order

Provider fallback order remains:

1. UK Carbon Intensity (`GB/UK`)
2. Carbon Intensity API (if enabled — keyless, so there is no token to check)
3. WattTime (if enabled + credentials)
4. ENTSO-E (if token + mapped region)
5. Electricity Maps (if enabled + token)
6. Simulated fallback (`PICO_ALLOW_SIM_FALLBACK=1`)

### Carbon Intensity API

The provider talks to **v2** (`/v2/<CODE>/history/<YYYY-MM-DD>`, and
`/v2/<CODE>/<ZONE>/history/…` for a bidding zone). v1 is frozen upstream and
will be removed; it served one provider data point — 15 minutes wide for
ENTSO-E — under a name promising an hour, and no history at all, so the device
had to sample its own curve into existence over a week of uptime.

A v2 day document is columnar: one array per figure, index-aligned to the hour
beginning `start + i*3600`, with a **null for a missing hour that is present in
the array**. Compacting those nulls away would slide every later value into the
wrong hour, which is why `hour_points()` skips them by position.

The API is rate-limited to **1 request per 10s per IP** and asks callers to
cache what they fetch, so:

- `ci_api_days.json` on flash caches the figure's hourly array per UTC date. A
  past day never changes upstream and is fetched once; only today's document is
  re-read, because it grows an hour at a time.
- Requests are spaced ≥11s apart, so a cold start fills the two windows
  (`[-48h, now]` and the week-shifted overlay) over several refreshes instead
  of walking into 429s. A day that is rate-limited, absent (404) or malformed
  is skipped, not fatal — the window is drawn from the days already held.
- The store is keyed by country/zone and dropped when either changes: the
  cached arrays are one figure for one place.

Freshness is still the caller's to derive. `basis` must be `measured` — an
annual average is a yearly constant, and a timeline drawn from one is flat, so
every hour scores alike — and a window that ends at the present is refused when
its newest hour is over 65 minutes old. The overlay window is exempt: it is
seven days old by construction.

Upgrading a device that ran the v1 provider leaves an orphaned
`ci_api_store.json` on flash; delete it.
