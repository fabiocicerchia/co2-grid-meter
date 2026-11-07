@domain:dashboard @area:dashboard-ui @from:web/static
Feature: Watching grid carbon intensity on the desktop dashboard
  Lets a household user see the device's current reading, run/wait advice and recent intensity trend in a browser, with their preferences remembered.

  Background:
    Given the dashboard is open in the user's browser
    And the dashboard can reach a CO2 grid meter device

  @id:dashboard.dashboard-ui.001 @rule:dashboard.current.shows-device-reading @inferred @source:web/static/script.js#pollPicoStatus
  Scenario: The dashboard shows the device's current intensity and run/wait advice
    Given the device reports an intensity of 212.6 gCO2/kWh
    And the device recommends "WAIT" because "Above recent average" with next window "14:00"
    When the dashboard refreshes
    Then the current intensity reads "213"
    And the recommendation reads "WAIT"
    And the reason reads "Above recent average"
    And the next window reads "14:00"

  @id:dashboard.dashboard-ui.002 @rule:dashboard.current.device-error-shown @inferred @source:web/static/script.js#pollPicoStatus
  Scenario: A device error blanks the reading and shows the error as the reason
    Given the device answers with the error "device unreachable"
    When the dashboard refreshes
    Then the current intensity, recommendation and next window read "—"
    And the reason reads "device unreachable"
    And the intensity meter has no lit lights and reads "No current data"

  @id:dashboard.dashboard-ui.003 @rule:dashboard.meter.ranks-against-last-week @inferred @source:web/static/script.js#meterFromWeekDistribution @questionable
  Scenario Outline: The intensity meter ranks the current intensity against last week's readings
    Given last week's readings for the shown window are 100, 200, 300 ... 1200 gCO2/kWh
    And the device reports a current intensity of <current>
    When the dashboard refreshes
    Then <lit> of the 12 meter lights are lit
    And the meter reads "<label>"

    Examples:
      | current | lit | label                     |
      | 50      | 0   | cleaner than usual • p0   |
      | 350     | 3   | cleaner than usual • p25  |
      | 450     | 4   | around average • p33      |
      | 650     | 6   | around average • p50      |
      | 1150    | 11  | dirtier than usual • p92  |
      | 1250    | 12  | dirtier than usual • p100 |

  @id:dashboard.dashboard-ui.004 @rule:dashboard.meter.needs-baseline @inferred @source:web/static/script.js#meterFromWeekDistribution
  Scenario: The meter waits for enough of last week's readings before ranking
    Given fewer than 12 of last week's readings are available
    And the device reports a current intensity of 300 gCO2/kWh
    When the dashboard refreshes
    Then no meter lights are lit
    And the meter reads "Collecting baseline…"

  @id:dashboard.dashboard-ui.005 @rule:dashboard.chart.past-48h-with-last-week-overlay @inferred @source:web/static/script.js#drawChart
  Scenario: The chart shows the past 48 hours next to last week's curve, which extends 12 hours ahead
    Given the device has readings for the past 48 hours and for the same period a week earlier
    When the dashboard refreshes
    Then the chart draws the past 48 hours of actual intensity as a solid line
    And the chart draws last week's intensity, moved forward one week and reaching 12 hours past now, as a dotted line
    And a "now" marker divides past from future

  @id:dashboard.dashboard-ui.006 @rule:dashboard.auto-refresh.remembered @inferred @source:web/static/script.js#startAuto
  Scenario: Auto refresh and its interval are remembered between visits
    Given the user started auto refresh every "1m"
    When the user opens the dashboard again
    Then auto refresh is running every 1m
    And the button reads "Stop" and the state reads "running"
    And a progress bar at the top fills up until the next refresh

  @id:dashboard.dashboard-ui.007 @rule:dashboard.theme.remembered-or-system @inferred @source:web/static/script.js#applyTheme
  Scenario Outline: The dashboard uses the saved theme, or else the system's colour scheme
    Given the user has <saved> as the theme
    And the operating system prefers a <system> colour scheme
    When the user opens the dashboard
    Then the dashboard is shown in the <shown> theme
    And the theme toggle reads "<label>"

    Examples:
      | saved     | system | shown | label |
      | no choice | dark   | dark  | Dark  |
      | no choice | light  | light | Light |
      | light     | dark   | light | Light |
      | dark      | light  | dark  | Dark  |

  @id:dashboard.dashboard-ui.008 @rule:dashboard.language.english-or-italian @inferred @source:web/static/script.js#applyI18n @questionable
  Scenario Outline: Dashboard labels follow the chosen language and the choice is remembered
    Given the user chose "<lang>" as the language
    When the user opens the dashboard
    Then the auto refresh control reads "<auto>"
    And the chart title reads "<chart>"

    Examples:
      | lang | auto                     | chart                     |
      | EN   | Auto refresh             | Past 48h + Next 12h       |
      | IT   | Aggiornamento automatico | Ultime 48h + Prossime 12h |
