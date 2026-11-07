@domain:device-web @area:offline-dashboard @from:pico/http
Feature: Serving the dashboard from the device
  Lets an operator with no desktop server open the dashboard straight from the device without breaking its API.

  Background:
    Given the dashboard files are copied to the device's static folder
    And no API token is configured

  @id:device-web.offline-dashboard.001 @rule:device-web.static.off-by-default @inferred @source:pico/http.py#_dispatch
  Scenario: Dashboard files are not served unless the operator turns serving on
    Given the operator has not enabled static serving
    When a client sends GET /index.html
    Then the response status is 404

  @id:device-web.offline-dashboard.002 @rule:device-web.static.dashboard-files-served @inferred @source:pico/http.py#serve_static_file
  Scenario Outline: With serving on, a dashboard file is served with a validator and five-minute caching
    Given the operator has enabled static serving
    When a client sends GET <path>
    Then the response status is 200
    And the Content-Type is <content type>
    And the response carries an ETag and Cache-Control: max-age=300

    Examples:
      | path        | content type                   |
      | /           | text/html; charset=utf-8       |
      | /index.html | text/html; charset=utf-8       |
      | /script.js  | text/javascript; charset=utf-8 |
      | /style.css  | text/css; charset=utf-8        |

  @id:device-web.offline-dashboard.003 @rule:device-web.static.missing-file-falls-through @inferred @source:pico/http.py#serve_static_file
  Scenario Outline: With serving on, the device API still answers its own paths
    Given the operator has enabled static serving
    When a client sends GET <path>
    Then the reply is <reply>

    Examples:
      | path           | reply                                             |
      | /status        | the device status as JSON                         |
      | /em/window.csv | the CSV export                                    |
      | /missing.js    | 404 {"error": "Not found", "path": "/missing.js"} |

  @id:device-web.offline-dashboard.004 @rule:device-web.static.unchanged-file-not-resent @inferred @source:pico/http.py#serve_static_file
  Scenario: An unchanged dashboard file is confirmed rather than resent
    Given the operator has enabled static serving
    And a browser already holds /index.html with its current ETag
    When the browser requests /index.html again with If-None-Match set to that ETag
    Then the response status is 304
    And the response carries the same ETag and no body
