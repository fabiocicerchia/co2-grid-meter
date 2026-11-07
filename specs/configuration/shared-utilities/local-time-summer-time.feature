@domain:configuration @area:shared-utilities @from:pico/timeutil
Feature: Keeping the device clock on local time across summer-time changes
  Serves people reading times on the device and its pages, who expect the clock to match their wall clock on both sides of the March and October changes.

  Background:
    Given the device is configured with a standard UTC offset and whether its zone observes EU summer time

  @id:configuration.shared-utilities.007 @rule:time.local-clock.eu-summer-time-switches-at-0100-utc @verified @source:pico/timeutil.py#is_eu_summer_time @test:tests/test_timeutil.py#test_spring_forward_happens_at_0100_utc_not_midnight @test:tests/test_timeutil.py#test_fall_back_happens_at_0100_utc @test:tests/test_timeutil.py#test_months_well_inside_each_season @test:tests/test_timeutil.py#test_offset_is_plus_one_in_winter_and_plus_two_in_summer
  Scenario Outline: Summer time starts and ends at 01:00 UTC on the last Sunday of March and October
    Given the device is configured for a zone at UTC+1 that observes EU summer time
    When the device sets its clock at <utc_instant>
    Then the device shows local time as UTC<offset>

    Examples:
      | utc_instant          | offset |
      | 2026-03-28 23:00 UTC | +1     |
      | 2026-03-29 00:59 UTC | +1     |
      | 2026-03-29 01:00 UTC | +2     |
      | 2026-07-01 12:00 UTC | +2     |
      | 2026-10-25 00:59 UTC | +2     |
      | 2026-10-25 01:00 UTC | +1     |
      | 2026-12-15 12:00 UTC | +1     |

  @id:configuration.shared-utilities.008 @rule:time.local-clock.configured-zone-offset @verified @source:pico/timeutil.py#utc_offset_seconds @test:tests/test_timeutil.py#test_a_zone_that_does_not_observe_dst_never_shifts @test:tests/test_timeutil.py#test_offset_is_plus_one_in_winter_and_plus_two_in_summer
  Scenario Outline: The clock follows the configured standard offset, adding an hour in summer only where summer time is observed
    Given the device is configured with standard offset UTC<standard> and summer time observed: <observes>
    When the device sets its clock at 2026-07-01 12:00 UTC
    Then the device shows local time as UTC<offset>

    Examples:
      | standard | observes | offset |
      | +1       | yes      | +2     |
      | +0       | yes      | +1     |
      | +8       | no       | +8     |
