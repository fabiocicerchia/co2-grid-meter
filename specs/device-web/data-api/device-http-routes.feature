@domain:device-web @area:data-api @from:pico/http
Feature: Answering requests on the device
  Gives dashboards, Home Assistant and scripts a stable set of device paths and predictable error replies.

  Background:
    Given the device is serving its web interface on the local network
    And no API token is configured

  @id:device-web.data-api.012 @rule:device-web.api.published-routes @inferred @source:pico/http.py#_dispatch
  Scenario Outline: Each published device path answers with its content type
    When a client sends GET <path>
    Then the response status is 200
    And the Content-Type is <content type>

    Examples:
      | path               | content type             |
      | /status            | application/json         |
      | /em/window         | application/json         |
      | /em/window-overlay | application/json         |
      | /em/summary        | application/json         |
      | /system-info       | application/json         |
      | /em/window.csv     | text/csv                 |
      | /html              | text/html; charset=utf-8 |
      | /html/             | text/html                |
      | /html/graph        | text/html                |

  @id:device-web.data-api.013 @rule:device-web.api.get-only @inferred @source:pico/http.py#_dispatch
  Scenario Outline: Only reading requests are accepted
    When a client sends <method> /status
    Then the response status is 405
    And the response body is {"error": "Only GET supported"}

    Examples:
      | method |
      | POST   |
      | PUT    |
      | DELETE |
      | HEAD   |

  @id:device-web.data-api.014 @rule:device-web.api.unknown-path-not-found @inferred @source:pico/http.py#_dispatch
  Scenario: An unknown path is answered with not found, naming the path
    When a client sends GET /no-such-route
    Then the response status is 404
    And the response body is {"error": "Not found", "path": "/no-such-route"}

  @id:device-web.data-api.015 @rule:device-web.api.internal-error-reported @inferred @source:pico/http.py#handle_http_request @questionable
  Scenario: A request that fails unexpectedly gets an internal-error reply and leaves a crash record
    Given building the /status reply fails with the error "division by zero"
    When a client sends GET /status
    Then the response status is 500
    And the response body is {"error": "Internal error", "details": "division by zero"}
    And a crash dump is written on the device and its path is added to the device log

  @id:device-web.data-api.016 @rule:device-web.api.cross-origin-readable @inferred @source:pico/http.py#_send_response @questionable
  Scenario: Device API replies can be read by pages from any origin
    When a browser page served from http://dashboard.example.com requests GET /status
    Then the response carries Access-Control-Allow-Origin: *
