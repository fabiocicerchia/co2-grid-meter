@domain:device-lifecycle @area:firmware-updates @from:pico/ota
Feature: Updating firmware over the air
  Lets an operator update a device they cannot physically reach, without a bad or interrupted update leaving it unbootable.

  Background:
    Given a device is running firmware version 1

  @id:device-lifecycle.firmware-updates.003 @rule:firmware.ota.only-verified-files-are-staged @verified @source:pico/ota.py#stage @test:tests/test_ota.py#test_a_corrupt_file_is_discarded_at_staging
  Scenario: A file that does not match its manifest is discarded
    Given the operator has started an update whose manifest lists main.py with its checksum and size
    When the device receives a main.py whose content does not match the manifest
    Then the update is refused with "main.py failed verification and was discarded"
    And no copy of the received main.py remains staged

  @id:device-lifecycle.firmware-updates.004 @rule:firmware.ota.all-or-nothing-activation @verified @source:pico/ota.py#verify @test:tests/test_ota.py#test_a_partial_update_never_activates
  Scenario: An update with any file missing never replaces the running firmware
    Given the operator has started an update of main.py and app.py
    And only main.py has been received
    When the operator activates the update
    Then the update is refused with "app.py was never staged"
    And the device still runs firmware version 1

  @id:device-lifecycle.firmware-updates.005 @rule:firmware.ota.recovery-code-and-paths-refused @verified @source:pico/ota.py#begin @test:tests/test_ota.py#test_the_recovery_code_is_never_updated_over_the_air @test:tests/test_ota.py#test_an_update_cannot_write_outside_the_flat_filesystem
  Scenario Outline: An update may not replace the recovery code or write outside the device's flat file area
    When the operator starts an update whose manifest names <file>
    Then the update is refused with "<message>"
    And nothing is staged

    Examples:
      | file       | message                                       |
      | boot.py    | boot.py is never updated over the air         |
      | ota.py     | ota.py is never updated over the air          |
      | ../evil.py | ../evil.py: updates are flat files, not paths |
      | lib/x.py   | lib/x.py: updates are flat files, not paths   |

  @id:device-lifecycle.firmware-updates.006 @rule:firmware.ota.healthy-boot-keeps-update @verified @source:pico/ota.py#mark_healthy @test:tests/test_ota.py#test_reaching_the_serving_loop_disarms_the_marker_and_frees_the_backup @test:tests/test_ota.py#test_a_healthy_boot_stops_the_attempt_count_growing @test:tests/test_ota.py#test_a_verified_update_replaces_the_firmware_and_arms_the_marker
  Scenario: New firmware that reaches its serving loop is kept
    Given the operator has activated a verified update to firmware version 2
    When the device boots firmware version 2 and reaches its serving loop
    Then the device keeps running firmware version 2
    And the update stage reads "idle"
    And later reboots no longer count as update attempts

  @id:device-lifecycle.firmware-updates.007 @rule:firmware.ota.unhealthy-firmware-rolls-back @verified @source:pico/ota.py#boot_check @test:tests/test_ota.py#test_firmware_that_never_gets_healthy_is_rolled_back @test:tests/test_ota.py#test_rollback_removes_a_file_the_update_added
  Scenario: Firmware that fails to reach its serving loop on three boots is rolled back
    Given the operator has activated a verified update to firmware version 2, which also adds newmod.py
    And firmware version 2 never reaches its serving loop
    When the device boots for the fourth time since activation
    Then the device prints "OTA: new firmware never reached the serving loop — rolled back"
    And the device runs firmware version 1 again
    And newmod.py is no longer on the device
    And the update stage reads "rolled_back"

  @id:device-lifecycle.firmware-updates.008 @rule:firmware.ota.power-loss-keeps-device-bootable @verified @source:pico/ota.py#activate @test:tests/test_ota.py#test_power_loss_mid_write_leaves_the_live_file_intact
  Scenario: Losing power during an update still leaves firmware that can boot
    Given the operator has staged a verified update to firmware version 2
    When the device loses power while the update is being activated
    Then main.py is still present and holds either version 1 or version 2 in full
    And the next boot treats the update as pending and counts it as an attempt

  @id:device-lifecycle.firmware-updates.009 @rule:firmware.ota.unreadable-state-boots-current-firmware @verified @source:pico/ota.py#read_state @test:tests/test_ota.py#test_power_loss_before_activation_leaves_an_unarmed_device @test:tests/test_ota.py#test_a_truncated_state_file_reads_as_no_update_in_flight @questionable
  Scenario Outline: An update interrupted before activation, or unreadable update state, leaves the current firmware running
    Given <situation>
    When the device boots
    Then the device boots firmware version 1 without counting an update attempt
    And the update stage reads "idle"

    Examples:
      | situation                                                     |
      | an update was started and partly received but never activated |
      | the saved update state was cut short by a power loss          |

  @id:device-lifecycle.firmware-updates.010 @rule:firmware.ota.outcome-visible-to-operator @verified @source:pico/ota.py#status @test:tests/test_ota.py#test_status_reports_what_an_update_did @questionable
  Scenario: The device reports what its last update did
    Given the operator has activated an update of app.py and main.py
    And the device has booted the new firmware once
    When the operator requests GET /system-info
    Then the response carries an ota block with stage "pending", attempts 1 and files ["app.py", "main.py"]
    And on a device without update support the ota block reads stage "unavailable"
