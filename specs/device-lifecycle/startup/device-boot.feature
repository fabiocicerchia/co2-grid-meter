@domain:device-lifecycle @area:startup @from:pico/pico
Feature: Booting the device
  Gives the device owner a firmware boot that reports bad settings by name, keeps serving when optional steps fail, and keeps a new firmware update once the boot completes.

  Background:
    Given the firmware is installed on the device

  @id:device-lifecycle.startup.001 @rule:device.startup.invalid-settings-stop-boot @inferred @source:pico/main.py#main @questionable
  Scenario: A device with missing or invalid settings refuses to start and names the problem
    Given the device settings file is missing a required value such as the Wi-Fi password
    When the device boots
    Then the device log shows a line starting with "FATAL:" followed by the settings problem
    And the device does not join Wi-Fi or start serving
    And no crash dump is written for this failure

  @id:device-lifecycle.startup.002 @rule:device.startup.unknown-language-reported @inferred @source:pico/main.py#main
  Scenario Outline: An unknown display language falls back to English and the fallback is logged
    Given the device's configured language is "<configured>", which the device does not support
    When the device boots
    Then the panel text is shown in English
    And the device log shows "Unknown language '<configured>', using en"

    Examples:
      | configured |
      | xx         |
      | klingon    |

  @id:device-lifecycle.startup.003 @rule:device.startup.serves-without-network @inferred @source:pico/main.py#main
  Scenario: A device that cannot join Wi-Fi at boot still starts serving, without setting its clock
    Given the configured Wi-Fi network cannot be reached
    When the device boots
    Then the device tries to join Wi-Fi twice
    And the device clock is not set from the network
    And the device goes on to show its "Waiting for data..." boot screen and serve requests

  @id:device-lifecycle.startup.004 @rule:device.startup.diagnostics-never-block-serving @inferred @source:pico/main.py#main
  Scenario: Failing boot diagnostics never stop the device from serving
    Given the boot diagnostics cannot run
    When the device boots
    Then the device log shows "Diagnostics unavailable:" with the reason
    And the device log shows "Uptime at start of serving:" with the uptime
    And the device starts serving requests

  @id:device-lifecycle.startup.005 @rule:device.firmware-updates.kept-on-healthy-boot @verified @source:pico/main.py#main @test:tests/test_ota.py#test_reaching_the_serving_loop_disarms_the_marker_and_frees_the_backup @test:tests/test_ota.py#test_a_healthy_boot_stops_the_attempt_count_growing
  Scenario: A new firmware update is kept once the device reaches serving, whether or not a provider is reachable
    Given a firmware update has just been activated and is waiting to prove itself
    And no carbon-intensity provider is reachable
    When the device boots the new firmware
    Then the device log shows "OTA: new firmware reached the serving loop — update kept"
    And the update is no longer rolled back on later boots
    And the previous firmware backup is removed

  @id:device-lifecycle.startup.006 @rule:device.startup.crash-leaves-dump @inferred @source:pico/main.py
  Scenario: An unexpected crash leaves a crash dump the operator can find from the log
    Given the device hits an unexpected error while booting, before its request loop is running
    When the firmware stops
    Then a crash dump file named after the "http" context and the time is written, recording the timestamp, context and error message
    And the device log shows "ERROR" followed by the crash dump's path
