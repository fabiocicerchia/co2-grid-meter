# TODO

Open items only. Completed work is dropped from here — the CHANGELOG
is the record of what shipped.

- [ ] Replace placeholder runtime config values in `firmware.py` (`ssid`, provider toggles/tokens, fallback switches) with environment-based or persisted settings.
- [ ] Improve/replace the slow XML-based ENTSO-E path in `firmware.py`.
- [ ] Add/complete tests for currently flagged firmware behavior (including `# TODO: TEST IT`).
- [ ] Refactor duplicated firmware logic into shared libraries (`# TODO: Use library` occurrences).
- [ ] Fix provider region selection flow currently hardcoded to `CAISO_NORTH` in the WattTime branch.
- [ ] Revisit stale/unclear firmware TODO notes (for example `# TODO: WHY?!`) and either resolve or replace with actionable comments.
- [ ] Improve recommendation-string formatting path marked as potentially unnecessary.
- [ ] Handle timezone daylight-saving transitions correctly (`CEST/BST` and `GMT+1` daylight adjustments).
- [ ] Remove or justify `pico/__init__.py` currently marked for removal.
- [ ] Multithread
- [ ] Print uptime
- [ ] Add a graph page under `/html` for quick local visualization without the full dashboard.
- [ ] Add i18n support for dashboard UI and firmware-visible labels/messages.
- [ ] Print richer Pico system/network diagnostics (IP, geolocation summary, and ISP/provider) in startup logs and optionally on-device status endpoints.
- [ ] Persist crashdump details to Pico filesystem for post-mortem debugging.
- [ ] Persist rolling logs for the last 48 hours on filesystem with simple rotation.
- [ ] Serve the web static folder directly from Pico when resources permit (embedded/offline mode).
- [ ] Refactor the `pico/` folder structure to better align with reusable firmware modules and deployment packaging.
- [ ] Add lightweight auth (token/basic auth) for HTTP endpoints when exposed outside trusted LAN.
- [ ] Add OTA-safe update flow (staged firmware update + rollback marker on boot failure).
- [ ] Add data export endpoints (`/em/window.csv` and compact JSON summaries) for home-automation integrations.
