@domain:device-web @area:offline-dashboard @from:pico/http
Feature: Serving the dashboard from the device
  Lets an operator with no desktop server open the dashboard straight from the device without breaking its API.

  Background:
    Given the dashboard files are copied to the device's static folder
    And no API token is configured

  @id:device-web.offline-dashboard.003 @rule:device-web.static.missing-file-falls-through @inferred @source:pico/http.py#serve_static_file
  Scenario Outline: With serving on, the device API still answers its own paths
    Given the operator has enabled static serving
    When a client sends GET <path>
    Then the reply is <reply>

    Examples:
      | path           | reply                                             |
      | /status        | the device status as JSON                         |
      | /em/window.csv | the CSV export                                    |
      | /html/graph    | the built-in graph page                           |
      | /missing.js    | 404 {"error": "Not found", "path": "/missing.js"} |
