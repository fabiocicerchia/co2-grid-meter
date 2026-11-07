@domain:dashboard @area:device-proxy @from:web/server
Feature: Running the dashboard server
  Lets an operator run the desktop dashboard on their own machine, on a port they choose, and stop it with an ordinary interrupt or terminate signal.

  Background:
    Given the dashboard server is installed on the operator's machine

  @id:dashboard.device-proxy.001 @rule:dashboard.server.loopback-only @inferred @source:web/server.py#run_server @questionable
  Scenario Outline: The dashboard listens only on this machine's own loopback address on the configured port
    Given the operator has set the dashboard port to <configured_port>
    When the operator starts the dashboard server
    Then the dashboard is served at http://127.0.0.1:<served_port>
    And the startup log says "Dashboard server listening on http://127.0.0.1:<served_port>"
    And other machines on the network cannot reach the dashboard

    Examples:
      | configured_port | served_port |
      | (not set)       | 5000        |
      | 8123            | 8123        |

  @id:dashboard.device-proxy.002 @rule:dashboard.server.stops-on-signal @inferred @source:web/server.py#_shutdown @questionable
  Scenario Outline: The dashboard stops cleanly when interrupted or told to terminate
    Given the dashboard server is running
    When the operator sends the <signal> signal to the dashboard server
    Then the log says "Shutting down dashboard server"
    And the dashboard stops accepting connections
    And the process exits with status 0

    Examples:
      | signal          |
      | SIGINT (Ctrl+C) |
      | SIGTERM         |
