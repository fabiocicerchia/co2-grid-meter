@domain:carbon-data @area:providers @from:pico/ci-api-parse
Feature: Reading hourly grid intensity from the Carbon Intensity API
  Gives device owners an hourly carbon-intensity timeline from the keyless Carbon Intensity API that is placed at the right hour, uses the most complete emissions figure, and is never shown when it is stale or meaningless.

  Background:
    Given the Carbon Intensity API is the provider serving the device's country

  @id:carbon-data.providers.001 @rule:carbon-data.ci-api.reports-most-complete-figure @verified @source:pico/ci_api_parse.py#day_values @test:tests/test_ci_api_parse.py#test_reports_consumption_lifecycle_for_a_country @test:tests/test_ci_api_parse.py#test_falls_back_to_lifecycle_for_a_zone
  Scenario Outline: The reported intensity is the consumption lifecycle figure, falling back to lifecycle and then direct
    Given the day's data for <place> carries the figures <figures present>
    When the meter reads that day's hourly intensity
    Then the hourly values shown are the <figure used> figure

    Examples:
      | place                    | figures present                          | figure used           |
      | the country IT           | consumption lifecycle, lifecycle, direct | consumption lifecycle |
      | the bidding zone IT/SICI | lifecycle, direct                        | lifecycle             |
      | the country IT           | direct only                              | direct                |

  @id:carbon-data.providers.002 @rule:carbon-data.ci-api.unusable-day-ignored @verified @source:pico/ci_api_parse.py#day_values @test:tests/test_ci_api_parse.py#test_annual_average_is_rejected @test:tests/test_ci_api_parse.py#test_an_unexpected_step_is_refused_not_guessed @test:tests/test_ci_api_parse.py#test_a_day_of_only_nulls_has_no_figure
  Scenario Outline: A day whose data is not measured hourly figures contributes no readings
    Given the day's data for IT <problem>
    When the meter reads that day's hourly intensity
    Then no hour of that day appears in the timeline

    Examples:
      | problem                                   |
      | is an annual average rather than measured |
      | is reported in 30-minute steps            |
      | has no numeric value in any figure        |

  @id:carbon-data.providers.003 @rule:carbon-data.ci-api.missing-hour-keeps-position @verified @source:pico/ci_api_parse.py#hour_points @test:tests/test_ci_api_parse.py#test_a_null_hour_keeps_the_hours_after_it_in_place
  Scenario: A missing hour leaves a gap and later hours keep their own times
    Given the IT data for 2026-08-27 has 407 at 00:00, no value at 01:00 and 402 at 02:00
    When the meter reads that day's hourly intensity
    Then the timeline shows 407 at 00:00 UTC
    And the timeline shows 402 at 02:00 UTC
    And the timeline shows no reading at 01:00 UTC

  @id:carbon-data.providers.004 @rule:carbon-data.ci-api.stale-reading-refused @verified @source:pico/ci_api_parse.py#stale_error @test:tests/test_ci_api_parse.py#test_fresh_hour_passes @test:tests/test_ci_api_parse.py#test_missed_pipeline_run_is_rejected
  Scenario Outline: A current reading older than four hours is refused
    Given the newest measured hour for IT began <age> ago
    When the meter refreshes the current intensity
    Then the current reading is <outcome>

    Examples:
      | age                           | outcome                                                  |
      | 10 minutes                    | accepted                                                 |
      | 3 hours 59 minutes 59 seconds | accepted                                                 |
      | 4 hours 0 minutes 1 second    | refused with "newest reading is 14401s old (max 14400s)" |

  @id:carbon-data.providers.005 @rule:carbon-data.ci-api.window-spans-midnight @verified @source:pico/ci_api_parse.py#day_starts @test:tests/test_ci_api_parse.py#test_window_covers_the_day_on_each_side_of_midnight
  Scenario: A window crossing midnight UTC includes the hours on both days
    Given the meter needs hourly intensity from 23:30 UTC on 2026-08-26 to 00:30 UTC on 2026-08-27
    When the meter reads the hourly intensity for that window
    Then the data for both 2026-08-26 and 2026-08-27 is requested

  @id:carbon-data.providers.006 @rule:carbon-data.ci-api.bidding-zone-requested @verified @source:pico/ci_api_parse.py#history_path @test:tests/test_ci_api_parse.py#test_country_and_zone_paths
  Scenario Outline: A configured bidding zone is asked for instead of the national figure
    Given the device is set to country <country> and zone <zone>
    When the meter requests the day 2026-08-27
    Then the Carbon Intensity API is asked for <path>

    Examples:
      | country | zone   | path                           |
      | it      | (none) | /v2/IT/history/2026-08-27      |
      | IT      | sici   | /v2/IT/SICI/history/2026-08-27 |
