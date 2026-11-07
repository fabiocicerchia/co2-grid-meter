@domain:device-web @area:data-api @from:pico/app
Feature: Reading grid intensity from the device API
  Serves the dashboard, home-automation tools and operators with the device's current reading, recommendation, intensity windows and system state over its JSON API.

  Background:
    Given the device reports on "Rome", "IT"
    And the timeline shows 48 hours back and 12 hours ahead by default

  @id:device-web.data-api.001 @rule:device-web.data-api.window-covers-requested-hours @inferred @source:pico/app.py#handle_em_window
  Scenario Outline: The intensity window covers the requested number of past hours up to the current hour
    Given the current time is 2026-11-07T10:25:00Z
    When a client requests GET /em/window <query>
    Then the history runs hourly from <start> to 2026-11-07T10:00:00Z
    And the response names the provider that supplied it and the resolved city and country

    Examples:
      | query              | start                |
      | with back_hours=6  | 2026-11-07T04:00:00Z |
      | without back_hours | 2026-11-05T10:00:00Z |

  @id:device-web.data-api.002 @rule:device-web.data-api.overlay-is-same-timeline-a-week-earlier @inferred @source:pico/app.py#handle_em_overlay
  Scenario: The overlay shows the same timeline one week earlier
    Given the current time is 2026-11-07T10:25:00Z
    When a client requests GET /em/window-overlay
    Then the history runs from 2026-10-29T10:00:00Z to 2026-10-31T22:00:00Z

  @id:device-web.data-api.003 @rule:device-web.data-api.status-reports-latest-hour-and-advice @inferred @source:pico/app.py#build_status_bundle
  Scenario: The status reports the latest hour's intensity with a run or wait recommendation
    Given the latest hour in the past-48-hour window has an intensity of 210 gCO2/kWh
    And the provider "ci_api" supplied the window
    When a client requests GET /status
    Then carbonIntensity is 210
    And recommendation is the advice computed from last week's readings around this hour
    And _provider is "ci_api"
    And datetime is the current hour in UTC
    And uptime_seconds is the device's uptime in seconds

  @id:device-web.data-api.004 @rule:device-web.data-api.no-reading-is-an-error @inferred @source:pico/app.py#build_status_bundle @questionable
  Scenario Outline: The status is refused with a reason when there is no reading to report
    Given <situation>
    When a client requests GET /status
    Then the response status is 500
    And the error details read "<details>"

    Examples:
      | situation                                            | details                                    |
      | the first fetch for this window has not finished yet | No reading yet - first fetch still running |
      | the provider returned an empty window                | No window history                          |
      | the latest hour has no intensity value               | No carbonIntensity in last point           |

  @id:device-web.data-api.005 @rule:device-web.data-api.status-includes-resolved-coordinates @inferred @source:pico/app.py#build_status_bundle @questionable
  Scenario: The status and system information carry the resolved coordinates
    Given the device's public IP resolves to latitude 51.5072 and longitude -0.1276
    When a client requests GET /status
    Then lat is 51.5072 and lon is -0.1276
    And the diagnostics show only a coarse location, ISP and network interface

  @id:device-web.data-api.006 @rule:device-web.data-api.system-info-shows-device-health @inferred @source:pico/app.py#handle_system_info
  Scenario Outline: System information shows connectivity, last provider, fetching and update state
    Given the device is on Wi-Fi at 192.0.2.10
    And the last window came from provider "ci_api"
    And the firmware <ota>
    When the operator requests GET /system-info
    Then wifi_connected is true and ip is "192.0.2.10"
    And provider_last_used is "ci_api"
    And fetcher shows the background fetching state and its last error
    And ota stage is <stage>

    Examples:
      | ota                           | stage                    |
      | supports over-the-air updates | the current update stage |
      | predates over-the-air updates | "unavailable"            |

  @id:device-web.data-api.007 @rule:device-web.data-api.forced-dummy-is-simulated @verified @source:pico/app.py#dummy_fetch_window_any @test:tests/test_fw_providers.py#test_force_dummy_is_the_simulated_series
  Scenario: With the simulated provider forced the window holds made-up hourly readings
    Given the operator has forced the provider "dummy"
    When a client requests GET /em/window
    Then every hour in the window has an intensity between 315 and 430
    And the city in the window is "Dummy"
    And _provider is "dummy"
