@domain:device-display @area:screen-layout @from:pico/fw-render
Feature: Showing the current reading and advice on the e-ink panel
  Serves the person glancing at the device: the panel must show the current intensity, the run/wait advice and a readable line under it, and keep refreshing on its own even when nobody opens the web pages.

  Background:
    Given the device has a working e-ink panel

  @id:device-display.screen-layout.007 @rule:device-display.screen.advice-line-wait-or-reason @verified @source:pico/fw_render.py#make_next_line @test:tests/test_fw_render.py#test_the_wait_line_obeys_the_same_limit @test:tests/test_fw_render.py#test_a_short_reason_is_untouched_and_a_missing_one_is_empty
  Scenario Outline: The advice line shows how long to wait, otherwise the reason
    Given the latest recommendation has verdict "<verdict>", wait hours <wait_hours> and reason "<reason>"
    And the device clock reads 11:00 local time
    When the device redraws the screen
    Then the verdict is taken as "<shown_verdict>", which is not "RUN NOW" or "OK", so the panel draws the advice line in its place
    And the advice line reads "<line>"

    Examples:
      | verdict   | wait_hours | reason                          | shown_verdict | line            |
      | WAIT      | 3          | Grid is much dirtier than usual | WAIT          | WAIT 3h (14:00) |
      | RUN       | 0          | Cleaner                         | RUN           | Cleaner         |
      | RUN       | none       |   Cleaner                       | RUN           | Cleaner         |
      | (missing) | none       | (missing)                       | —             |                 |

  @id:device-display.screen-layout.008 @rule:device-display.screen.advice-line-fits-panel @verified @source:pico/fw_render.py#next_line_chars @test:tests/test_fw_render.py#test_the_limit_is_derived_from_the_panel_width @test:tests/test_fw_render.py#test_the_line_ends_inside_the_panel_interior @test:tests/test_fw_render.py#test_a_long_reason_is_cut_between_words_to_fit @test:tests/test_fw_render.py#test_the_wait_line_obeys_the_same_limit @test:tests/test_fw_render.py#test_render_screen_fits_the_line_to_the_panel_it_draws_on
  Scenario Outline: The advice line is cut between words to fit the panel width
    Given the device panel is in <orientation> orientation, <width> pixels wide
    And the advice line would read "<full_line>"
    When the device redraws the screen
    Then at most <max_chars> characters are shown
    And the line reads "<shown>", ending on a whole word

    Examples:
      | orientation | width | full_line                                     | max_chars | shown                     |
      | landscape   | 250   | Grid is much dirtier than usual for this hour | 29        | Grid is much dirtier than |
      | portrait    | 128   | Grid is much dirtier than usual for this hour | 13        | Grid is much              |
      | landscape   | 250   | WAIT 3h (14:00)                               | 29        | WAIT 3h (14:00)           |
      | portrait    | 128   | WAIT 3h (14:00)                               | 13        | WAIT 3h                   |

  @id:device-display.screen-layout.009 @rule:device-display.screen.data-error-screen @inferred @source:pico/fw_render.py#_display_tick
  Scenario Outline: When fresh data cannot be obtained the panel shows a data error with the reason
    Given the device cannot get a reading because "<error>"
    When the device's periodic screen refresh runs
    Then the panel is cleared and shows the title "DATA ERROR"
    And the reason is shown in red on up to 3 lines of at most 29 characters, broken between words
    And the Wi-Fi indicator and clock are shown at the top

    Examples:
      | error                                                                        |
      | provider request timed out after 10 seconds while contacting api.example.com |

  @id:device-display.screen-layout.010 @rule:device-display.screen.periodic-refresh @inferred @source:pico/fw_render.py#_display_tick
  Scenario Outline: The panel refreshes on its own schedule, no more often than the configured interval
    Given the minimum render interval is configured as <interval> seconds
    And the panel was last redrawn <elapsed> seconds ago
    And nobody has opened the device's status page
    When the device's periodic screen refresh runs
    Then the panel is <outcome>

    Examples:
      | interval | elapsed | outcome                         |
      | 60       | 30      | left unchanged                  |
      | 60       | 60      | redrawn with the latest reading |
      | 60       | 300     | redrawn with the latest reading |

  @id:device-display.screen-layout.011 @rule:device-display.screen.led-bar-needs-week-history @inferred @source:pico/fw_render.py#week_percentile @questionable
  Scenario Outline: The LED bar stays empty until half a day of last week's readings is available
    Given the device has <hours> hours of readings from the same period last week
    When the device redraws the screen
    Then the LED bar <leds>
    And the intensity zone worked out is <zone>, although the panel does not draw the zone

    Examples:
      | hours | leds                                                                            | zone                          |
      | 4     | is empty                                                                        | mid                           |
      | 11    | is empty                                                                        | mid                           |
      | 12    | is lit in proportion to where the current reading ranks in last week's readings | low, mid or high by that rank |

  @id:device-display.screen-layout.012 @rule:device-display.screen.missing-intensity-shows-zero @inferred @source:pico/fw_render.py#render_screen @questionable
  Scenario: A reading with no intensity value is shown as 0
    Given the latest status has no usable carbon intensity value
    When the device redraws the screen
    Then the current intensity shown is 0
