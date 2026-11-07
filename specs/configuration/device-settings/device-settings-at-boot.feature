@domain:configuration @area:device-settings @from:pico/config
Feature: Starting a device from its settings
  Serves the person setting up a meter: the device boots only with a usable settings file, and anything left unset falls back to a documented out-of-the-box default.

  Background:
    Given the device's own values are read from settings.json when the firmware starts

  @id:configuration.device-settings.001 @rule:device.settings.boot-refused-until-required-values-set @verified @source:pico/config.py#SETTINGS_ERROR @test:tests/test_settings.py#test_missing_wifi_fails_by_name @test:tests/test_settings.py#test_every_missing_value_is_listed_at_once @test:tests/test_settings.py#test_whitespace_is_not_a_value @test:tests/test_settings.py#test_watttime_needs_both_halves @test:tests/test_settings.py#test_a_forced_provider_needs_only_its_own_credentials @test:tests/test_settings.py#test_an_unknown_setting_is_an_error_naming_it
  Scenario Outline: A device with missing or invalid settings refuses to start and names every problem
    Given settings.json <state>
    When the device starts
    Then the device stops before joining Wi-Fi
    And the boot log shows a FATAL line naming <named>
    And no carbon reading is shown

    Examples:
      | state                                                  | named                            |
      | leaves the Wi-Fi name and password empty               | wifi.ssid, wifi.password         |
      | sets the Wi-Fi name to blank spaces                    | wifi.ssid                        |
      | enables ENTSO-E without a token                        | providers.entsoe.token           |
      | enables WattTime with a username but no password       | providers.watttime.password      |
      | forces provider "em" without an Electricity Maps token | providers.electricity_maps.token |
      | sets an unknown option "wifi.sid"                      | wifi.sid                         |

  @id:configuration.device-settings.002 @rule:device.settings.keyless-providers-need-no-credentials @verified @source:pico/settings.py#required_names @test:tests/test_settings.py#test_only_enabled_providers_need_credentials @test:tests/test_settings.py#test_a_forced_provider_needs_only_its_own_credentials
  Scenario Outline: A device that only asks keyless or unasked providers boots without any tokens
    Given settings.json sets the Wi-Fi name and password
    And <providers>
    When the device starts
    Then the device starts without a settings error

    Examples:
      | providers                                                      |
      | only the keyless ci-api provider is enabled                    |
      | ENTSO-E is enabled without a token but provider "uk" is forced |

  @id:configuration.device-settings.003 @rule:device.settings.out-of-box-defaults @verified @source:pico/config.py#CONFIG @test:tests/test_settings.py#test_omitted_values_keep_their_defaults
  Scenario Outline: Settings left out of settings.json take the firmware default
    Given settings.json sets only the Wi-Fi name, password and an ENTSO-E token
    When the device starts
    Then <setting> is <default>

    Examples:
      | setting                               | default                                                           |
      | the provider asked                    | ENTSO-E, for bidding zone IT-CSOUTH                               |
      | the fallback location                 | Rome, IT (41.9028, 12.4964)                                       |
      | local time                            | UTC+1 with EU summer time                                         |
      | the web server                        | listening on every interface, port 8080                           |
      | serving the dashboard from the device | off                                                               |
      | the device language                   | en                                                                |
      | the green / yellow bands              | up to the 25th / 50th percentile                                  |
      | the timeline                          | 48 hours back and 12 hours ahead                                  |
      | locating by public IP                 | on, rechecked every 24 hours, retried after 15 minutes on failure |

  @id:configuration.device-settings.004 @rule:device.settings.api-open-without-token @inferred @source:pico/config.py#CONFIG
  Scenario: A device with no API token configured leaves every endpoint open
    Given settings.json does not set web.api_token
    When a client on the LAN calls the device API without an Authorization header
    Then the device answers the request instead of returning 401
