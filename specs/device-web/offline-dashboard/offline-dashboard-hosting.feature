@domain:device-web @area:offline-dashboard @from:pico/staticfiles
Feature: Hosting the dashboard from the device
  Lets an operator open the dashboard straight from the Pico with no desktop server, without the device handing out its settings file or other files on its flash unless the dashboard folder is set to the filesystem root.

  Background:
    Given the dashboard files are copied to the device's static folder "static"
    And no API token is configured on the device

  @id:device-web.offline-dashboard.005 @rule:device-web.offline-dashboard.off-by-default @inferred @source:pico/http.py#_dispatch
  Scenario: The device does not serve dashboard files unless the operator turns it on
    Given the operator has not enabled static file serving
    When a browser requests "/index.html" from the device
    Then the device answers 404
    And the body is {"error": "Not found", "path": "/index.html"}

  @id:device-web.offline-dashboard.006 @rule:device-web.offline-dashboard.confined-to-static-root @inferred @source:pico/staticfiles.py#resolve
  Scenario Outline: A request cannot reach any file outside the dashboard folder
    Given the operator has enabled static file serving
    And the device's settings file holds the Wi-Fi password and provider tokens
    When a client requests "<path>" from the device
    Then the device answers 404 with {"error": "Not found", "path": "<path>"}
    And no file content from outside the static folder is sent

    Examples:
      | path                     |
      | /../settings.json        |
      | /css/../../settings.json |
      | /%2e%2e/settings.json    |
      | /%2e%2e%2fsettings.json  |
      | /..%2fsettings.json      |
      | //settings.json          |
      | /%2fsettings.json        |
      | /..\settings.json        |
      | /css\..\..\settings.json |

  @id:device-web.offline-dashboard.007 @rule:device-web.offline-dashboard.root-setting-exposes-flash @inferred @source:pico/staticfiles.py#resolve @questionable
  Scenario Outline: Setting the dashboard folder to the filesystem root exposes the settings file
    Given the operator has enabled static file serving
    And the operator has set the static folder to "<static_root>" in the settings file
    When a client requests "/settings.json" from the device
    Then the device answers 200 with Content-Type "application/json"
    And the body is the device's settings file, including the Wi-Fi password and provider tokens

    Examples:
      | static_root |
      | /           |
      |             |

  @id:device-web.offline-dashboard.008 @rule:device-web.offline-dashboard.only-dashboard-file-types @inferred @source:pico/staticfiles.py#content_type
  Scenario Outline: Only the file types the dashboard ships are ever served
    Given the operator has enabled static file serving
    And the file "<file>" exists in the static folder
    When a client requests "/<file>" from the device
    Then the device answers 404 with {"error": "Not found", "path": "/<file>"}

    Examples:
      | file        |
      | secret.py   |
      | private_key |
      | tool.exe    |
      | notes.txt   |

  @id:device-web.offline-dashboard.009 @rule:device-web.offline-dashboard.asset-served @inferred @source:pico/http.py#serve_static_file
  Scenario Outline: A dashboard file is served with its type and a five-minute cache lifetime
    Given the operator has enabled static file serving
    When a browser requests "<path>" from the device
    Then the device answers 200 with the contents of "<file>" from the static folder
    And the Content-Type is "<content_type>"
    And the response carries an ETag and "Cache-Control: max-age=300"

    Examples:
      | path           | file          | content_type                   |
      | /              | index.html    | text/html; charset=utf-8       |
      | /script.js?v=3 | script.js     | text/javascript; charset=utf-8 |
      | /style.css     | style.css     | text/css; charset=utf-8        |
      | /css/style.css | css/style.css | text/css; charset=utf-8        |

  @id:device-web.offline-dashboard.010 @rule:device-web.offline-dashboard.unchanged-asset-not-resent @inferred @source:pico/staticfiles.py#not_modified
  Scenario Outline: A browser revalidating an unchanged dashboard file gets 304 with no body
    Given the operator has enabled static file serving
    And the browser last received "/script.js" with an ETag that still matches the file
    When the browser requests "/script.js" with If-None-Match "<if_none_match>"
    Then the device answers 304 Not Modified
    And the response carries the current ETag and no file contents

    Examples:
      | if_none_match                                      |
      | the same ETag                                      |
      | the same ETag with a W/ prefix                     |
      | "other" followed by the same ETag, comma-separated |
      | *                                                  |

  @id:device-web.offline-dashboard.011 @rule:device-web.offline-dashboard.api-not-shadowed @inferred @source:pico/http.py#serve_static_file
  Scenario Outline: Turning on dashboard hosting leaves the device API answering as before
    Given the operator has enabled static file serving
    When a client requests "<path>" from the device
    Then the device answers with the <response> it gives when static serving is off

    Examples:
      | path           | response            |
      | /status        | JSON status         |
      | /em/window.csv | CSV window export   |
      | /html/graph    | built-in graph page |
