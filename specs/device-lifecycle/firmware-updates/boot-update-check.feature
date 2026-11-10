@domain:device-lifecycle @area:firmware-updates @from:pico/boot
Feature: Checking a firmware update at power-on
  Lets the device owner trust that a power cycle always brings the meter back up, and see on the serial console whether new firmware is on trial or was rolled back.

  Background:
    Given the device has been flashed with the meter firmware

  @id:device-lifecycle.firmware-updates.001 @rule:device-lifecycle.firmware-updates.boot-never-blocked-by-update-check @inferred @source:pico/boot.py#boot
  Scenario: A failing update check never stops the device from booting
    Given the updater is missing or fails while checking for a pending update
    When the device powers on
    Then the console shows "OTA: boot check skipped (<reason>)"
    And the installed firmware starts anyway

  @id:device-lifecycle.firmware-updates.002 @rule:device-lifecycle.firmware-updates.boot-announces-update-outcome @inferred @source:pico/boot.py#boot
  Scenario Outline: The console announces whether new firmware is on trial or was rolled back
    Given <update situation>
    When the device powers on
    Then the console shows "<message>"

    Examples:
      | update situation                                                                         | message                                                        |
      | a newly installed update has not yet proven healthy and is booting for the second time   | OTA: booting new firmware, attempt 2                           |
      | a newly installed update has used up its boot attempts without reaching the serving loop | OTA: new firmware never reached the serving loop — rolled back |
      | no update is pending                                                                     | (no OTA message)                                               |
