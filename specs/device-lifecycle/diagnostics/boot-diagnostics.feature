@domain:device-lifecycle @area:diagnostics @from:pico/diagnostics
Feature: Boot diagnostics without leaking location or secrets
  Lets the operator see at boot, and on /status, which network the device joined and where it thinks it is, so a wrong grid reading can be traced to a wrong geolocation, without exposing a home address or credentials.

  Background:
    Given the device has joined Wi-Fi
    And automatic location from the public IP is enabled

  @id:device-lifecycle.diagnostics.004 @rule:device.diagnostics.boot-log-network-location-isp @inferred @source:pico/diagnostics.py#boot_lines
  Scenario Outline: The boot log shows the network interface, the resolved location and the ISP
    Given the device's interface is ip 192.168.1.50, netmask 255.255.255.0, gateway 192.168.1.1, dns 1.1.1.1
    And the <service> geolocation answer places the device in <city>, <region>, <country> (<cc>) with ISP <isp>
    When the device boots
    Then the log shows "Network: ip 192.168.1.50 netmask 255.255.255.0 gateway 192.168.1.1 dns 1.1.1.1"
    And the log shows "Location: <location>"
    And the log shows "ISP: <isp>"

    Examples:
      | service    | city   | region | country  | cc | isp     | location              |
      | ipwho.is   | Berlin | Berlin | Germany  | DE | Telekom | Berlin, Germany (DE)  |
      | ipwho.is   | Lisbon | Lisbon | Portugal | PT | MEO     | Lisbon, Portugal (PT) |

  @id:device-lifecycle.diagnostics.005 @rule:device.diagnostics.coarse-location-only @inferred @source:pico/diagnostics.py#geo_summary @questionable
  Scenario Outline: Precise coordinates never appear in the diagnostics
    Given the geolocation answer places the device at latitude 52.52, longitude 13.405 in Berlin, Germany (DE)
    When the operator reads the <surface>
    Then it names Berlin, Germany (DE)
    And it contains no latitude or longitude value

    Examples:
      | surface                        |
      | boot diagnostics log lines     |
      | diagnostics section of /status |

  @id:device-lifecycle.diagnostics.006 @rule:device.diagnostics.no-credentials @inferred @source:pico/app.py#diagnostics_summary
  Scenario: Provider tokens never appear in the diagnostics
    Given provider API tokens are configured on the device
    When the operator reads the boot diagnostics or the diagnostics section of /status
    Then only network interface, coarse location and ISP details are shown
    And no configured token appears

  @id:device-lifecycle.diagnostics.007 @rule:device.diagnostics.location-text @inferred @source:pico/diagnostics.py#format_location
  Scenario Outline: The location shows what is known, once, and says unknown when nothing is
    Given the geolocation answer gives city "<city>", region "<region>", country "<country>" and country code "<cc>"
    When the device boots
    Then the log shows "Location: <location>"

    Examples:
      | city   | region | country | cc | location             |
      | Berlin | Berlin | Germany | DE | Berlin, Germany (DE) |
      | Oslo   |        |         | NO | Oslo (NO)            |
      |        | Bavaria |        | DE | Bavaria (DE)         |
      |        |        |         |    | unknown              |

  @id:device-lifecycle.diagnostics.008 @rule:device.diagnostics.missing-details-placeholders @inferred @source:pico/diagnostics.py#boot_lines
  Scenario: Missing network details and an unknown ISP do not break the boot log
    Given the network interface reports no details
    And geolocation found the city Oslo in country code NO but no ISP
    When the device boots
    Then the log shows "Network: ip ? netmask ? gateway ? dns ?"
    And the log shows "Location: Oslo (NO)"
    And no ISP line is logged
