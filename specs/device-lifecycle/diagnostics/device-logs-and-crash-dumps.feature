@domain:device-lifecycle @area:diagnostics @from:pico/config
Feature: Keeping device logs and crash records
  Serves the operator diagnosing a meter: messages go to daily log files on the device with bounded retention, and failures leave a crash record behind.

  Background:
    Given the device writes its own logs to its flash filesystem

  @id:device-lifecycle.diagnostics.001 @rule:device.logs.daily-log-file @verified @source:pico/config.py#append_log_line @test:tests/test_flash_lock.py#test_a_log_line_waits_for_whoever_holds_the_flash_lock
  Scenario: Each firmware message is appended to the log file for the current day
    Given the device clock reads 2026-11-07
    When the firmware logs the message "Wi-Fi connected"
    Then logs/2026-11-07.log gains a line starting with the Unix timestamp in brackets
    And the line ends with the level and "Wi-Fi connected"

  @id:device-lifecycle.diagnostics.002 @rule:device.logs.two-day-retention @inferred @source:pico/config.py#prune_old_logs
  Scenario: Only the two most recent daily log files are kept
    Given the device holds log files for 2026-11-04, 2026-11-05 and 2026-11-06
    When the firmware logs its first message on 2026-11-07
    Then only the log files for 2026-11-06 and 2026-11-07 remain

  @id:device-lifecycle.diagnostics.003 @rule:device.logs.crash-record-kept @inferred @source:pico/config.py#write_crashdump @questionable
  Scenario: A failure leaves a crash record naming when, where and what went wrong
    Given the device is serving requests
    When handling a web request fails with the error "out of memory"
    Then a file crashdumps/http-<timestamp>.txt exists
    And it records the timestamp, context=http and error=out of memory
    And the day's log gains an ERROR line pointing at that file
