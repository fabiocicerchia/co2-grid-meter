@domain:carbon-data @area:provider-selection @from:pico/fw-providers
Feature: Choosing the one provider that serves grid readings
  Lets the device owner decide, in the settings file, which single carbon-data provider the device reads from, and tells them plainly when that choice is missing, ambiguous or incomplete.

  Background:
    Given the device is located in a grid whose country is "IT"

  @id:carbon-data.provider-selection.001 @rule:carbon-data.provider-selection.single-enabled-provider-serves @verified @source:pico/fw_providers.py#_select @test:tests/test_fw_providers.py#test_each_provider_is_selected_when_it_alone_is_configured @test:tests/test_fw_providers.py#test_fetch_window_any_reports_the_selected_name
  Scenario Outline: The one enabled and ready provider serves the readings and is reported by name
    Given only <provider> is enabled in the device settings
    And <provider> has every credential it needs
    When the device fetches the grid readings
    Then the readings come from <provider>
    And the provider is reported as "<name>"

    Examples:
      | provider             | name      |
      | UK Carbon Intensity  | uk        |
      | Carbon Intensity API | ci_api    |
      | Electricity Maps     | em        |
      | CO2 Signal           | co2signal |
      | WattTime             | watttime  |
      | ENTSO-E              | entsoe    |

  @id:carbon-data.provider-selection.002 @rule:carbon-data.provider-selection.no-usable-provider-is-an-error @verified @source:pico/fw_providers.py#_select @test:tests/test_fw_providers.py#test_no_provider_configured_is_an_error @test:tests/test_fw_providers.py#test_an_enabled_provider_without_its_credentials_is_not_selected @test:tests/test_fw_providers.py#test_entsoe_needs_a_mapped_area @questionable
  Scenario Outline: Without a usable provider the device reports that none is available
    Given <setup>
    When the device fetches the grid readings
    Then no readings are shown
    And the device reports the error "No providers available"

    Examples:
      | setup                                                                                   |
      | no provider is enabled                                                                  |
      | only Electricity Maps is enabled and it has no token                                    |
      | only WattTime is enabled and it has no password                                         |
      | only ENTSO-E is enabled with a token and the device country "ZZ" is not an ENTSO-E area |

  @id:carbon-data.provider-selection.003 @rule:carbon-data.provider-selection.only-one-provider-enabled @verified @source:pico/fw_providers.py#_select @test:tests/test_fw_providers.py#test_two_providers_configured_is_an_error_naming_both @test:tests/test_fw_providers.py#test_misconfiguration_still_errors_when_nothing_is_forced
  Scenario: Enabling more than one provider is refused, naming them in documented order
    Given the Carbon Intensity API is enabled
    And WattTime is enabled with its username and password
    When the device fetches the grid readings
    Then no readings are shown
    And the device reports the error "Enable only one provider at a time: ci_api,watttime"

  @id:carbon-data.provider-selection.004 @rule:carbon-data.provider-selection.force-overrides-enabled-flags @verified @source:pico/fw_providers.py#_forced_provider @test:tests/test_fw_providers.py#test_force_selects_a_provider_whose_enabled_flag_is_off @test:tests/test_fw_providers.py#test_force_wins_over_another_enabled_provider @test:tests/test_fw_providers.py#test_force_is_trimmed_and_case_insensitive
  Scenario Outline: A forced provider is used whatever the enabled switches say
    Given providers.force is set to "<force>"
    And <provider> has every credential it needs but is not enabled
    And the Carbon Intensity API is enabled
    When the device fetches the grid readings
    Then the readings come from <provider>
    And the provider is reported as "<name>"

    Examples:
      | force       | provider         | name     |
      | em          | Electricity Maps | em       |
      |   WATTTIME  | WattTime         | watttime |
      | entsoe      | ENTSO-E          | entsoe   |

  @id:carbon-data.provider-selection.005 @rule:carbon-data.provider-selection.forced-provider-never-falls-back @verified @source:pico/fw_providers.py#_forced_provider @test:tests/test_fw_providers.py#test_forcing_a_provider_without_credentials_fails_by_name @test:tests/test_fw_providers.py#test_forcing_entsoe_for_an_unmapped_area_fails_by_name
  Scenario Outline: A forced provider missing its settings fails by name instead of falling back
    Given providers.force is set to "<force>"
    And <missing setup>
    And the Carbon Intensity API is enabled
    When the device fetches the grid readings
    Then no readings come from the Carbon Intensity API
    And the device reports the error "providers.force is <force>, which needs <needs>"

    Examples:
      | force    | missing setup                                            | needs                                                      |
      | em       | Electricity Maps has no token                            | providers.electricity_maps.token                           |
      | watttime | WattTime has no username or password                     | providers.watttime.username, providers.watttime.password   |
      | entsoe   | ENTSO-E has a token, no area override, and the country is "ZZ" | providers.entsoe.area_override (ZZ is not an ENTSO-E area) |

  @id:carbon-data.provider-selection.006 @rule:carbon-data.provider-selection.unknown-forced-name-lists-choices @verified @source:pico/fw_providers.py#_forced_provider @test:tests/test_fw_providers.py#test_forcing_an_unknown_name_lists_the_known_ones @test:tests/test_fw_providers.py#test_a_non_string_force_is_an_unknown_name_not_a_crash
  Scenario Outline: Forcing an unknown provider name is refused with the list of valid names
    Given providers.force is set to <value>
    When the device fetches the grid readings
    Then no readings are shown
    And the device reports the error "providers.force names no provider: <shown> (one of uk, ci_api, em, co2signal, watttime, entsoe, dummy)"

    Examples:
      | value  | shown |
      | "nope" | nope  |
      | true   | true  |

  @id:carbon-data.provider-selection.007 @rule:carbon-data.provider-selection.force-dummy-simulates @verified @source:pico/app.py#_fetch_window @test:tests/test_fw_providers.py#test_force_dummy_is_the_simulated_series
  Scenario: Forcing "dummy" shows a simulated series instead of any real provider
    Given providers.force is set to "dummy"
    And the Carbon Intensity API is enabled
    When the device fetches the grid readings
    Then the readings are an hourly simulated series
    And the provider is reported as "dummy"
    And no real provider is asked for readings
