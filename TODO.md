# TODO

Open items only. Completed work is dropped from here — the CHANGELOG
is the record of what shipped.

- [ ] Move `providers.ukci_enabled` under a `ukci` block, like every other
      provider.
- [ ] A setting to force a provider and a city, for testing a grid you are not in.
- [ ] Decide whether the 22-character truncation in `fw_render` is needed at all.
- [ ] Improve recommendation-string formatting path marked as potentially unnecessary.
- [ ] Refactor the `pico/` folder structure to better align with reusable firmware modules and deployment packaging.
- [ ] Add lightweight auth (token/basic auth) for HTTP endpoints when exposed outside trusted LAN.
