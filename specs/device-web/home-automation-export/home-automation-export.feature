@domain:device-web @area:home-automation-export @from:pico/export
Feature: Exporting grid readings for home automation and spreadsheets
  Gives Home Assistant users and spreadsheet users a CSV of the rolling window and one flat summary object, so they can automate on the reading without parsing the dashboard's payload.

  Background:
    Given the device has a rolling window of hourly carbon-intensity readings

  @id:device-web.home-automation-export.001 @rule:device-web.export.csv-window-format @verified @source:pico/export.py#window_csv @test:tests/test_export.py#test_csv_has_a_documented_header_and_one_row_per_point @test:tests/test_export.py#test_csv_writes_whole_numbers_without_a_trailing_zero
  Scenario Outline: The window CSV has a fixed header and one row per hourly reading
    Given the window holds a reading of <reading> gCO2eq/kWh at 2026-09-01T10:00:00Z
    When a spreadsheet user downloads /em/window.csv
    Then the first line is "datetime,epoch,carbon_intensity"
    And the next line is "2026-09-01T10:00:00Z,1788256800,<written>"
    And every line ends with CRLF, including the last

    Examples:
      | reading   | written |
      | 430       | 430     |
      | 430.0     | 430     |
      | 412.5     | 412.5   |
      | 412.12345 | 412.123 |

  @id:device-web.home-automation-export.002 @rule:device-web.export.csv-drops-incomplete-readings @verified @source:pico/export.py#history_rows @test:tests/test_export.py#test_csv_drops_holes_rather_than_emitting_half_a_row
  Scenario Outline: Readings with no timestamp or no usable value are left out of the CSV
    Given the window holds a complete reading of 430 at 10:00 and one of 390 at 14:00
    And the window also holds a reading <defect>
    When a spreadsheet user downloads /em/window.csv
    Then the CSV holds the header and exactly two rows
    And the rows end in 430 and 390
    And no row has an empty column

    Examples:
      | defect                             |
      | with no value at 11:00             |
      | of 400 with no timestamp           |
      | with the value "nonsense" at 13:00 |

  @id:device-web.home-automation-export.003 @rule:device-web.export.non-finite-reading-breaks-export @inferred @source:pico/export.py#_number @questionable
  Scenario Outline: A NaN or infinite reading makes the whole export fail instead of being skipped
    Given the window holds a reading of 430 at 10:00
    And the window holds a reading of "<value>" at 11:00
    When a Home Assistant sensor polls <endpoint>
    Then the device answers with an internal error instead of the export
    And the reading of 430 is not delivered either

    Examples:
      | value | endpoint       |
      | NaN   | /em/window.csv |
      | inf   | /em/window.csv |
      | NaN   | /em/summary    |

  @id:device-web.home-automation-export.004 @rule:device-web.export.csv-bounded-newest-rows @verified @source:pico/export.py#history_rows @test:tests/test_export.py#test_csv_is_bounded_and_keeps_the_newest_rows
  Scenario: The window CSV is capped at two weeks of rows and keeps the newest
    Given the window holds more than 336 hourly readings
    When a spreadsheet user downloads /em/window.csv with back_hours=720
    Then the CSV holds the header and 336 rows
    And the rows are the 336 most recent readings
    And the oldest readings are left out

  @id:device-web.home-automation-export.005 @rule:device-web.export.csv-time-ordered @verified @source:pico/export.py#history_rows @test:tests/test_export.py#test_rows_come_out_in_time_order_whatever_the_provider_did
  Scenario: CSV rows come out oldest first whatever order the provider sent
    Given the provider sent readings for 12:00, 10:00 and 11:00 in that order
    When a spreadsheet user downloads /em/window.csv
    Then the rows are in the order 10:00, 11:00, 12:00

  @id:device-web.home-automation-export.006 @rule:device-web.export.csv-empty-window-header-only @verified @source:pico/export.py#window_csv @test:tests/test_export.py#test_csv_of_an_empty_window_is_a_header_not_an_error
  Scenario: An empty window exports as a header-only CSV, not an error
    Given the window holds no readings
    When a spreadsheet user downloads /em/window.csv
    Then the body is exactly "datetime,epoch,carbon_intensity" followed by CRLF

  @id:device-web.home-automation-export.007 @rule:device-web.export.summary-flat-verdict @verified @source:pico/export.py#summary_from_window @test:tests/test_export.py#test_summary_is_flat_and_carries_no_history
  Scenario: The summary is one flat object with the current reading, the verdict and the window's range
    Given the device is in Lisbon, PT, served by electricity_maps
    And the window holds readings of 430, 412.5 and 380
    And the current reading is 380 and the recommendation is OK, "below the weekly median"
    When a Home Assistant sensor polls /em/summary
    Then carbon_intensity is 380 and unit is "gCO2eq/kWh"
    And verdict is "OK", reason is "below the weekly median", wait_hours is null
    And window_points is 3, window_min is 380, window_max is 430
    And city is "Lisbon", cc is "PT", provider is "electricity_maps"
    And the object has no history field

  @id:device-web.home-automation-export.008 @rule:device-web.export.summary-tolerates-missing-data @verified @source:pico/export.py#summary_from_window @test:tests/test_export.py#test_summary_survives_an_empty_window_and_a_missing_recommendation @questionable
  Scenario: With no window readings and no recommendation the summary reports nulls instead of failing
    Given the window holds no usable readings
    And there is no recommendation
    When a Home Assistant sensor polls /em/summary
    Then window_points is 0
    And window_min and window_max are null
    And verdict and wait_hours are null
