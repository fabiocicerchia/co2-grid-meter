@domain:developer-tooling @area:mock-device @from:mock/handler
Feature: Serving simulated device data to the dashboard
  Lets dashboard developers run the dashboard against a stand-in Pico that answers the firmware's endpoints with simulated, IP-located readings, so no hardware is needed.

  Background:
    Given the mock device is running with the simulated provider
    And the mock device's public IP geolocates to Berlin, DE

  @id:developer-tooling.mock-device.001 @rule:mock-device.status.current-reading-and-recommendation @inferred @source:mock/handler.py#MockPicoHandler @questionable
  Scenario: The mock device reports a current reading with a run/wait recommendation
    When the dashboard requests GET /status from the mock device
    Then the response status is 200 with a JSON body
    And the body names the city "Berlin", country "DE", its latitude and longitude, and geo source "ip"
    And the body carries the current hour as datetime, a carbonIntensity equal to the last history reading, and a recommendation
    And the history spans 36 hours before to 12 hours after the current hour, taken from the simulated data one week earlier

  @id:developer-tooling.mock-device.002 @rule:mock-device.window.history-length @inferred @source:mock/handler.py#MockPicoHandler
  Scenario Outline: The mock device returns as many hours of history as asked, 48 by default
    When the dashboard requests <path> from the mock device
    Then the response status is 200 with content type <content_type>
    And the readings cover the <hours> hours up to the current hour

    Examples:
      | path                            | content_type     | hours |
      | GET /em/window                  | application/json | 48    |
      | GET /em/window?back_hours=24    | application/json | 24    |
      | GET /em/window.csv              | text/csv         | 48    |
      | GET /em/window.csv?back_hours=6 | text/csv         | 6     |

  @id:developer-tooling.mock-device.003 @rule:mock-device.overlay.last-week-window @inferred @source:mock/handler.py#MockPicoHandler
  Scenario: The forecast overlay shows the same span of last week's readings
    When the dashboard requests GET /em/window-overlay from the mock device
    Then the response status is 200 with a JSON body
    And the history spans from 48 hours before to 12 hours after the current hour, one week earlier

  @id:developer-tooling.mock-device.004 @rule:mock-device.summary.compact-summary @inferred @source:mock/handler.py#MockPicoHandler
  Scenario: The mock device offers the compact home-automation summary
    When the dashboard requests GET /em/summary from the mock device
    Then the response status is 200 with a JSON body
    And the summary is built from the last 48 hours, with the latest reading as current, a recommendation, the current hour as its time, city "Berlin", country "DE" and provider "simulated"

  @id:developer-tooling.mock-device.005 @rule:mock-device.routing.unknown-path-not-found @inferred @source:mock/handler.py#MockPicoHandler
  Scenario: An unknown path on the mock device is not found
    When the dashboard requests GET /does-not-exist from the mock device
    Then the response status is 404
    And the body is an empty JSON object

  @id:developer-tooling.mock-device.006 @rule:mock-device.errors.failure-reported-as-502 @inferred @source:mock/handler.py#MockPicoHandler @questionable
  Scenario Outline: The mock device answers 502 with the error when it cannot build a response
    Given <condition>
    When the dashboard requests <path> from the mock device
    Then the response status is 502
    And the body is JSON with an "error" message

    Examples:
      | condition                               | path                          |
      | the mock device cannot geolocate its IP | GET /status                   |
      | the mock device cannot geolocate its IP | GET /em/window                |
      | the mock device can geolocate its IP    | GET /em/window?back_hours=abc |
