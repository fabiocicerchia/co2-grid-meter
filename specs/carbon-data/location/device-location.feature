@domain:carbon-data @area:location @from:pico/app
Feature: Working out which grid the device reports on
  Serves device owners by picking the location whose grid is reported, from the request, the device's public IP or the configured default city, so readings match where the device is.

  Background:
    Given the device is configured with the default city "Rome" in country "IT" at 41.9, 12.5

  @id:carbon-data.location.001 @rule:carbon-data.location.request-overrides-detected-location @inferred @source:pico/app.py#resolve_geo
  Scenario Outline: A location given in the request wins over the detected one
    Given the device's public IP resolves to "London", "GB" at 51.5, -0.13
    When a client asks the device for a reading with city "<city>", country "<cc>", latitude "<lat>" and longitude "<lon>"
    Then the reading is for city "<shown_city>" in country "<shown_cc>"
    And the reading is for latitude <shown_lat> and longitude <shown_lon>

    Examples:
      | city  | cc | lat   | lon  | shown_city | shown_cc | shown_lat | shown_lon |
      | Paris | fr | 48.85 | 2.35 | Paris      | FR       | 48.85     | 2.35      |
      | Paris |    |       |      | Paris      | GB       | 51.5      | -0.13     |
      |       |    |       |      | London     | GB       | 51.5      | -0.13     |

  @id:carbon-data.location.002 @rule:carbon-data.location.falls-back-to-configured-city @verified @source:pico/app.py#_auto_geo_defaults @test:tests/test_fw_providers.py#test_forcing_a_provider_forces_the_configured_city
  Scenario Outline: Without a usable IP location the configured default city is reported
    Given automatic location from the public IP is <auto>
    And the IP location service <lookup>
    When a client asks the device for a reading without giving a location
    Then the reading is for city "<shown_city>" in country "<shown_cc>"
    And the device keeps answering requests

    Examples:
      | auto     | lookup                 | shown_city | shown_cc |
      | enabled  | resolves to London, GB | London     | GB       |
      | enabled  | reports failure        | Rome       | IT       |
      | enabled  | answers without a city | Rome       | IT       |
      | enabled  | is unreachable         | Rome       | IT       |
      | disabled | resolves to London, GB | Rome       | IT       |

  @id:carbon-data.location.003 @rule:carbon-data.location.forced-provider-uses-configured-city @verified @source:pico/app.py#resolve_geo @test:tests/test_fw_providers.py#test_forcing_a_provider_forces_the_configured_city
  Scenario: Forcing a provider reports the configured city, not the detected one
    Given the device's public IP resolves to "London", "GB" at 51.5, -0.13
    And the operator has forced the provider "ci_api"
    When a client asks the device for a reading without giving a location
    Then the reading is for city "Rome" in country "IT"
    And the reading is for latitude 41.9 and longitude 12.5
