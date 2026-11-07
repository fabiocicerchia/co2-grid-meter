@domain:configuration @area:device-settings @from:pico/settings
Feature: Configuring a device through its settings file
  Lets the person setting up a Pico give it Wi-Fi credentials, provider tokens and preferences in an on-device settings.json, and stops the device at startup, naming the setting at fault, when that file can't be used.

  Background:
    Given Given the device reads settings.json from its own filesystem when it starts

  @id:configuration.device-settings.005 @rule:configuration.device-settings.file-overrides-defaults @verified @source:pico/settings.py#apply @test:tests/test_settings.py#test_nested_values_reach_the_config_tree @test:tests/test_settings.py#test_omitted_values_keep_their_defaults
  Scenario: Values in the settings file replace the built-in defaults and omitted values keep them
    Given settings.json sets wifi.ssid to "home" and providers.entsoe.token to "tok_example"
    And settings.json does not mention defaults.city, whose default is "Rome"
    When the device starts up
    Then the device uses Wi-Fi network "home" and ENTSO-E token "tok_example"
    And the device's city is still "Rome"

  @id:configuration.device-settings.006 @rule:configuration.device-settings.unreadable-file-halts-startup @verified @source:pico/settings.py#load @test:tests/test_settings.py#test_malformed_json_is_reported_not_skipped @test:tests/test_settings.py#test_a_json_array_is_refused
  Scenario Outline: A settings file that is not a JSON object stops the device at startup
    Given settings.json contains <content>
    When the device starts up
    Then the device does not start
    And the startup error says "settings.json <message>"

    Examples:
      | content | message                    |
      | {nope   | is not valid JSON: …       |
      | [1, 2]  | must contain a JSON object |

  @id:configuration.device-settings.007 @rule:configuration.device-settings.unknown-setting-halts-startup @verified @source:pico/settings.py#apply @test:tests/test_settings.py#test_an_unknown_setting_is_an_error_naming_it @test:tests/test_settings.py#test_the_old_flat_ukci_key_fails_startup_by_name @test:tests/test_settings.py#test_a_block_set_to_a_single_value_fails_startup_by_name
  Scenario Outline: A misspelled setting, or a whole settings block given a single value, stops the device and is named
    Given settings.json contains <entry>
    When the device starts up
    Then the device does not start
    And the startup error says "settings.json <problem>: <name>"

    Examples:
      | entry                               | problem                                    | name                   |
      | "wifi": {"sid": "home"}             | sets unknown option(s)                     | wifi.sid               |
      | "providers": {"ukci_enabled": true} | sets unknown option(s)                     | providers.ukci_enabled |
      | "providers": {"ukci": true}         | sets a block of settings to a single value | providers.ukci         |

  @id:configuration.device-settings.008 @rule:configuration.device-settings.example-file-accepted @inferred @source:pico/settings.py#apply @questionable
  Scenario: A copy of the example settings file with Wi-Fi filled in starts the device
    Given settings.json is a copy of settings.example.json, including its "_comment" entry
    And the copy has wifi.ssid and wifi.password filled in
    When the device starts up
    Then the device does not start
    And the startup error says "settings.json sets unknown option(s): _comment"

  @id:configuration.device-settings.009 @rule:configuration.device-settings.missing-required-listed-at-once @verified @source:pico/settings.py#require @test:tests/test_settings.py#test_missing_wifi_fails_by_name @test:tests/test_settings.py#test_every_missing_value_is_listed_at_once @test:tests/test_settings.py#test_whitespace_is_not_a_value
  Scenario: Every missing required setting is listed in one startup error
    Given settings.json leaves wifi.ssid blank ("  ") and omits wifi.password
    And the ENTSO-E provider is enabled with no token
    When the device starts up
    Then the device does not start
    And the startup error lists wifi.ssid, wifi.password and providers.entsoe.token together
    And the startup error says to copy settings.example.json to settings.json and fill the values in

  @id:configuration.device-settings.010 @rule:configuration.device-settings.credentials-only-for-used-providers @verified @source:pico/settings.py#required_names @test:tests/test_settings.py#test_only_enabled_providers_need_credentials @test:tests/test_settings.py#test_watttime_needs_both_halves @test:tests/test_settings.py#test_a_forced_provider_needs_only_its_own_credentials @test:tests/test_settings.py#test_force_false_is_unset
  Scenario Outline: Provider credentials are required only for the providers the device will ask
    Given Wi-Fi is configured
    And <provider> is <state>
    And providers.force is <force>
    When the device starts up
    Then the startup error <outcome>

    Examples:
      | provider                      | state   | force  | outcome                                                               |
      | ci-api (keyless)              | enabled | unset  | does not occur                                                        |
      | WattTime with only a username | enabled | unset  | names providers.watttime.password                                     |
      | ENTSO-E without a token       | enabled | " UK " | does not occur                                                        |
      | ENTSO-E without a token       | enabled | "em"   | names providers.electricity_maps.token and not providers.entsoe.token |
      | ENTSO-E without a token       | enabled | false  | names providers.entsoe.token                                          |
