@domain:carbon-data @area:providers @from:pico/providers
Feature: Reading grid carbon intensity from data providers
  Gives device owners an hourly grid carbon-intensity curve from whichever provider they set up, and gives operators a clear refusal when a provider can't serve.

  Background:
    Given the device has one provider set up in its settings

  @id:carbon-data.providers.007 @rule:carbon-data.providers.credentials-named-when-missing @verified @source:pico/providers/base.py#EmissionsProvider @test:tests/test_fw_providers.py#test_the_request_time_guard_still_names_missing_credentials @test:tests/test_fw_providers.py#test_forcing_a_provider_without_credentials_fails_by_name @test:tests/test_fw_providers.py#test_an_enabled_provider_without_its_credentials_is_not_selected
  Scenario Outline: A provider without its credentials refuses and names the missing settings
    Given the <provider> provider is selected
    And <settings> is empty in the device settings
    When the device fetches the intensity window
    Then no reading is fetched
    And the error names <settings>

    Examples:
      | provider         | settings                                                 |
      | Electricity Maps | providers.electricity_maps.token                         |
      | CO2Signal        | providers.co2signal.token                                |
      | WattTime         | providers.watttime.username, providers.watttime.password |
      | ENTSO-E          | providers.entsoe.token                                   |

  @id:carbon-data.providers.008 @rule:carbon-data.providers.entsoe-area-must-be-mapped @verified @source:pico/providers/entsoe.py#EntsoeProvider @test:tests/test_fw_providers.py#test_entsoe_needs_a_mapped_area @test:tests/test_fw_providers.py#test_entsoe_area_override_wins_over_the_country @test:tests/test_fw_providers.py#test_forcing_entsoe_for_an_unmapped_area_fails_by_name
  Scenario Outline: ENTSO-E serves only a known bidding area, and the area override wins over the device's country
    Given the ENTSO-E provider is selected with a token
    And the device's country is <country>
    And the ENTSO-E area override is <override>
    When the device fetches the intensity window
    Then <outcome>

    Examples:
      | country | override  | outcome                                                                 |
      | IT      | (empty)   | the window is fetched for area IT and labelled IT                       |
      | ZZ      | IT-CSOUTH | the window is fetched for area IT-CSOUTH and labelled IT-CSOUTH         |
      | ZZ      | (empty)   | no reading is fetched and the error says ZZ is not an ENTSO-E area      |
      | IT      | NOWHERE   | no reading is fetched and the error says NOWHERE is not an ENTSO-E area |

  @id:carbon-data.providers.009 @rule:carbon-data.providers.entsoe-intensity-from-generation-mix @inferred @source:pico/providers/entsoe.py#_history_from_buckets @questionable
  Scenario Outline: ENTSO-E intensity is the generation-weighted average of fixed per-fuel emission factors
    Given ENTSO-E reports <generation> for one hour
    When the device fetches the intensity window
    Then that hour shows <intensity>

    Examples:
      | generation                                             | intensity                |
      | 1000 MW lignite and 1000 MW solar                      | 525 gCO2/kWh             |
      | 500 MW natural gas                                     | 370 gCO2/kWh             |
      | 800 MW solar and 200 MW onshore wind                   | no reading for that hour |
      | 500 MW natural gas and 500 MW of an unlisted fuel type | 185 gCO2/kWh             |

  @id:carbon-data.providers.010 @rule:carbon-data.providers.stale-current-reading-refused @verified @source:pico/providers/ci_api.py#CiApiProvider @test:tests/test_ci_api_parse.py#test_missed_pipeline_run_is_rejected @test:tests/test_ci_api_parse.py#test_fresh_hour_passes
  Scenario Outline: A current Carbon Intensity API window whose newest hour is over four hours old is refused
    Given the Carbon Intensity API provider is selected
    And the newest measured hour it returns is <age> old
    When the device fetches the <window>
    Then <outcome>

    Examples:
      | age        | window                     | outcome                                                                           |
      | 10 minutes | window ending now          | the window is shown                                                               |
      | 5 hours    | window ending now          | no reading is shown and the error says the newest reading is too old (max 14400s) |
      | 7 days     | week-ago comparison window | the window is shown                                                               |

  @id:carbon-data.providers.011 @rule:carbon-data.providers.sampled-history-builds-from-readings @inferred @source:pico/providers/base.py#SampledProvider @questionable
  Scenario Outline: CO2Signal history is built on the device from one reading per hour
    Given the CO2Signal provider is selected
    And the device has collected <readings>
    When the device fetches the <window>
    Then the history shows <points>
    And readings more than 14 days older than the newest one are no longer kept

    Examples:
      | readings                                        | window                     | points                                                     |
      | 210 gCO2/kWh at 10:05 and 230 gCO2/kWh at 10:40 | window from 08:00 to 11:00 | one point at 10:00 of 230 gCO2/kWh                         |
      | 200 at 09:10 and 240 at 10:20                   | window from 08:00 to 11:00 | 200 at 09:00 and 240 at 10:00                              |
      | only 250 gCO2/kWh at 06:30                      | window from 08:00 to 11:00 | one point at 06:00 of 250 gCO2/kWh                         |
      | nothing yet, and CO2Signal is unreachable       | window from 08:00 to 11:00 | no points, and the error says the co2signal store is empty |

  @id:carbon-data.providers.012 @rule:carbon-data.providers.watttime-cooldown-after-forbidden @inferred @source:pico/providers/watttime.py#WattTimeProvider @questionable
  Scenario: WattTime pauses for a day after it refuses access
    Given the WattTime provider is selected with a username and password
    And WattTime answered 403 Forbidden to the last history request
    When the device fetches the intensity window within the next 24 hours
    Then no request is made to WattTime
    And the error says 'WattTime temporarily disabled'

  @id:carbon-data.providers.013 @rule:carbon-data.providers.watttime-region-configured-or-located @inferred @source:pico/providers/watttime.py#WattTimeProvider
  Scenario Outline: WattTime serves the configured region, otherwise the region where the device is
    Given the WattTime provider is selected with a username and password
    And the WattTime region setting is <region setting>
    When the device fetches the intensity window
    Then <outcome>

    Examples:
      | region setting                                     | outcome                                                                                           |
      | CAISO_NORTH                                        | the window shows hourly averages for CAISO_NORTH, labelled CAISO_NORTH                            |
      | (empty), device at 37.77, -122.42                  | the window shows hourly averages for the region WattTime locates there, labelled with that region |
      | (empty), WattTime names no region for the location | no reading is shown and the error says 'WattTime region missing ba'                               |

  @id:carbon-data.providers.014 @rule:carbon-data.providers.uk-actual-before-forecast @inferred @source:pico/providers/ukci.py#UkciProvider
  Scenario Outline: UK Carbon Intensity shows national actual readings, using the forecast where no actual exists
    Given the UK Carbon Intensity provider is selected
    And for one half-hour the published actual is <actual> and the forecast is <forecast>
    When the device fetches the intensity window
    Then that point shows <shown>
    And the window is labelled Great Britain wherever the device is

    Examples:
      | actual | forecast | shown    |
      | 182    | 190      | 182      |
      | (none) | 190      | 190      |
      | (none) | (none)   | no point |
