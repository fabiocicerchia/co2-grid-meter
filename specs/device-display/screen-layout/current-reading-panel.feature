@domain:device-display @area:screen-layout @from:pico/display
Feature: Showing the current reading and advice on the e-ink panel
  Gives anyone glancing at the device the current grid intensity, the run/wait advice, how dirty the hour is relative to the week, the time and Wi-Fi state without opening the dashboard.

  Background:
    Given the device has a reading for the current hour

  @id:device-display.screen-layout.001 @rule:display.verdict-panel.colour-follows-verdict @verified @source:pico/display.py#draw_current_panel @test:tests/test_fw_render.py#test_the_line_ends_inside_the_panel_interior
  Scenario Outline: A clean or average grid shows the verdict in black; anything else shows the next step in red
    Given the device language is <language>
    And the recommendation verdict is <verdict>
    And the recommendation's next step reads "<next step>"
    When the device refreshes the panel
    Then the verdict panel is filled <colour>
    And the panel reads "<panel text>" in white

    Examples:
      | language | verdict  | next step          | colour | panel text         |
      | English  | RUN NOW  | Cleaner than avg   | black  | RUN NOW            |
      | English  | OK       | Around average     | black  | OK                 |
      | Italian  | ORA      | Meglio della media | black  | ORA                |
      | English  | WAIT     | WAIT 3h (14:00)    | red    | WAIT 3h (14:00)    |
      | Italian  | ATTENDI  | ATTENDI 3h (14:00) | red    | ATTENDI 3h (14:00) |
      | English  | none yet |                    | red    |                    |

  @id:device-display.screen-layout.002 @rule:display.reading.co2-line-whole-grams @inferred @source:pico/display.py#draw_current_panel
  Scenario Outline: The current intensity is shown in whole grams per kilowatt-hour
    Given the current intensity is <intensity> gCO2/kWh
    When the device refreshes the panel
    Then the line under the verdict panel reads "<shown>"

    Examples:
      | intensity | shown          |
      | 412       | CO2: 412 g/kWh |
      | 412.9     | CO2: 412 g/kWh |
      | 0         | CO2: 0 g/kWh   |

  @id:device-display.screen-layout.003 @rule:display.led-bar.level-tracks-week-percentile @inferred @source:pico/display.py#led_level_from_percentile @questionable
  Scenario Outline: The LED bar lights one segment per eighth of the week's range the current hour sits at
    Given the current hour sits at the <percentile> percentile of the past week
    When the device refreshes the panel
    Then <lit> of the 8 LED segments are filled and the rest are outlined

    Examples:
      | percentile                | lit |
      | 0.00                      | 0   |
      | 0.30                      | 2   |
      | 0.50                      | 4   |
      | 0.94                      | 8   |
      | 1.00                      | 8   |
      | unknown (no week history) | 0   |

  @id:device-display.screen-layout.004 @rule:display.status-bar.wifi-signal-bars @inferred @source:pico/display.py#draw_wifi_icon
  Scenario Outline: The Wi-Fi icon shows signal bars when connected and an empty red icon when offline
    Given the device is <state> with <bars> signal bars
    When the device refreshes the panel
    Then <filled> bars of the Wi-Fi icon are filled in black
    And the remaining bars are outlined in red
    And the antenna dot is <dot>

    Examples:
      | state        | bars | filled | dot          |
      | connected    | 3    | 3      | filled black |
      | connected    | 6    | 4      | filled black |
      | disconnected | 3    | 0      | outlined red |

  @id:device-display.screen-layout.005 @rule:display.status-bar.local-clock @inferred @source:pico/display.py#draw_time
  Scenario: The panel shows the device's local time as hours and minutes
    Given the device's local time is 09:05:42
    When the device refreshes the panel
    Then the top bar shows "09:05"

  @id:device-display.screen-layout.006 @rule:display.layout.orientation-from-settings @inferred @source:pico/display.py#get_epd
  Scenario Outline: The panel is laid out in landscape or portrait as the device settings say
    Given the device setting for landscape display is <landscape>
    When the device starts drawing on the panel
    Then the panel is laid out <orientation>, <width> pixels wide

    Examples:
      | landscape | orientation  | width |
      | on        | in landscape | 250   |
      | off       | in portrait  | 128   |
