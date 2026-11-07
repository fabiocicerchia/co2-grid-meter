@domain:developer-tooling @area:mock-device @from:mock/mock-pico
Feature: Running the mock Pico
  Gives developers a stand-in Pico on their own machine so they can build the dashboard without hardware.

  Background:
    Given the developer has the mock Pico installed

  @id:developer-tooling.mock-device.007 @rule:tooling.mock-device.listens-on-loopback-at-configured-port @inferred @source:mock/mock_pico.py#run_server @questionable
  Scenario Outline: The mock Pico is reachable only from the developer's own machine, on the configured port
    Given PICO_PORT is set to <port>
    And HOST is set to <host>
    When the developer starts the mock Pico
    Then the log shows "Dashboard server listening on http://127.0.0.1:<port>"
    And the mock Pico answers on 127.0.0.1:<port>
    And the mock Pico cannot be reached from other machines on the network

    Examples:
      | port | host      |
      | 8080 | 127.0.0.1 |
      | 9090 | 0.0.0.0   |

  @id:developer-tooling.mock-device.008 @rule:tooling.mock-device.stops-cleanly-on-interrupt @inferred @source:mock/mock_pico.py#_shutdown @questionable
  Scenario Outline: Interrupting the mock Pico logs a shutdown but leaves it hung with its port held
    Given the mock Pico is running
    When the developer sends <signal> to the mock Pico
    Then the log shows "Shutting down dashboard server"
    And the mock Pico process stays running and does not exit
    And the port stays occupied

    Examples:
      | signal          |
      | SIGINT (Ctrl-C) |
      | SIGTERM         |
