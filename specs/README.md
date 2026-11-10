# Specifications of co2-grid-meter

What this code does, one atomic Gherkin scenario per behaviour, read from the code by code-atlas.
Tags: `@verified` a test asserts it · `@inferred` read from the code only · `@gap` an entry point no test covers · `@human` written or amended by a person, never rewritten.

## Grid Carbon Data
Getting carbon-intensity readings and forecasts for the device's grid from external providers.

- **Location detection**: [Working out which grid the device reports on](carbon-data/location/device-location.feature) (3)
- **Provider selection and fallback**: [Choosing the one provider that serves grid readings](carbon-data/provider-selection/provider-selection.feature) (7)
- **Data providers**: [Reading hourly grid intensity from the Carbon Intensity API](carbon-data/providers/ci-api-hourly-readings.feature) (6), [Reading grid carbon intensity from data providers](carbon-data/providers/grid-carbon-providers.feature) (8)

## Configuration
How the device and desktop apps are configured.

- **Application settings**: [Configuring the dashboard and mock device through environment variables](configuration/app-settings/desktop-environment-settings.feature) (5)
- **Device settings**: [Starting a device from its settings](configuration/device-settings/device-settings-at-boot.feature) (2), [Configuring a device through its settings file](configuration/device-settings/device-settings-file.feature) (6)
- **Time and text helpers**: [Keeping the device clock on local time across summer-time changes](configuration/shared-utilities/local-time-summer-time.feature) (2), [Reading provider timestamps and fitting device text](configuration/shared-utilities/provider-timestamps-and-device-text.feature) (6)

## Desktop Dashboard
The browser dashboard that visualises the device's data from a desktop.

- **Dashboard interface**: [Watching grid carbon intensity on the desktop dashboard](dashboard/dashboard-ui/dashboard-reading-and-controls.feature) (8)
- **Device proxy**: [Running the dashboard server](dashboard/device-proxy/dashboard-server-lifecycle.feature) (2)
- **Documentation site styling**: [Browsing the documentation site privately and on-brand](dashboard/docs-site/docs-site-look.feature) (2)

## Developer Tooling & Operations
Building, running and simulating the product without hardware.

- **Mock device**: [Serving simulated device data to the dashboard](developer-tooling/mock-device/mock-device-endpoints.feature) (6), [Running the mock Pico](developer-tooling/mock-device/mock-device-server.feature) (2)

## E-ink Display
What the Pico shows on its physical e-ink panel.

- **Intensity graph**: [Drawing the intensity graph on the e-ink panel](device-display/intensity-graph/intensity-graph.feature) (6)
- **Languages**: [Showing device text in the configured language](device-display/languages/device-languages.feature) (5)
- **Panel hardware**: [Showing a frame on the e-ink panel](device-display/panel-driver/eink-panel-output.feature) (2)
- **Screen layout**: [Showing the current reading and advice on the e-ink panel](device-display/screen-layout/current-reading-panel.feature) (5), [Showing the current reading and advice on the e-ink panel](device-display/screen-layout/eink-main-screen.feature) (6)

## Device Lifecycle
Bringing the Pico up, keeping it connected and keeping its firmware healthy.

- **Wi-Fi and clock**: [Keeping the device online and reachable](device-lifecycle/connectivity/device-reachability.feature) (3), [Joining Wi-Fi and reporting the connection](device-lifecycle/connectivity/wifi-connection.feature) (4)
- **Diagnostics**: [Boot diagnostics without leaking location or secrets](device-lifecycle/diagnostics/boot-diagnostics.feature) (5), [Keeping device logs and crash records](device-lifecycle/diagnostics/device-logs-and-crash-dumps.feature) (3), [Reporting device uptime](device-lifecycle/diagnostics/device-uptime.feature) (4)
- **Firmware updates**: [Checking a firmware update at power-on](device-lifecycle/firmware-updates/boot-update-check.feature) (2), [Updating firmware over the air](device-lifecycle/firmware-updates/firmware-updates.feature) (8)
- **Startup and main loop**: [Booting the device](device-lifecycle/startup/device-boot.feature) (5)

## Device Web & API
What the Pico serves over its own local network connection.

- **Data API**: [Restricting device access with an API token](device-web/data-api/device-api-token.feature) (4), [Reading grid intensity from the device API](device-web/data-api/device-data-api.feature) (7), [Answering requests on the device](device-web/data-api/device-http-routes.feature) (5)
- **Built-in pages**: [Viewing the device's built-in pages](device-web/device-pages/device-built-in-pages.feature) (6)
- **Home automation export**: [Exporting grid readings for home automation and spreadsheets](device-web/home-automation-export/home-automation-export.feature) (8)
- **Offline dashboard hosting**: [Hosting the dashboard from the device](device-web/offline-dashboard/offline-dashboard-hosting.feature) (6), [Serving the dashboard from the device](device-web/offline-dashboard/offline-dashboard-serving.feature) (1)

## Run/Wait Recommendation
Turning grid carbon intensity into advice on whether to use electricity now or wait.

- **Run or wait advice**: [Advising whether to run now or wait](recommendation/advice/run-or-wait-advice.feature) (2)
- **Best time to run**: [Telling the user when the next cleanest hour is](recommendation/best-time/best-time-to-run.feature) (3)
