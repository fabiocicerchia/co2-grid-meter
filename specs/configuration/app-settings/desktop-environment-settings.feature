@domain:configuration @area:app-settings @from:co2-grid-meter/common-config
Feature: Configuring the dashboard and mock device through environment variables
  Operators running the desktop dashboard and the mock Pico tune ports, upstream device, location defaults and provider options from environment variables, falling back to built-in defaults.

  Background:
    Given the operator starts the dashboard or the mock device on a desktop machine

  @id:configuration.app-settings.001 @rule:configuration.app-settings.defaults-when-unset @inferred @source:common_config.py#_build_dataclass
  Scenario Outline: Settings left unset take their built-in defaults
    Given the environment variable <variable> is not set
    When the operator starts the dashboard and the mock device
    Then the <setting> is <default>

    Examples:
      | variable                 | setting                              | default               |
      | WEB_PORT                 | dashboard listening port             | 5000                  |
      | PICO_BASE_URL            | dashboard's upstream device address  | http://127.0.0.1:8080 |
      | PICO_REQUEST_TIMEOUT_SEC | dashboard's upstream request timeout | 15 seconds            |
      | PICO_REQUEST_RETRIES     | dashboard's upstream retry limit     | 3                     |
      | LOG_LEVEL                | dashboard log level                  | INFO                  |
      | PICO_PORT                | mock device listening port           | 8080                  |
      | DEFAULT_COUNTRY          | mock device default country          | IT                    |
      | DEFAULT_CITY             | mock device default city             | Rome                  |

  @id:configuration.app-settings.002 @rule:configuration.app-settings.environment-overrides-default @inferred @source:common_config.py#_value_for_field
  Scenario Outline: An environment variable overrides the built-in default
    Given the environment variable <variable> is set to "<value>"
    When the operator starts the dashboard and the mock device
    Then the <setting> is <value>

    Examples:
      | variable                   | value             | setting                                       |
      | WEB_PORT                   | 5050              | dashboard listening port                      |
      | PICO_BASE_URL              | http://192.0.2.10 | dashboard's upstream device address           |
      | PICO_PORT                  | 8181              | mock device listening port                    |
      | PICO_CACHE_REFRESH_SECONDS | 600               | mock device cache refresh interval in seconds |
      | DEFAULT_CITY               | Lisbon            | mock device default city                      |

  @id:configuration.app-settings.003 @rule:configuration.app-settings.boolean-flag-words @inferred @source:common_config.py#_to_bool @questionable
  Scenario Outline: Only 1, true, yes and on switch a flag on
    Given the environment variable PICO_ALLOW_SIM_FALLBACK is set to "<value>"
    When the operator starts the mock device
    Then the simulated-provider fallback is <state>

    Examples:
      | value   | state |
      | 1       | on    |
      | TRUE    | on    |
      |  yes    | on    |
      | on      | on    |
      | 0       | off   |
      | false   | off   |
      | enabled | off   |
      |         | off   |

  @id:configuration.app-settings.004 @rule:configuration.app-settings.invalid-number-refuses-start @inferred @source:common_config.py#_build_dataclass @questionable
  Scenario Outline: A non-numeric value for a numeric setting stops startup with a misleading message
    Given the environment variable <variable> is set to "<value>"
    When the operator starts the <app>
    Then the <app> does not start
    And the error reads "Missing required config field: <field>"

    Examples:
      | variable                 | value         | app         | field                                       |
      | WEB_PORT                 | five-thousand | dashboard   | WebServerSettings.port                      |
      | PICO_REQUEST_TIMEOUT_SEC |               | dashboard   | WebUpstreamSettings.request_timeout_seconds |
      | DEFAULT_LAT              | north         | mock device | LocationDefaults.latitude                   |

  @id:configuration.app-settings.005 @rule:configuration.app-settings.empty-text-overrides-default @inferred @source:common_config.py#_value_for_field @questionable
  Scenario: A text setting set to an empty value replaces its default with an empty value
    Given the environment variable PICO_BASE_URL is set to an empty value
    When the operator starts the dashboard
    Then the dashboard's upstream device address is empty, not http://127.0.0.1:8080
