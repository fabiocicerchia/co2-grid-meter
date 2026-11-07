@domain:device-web @area:device-pages @from:pico/pages
Feature: Viewing the device's built-in pages
  Lets someone on the local network check the meter's current reading, recommendation and recent history in a browser without the desktop dashboard.

  Background:
    Given the device is on the local network and serving its pages

  @id:device-web.device-pages.001 @rule:device-web.pages.status-page-shows-current-reading @inferred @source:pico/pages.py#build_index_html
  Scenario: The status page shows the current reading and recommendation
    Given the device's current status reports city "Berlin", country "DE", 312 gCO₂/kWh from provider "electricitymaps"
    And the recommendation is "WAIT" with reason "Above recent average", 3 wait hours and next best "15:00"
    When a visitor opens /html
    Then the heading reads "Berlin grid CO₂ status"
    And the page shows carbon intensity "312 gCO₂/kWh" and provider "electricitymaps"
    And the page shows recommendation "WAIT", reason "Above recent average", wait hours "3" and next best "15:00"
    And the line under the heading shows the country, the reading time and the latitude and longitude
    And any value the status does not report is shown as "--"

  @id:device-web.device-pages.002 @rule:device-web.pages.verdict-colour @inferred @source:pico/pages.py#build_index_html @questionable
  Scenario Outline: The recommendation badge is coloured by verdict
    Given the device's current recommendation is "<verdict>"
    When a visitor opens /html
    Then the recommendation badge reads "<verdict>"
    And the badge is <colour>

    Examples:
      | verdict | colour |
      | GO      | green  |
      | WAIT    | red    |
      | --      | amber  |

  @id:device-web.device-pages.003 @rule:device-web.pages.status-page-refresh @inferred @source:pico/pages.py#build_index_html
  Scenario: The status page refreshes itself and reports when it cannot load
    Given a visitor has /html open
    When 30 seconds pass, or the visitor presses Refresh
    Then the page loads the device's status again and shows the new values
    And if the status cannot be loaded, the line under the heading reads "Error loading /status: " followed by the reason, for example "HTTP 401"

  @id:device-web.device-pages.004 @rule:device-web.pages.theme-remembered @inferred @source:pico/pages.py#build_index_html @questionable
  Scenario: The status page's dark mode choice is remembered in the browser
    Given a visitor has /html open in the default theme, which follows the system setting
    When the visitor presses "Dark mode"
    Then the page turns dark and the button reads "Light mode"
    And reopening /html in the same browser shows it dark again
    And pressing "Light mode" returns the page to following the system setting, not to a fixed light theme

  @id:device-web.device-pages.005 @rule:device-web.pages.graph-last-48-hours @inferred @source:pico/pages.py#GRAPH_HTML
  Scenario Outline: The graph page plots the last 48 hours of intensity
    Given the device holds <history> for the last 48 hours
    When a visitor opens /html/graph
    Then the page is titled "Last 48h CO₂ (gCO₂/kWh)"
    And the chart shows <shown>

    Examples:
      | history         | shown                                                        |
      | hourly readings | one line through the readings, scaled from lowest to highest |
      | no readings     | the text "No data"                                           |

  @id:device-web.device-pages.006 @rule:device-web.pages.pages-index @inferred @source:pico/pages.py#MINI_HTML @questionable
  Scenario: The device lists its local pages
    When a visitor opens /html/
    Then the page is headed "Pico local pages"
    And it links to "Graph" at /html/graph and "System info JSON" at /system-info
