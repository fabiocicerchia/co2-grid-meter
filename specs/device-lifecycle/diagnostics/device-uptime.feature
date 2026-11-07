@domain:device-lifecycle @area:diagnostics @from:pico/uptime
Feature: Reporting device uptime
  Gives operators a trustworthy time-since-boot so they can tell a device that has run for days from one stuck in a reboot loop, even when Wi-Fi or the clock never came up.

  Background:
    Given the device firmware has booted

  @id:device-lifecycle.diagnostics.009 @rule:device.uptime.counts-from-boot-without-clock @verified @source:pico/uptime.py#Uptime @test:tests/test_uptime.py#test_starts_at_zero @test:tests/test_uptime.py#test_counts_elapsed_time @test:tests/test_uptime.py#test_accumulates_across_several_samples @test:tests/test_uptime.py#test_does_not_depend_on_the_wall_clock
  Scenario Outline: Uptime counts whole seconds since boot, independent of the wall clock
    Given the device clock has never been set from the network
    And the device has been running for <elapsed>
    When a client requests the device status
    Then the status reports uptime_seconds of <uptime_seconds>

    Examples:
      | elapsed                         | uptime_seconds |
      | 0 seconds                       | 0              |
      | 90 seconds                      | 90             |
      | 1 hour                          | 3600           |
      | 5 minutes sampled once a minute | 300            |

  @id:device-lifecycle.diagnostics.010 @rule:device.uptime.survives-counter-wrap @verified @source:pico/uptime.py#Uptime @test:tests/test_uptime.py#test_survives_the_ticks_wraparound @test:tests/test_uptime.py#test_survives_many_wraps_when_sampled_regularly @questionable
  Scenario: Uptime keeps counting past the twelve-day counter rollover
    Given the device has been running across one or more rollovers of its millisecond counter
    And uptime has been sampled at least every few days
    When a client requests the device status
    Then uptime_seconds equals the full time since boot, not the time since the last rollover

  @id:device-lifecycle.diagnostics.011 @rule:device.uptime.never-decreases @verified @source:pico/uptime.py#Uptime @test:tests/test_uptime.py#test_a_counter_going_backwards_does_not_shrink_uptime
  Scenario: Reported uptime never goes down while the device stays up
    Given the device status last reported uptime_seconds of 60
    And the device's counter has since jumped backwards by 30 seconds
    When a client requests the device status
    Then the status reports uptime_seconds of 60

  @id:device-lifecycle.diagnostics.012 @rule:device.uptime.human-readable-format @verified @source:pico/uptime.py#format_uptime @test:tests/test_uptime.py#TestFormat
  Scenario Outline: Uptime in the firmware log shows the largest three time units
    Given the device has been up for <seconds> seconds
    When the firmware writes uptime to its log
    Then the uptime reads "<text>"

    Examples:
      | seconds | text      |
      | 0       | 0s        |
      | -5      | 0s        |
      | 45      | 45s       |
      | 125     | 2m 5s     |
      | 3725    | 1h 2m 5s  |
      | 274327  | 3d 4h 12m |
      | 777600  | 9d 0h 0m  |
