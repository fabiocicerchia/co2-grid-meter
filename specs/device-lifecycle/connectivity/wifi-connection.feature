@domain:device-lifecycle @area:connectivity @from:pico/fw-network
Feature: Joining Wi-Fi and reporting the connection
  Lets the device owner see whether the meter is online, how strong its Wi-Fi is, and why it is not reaching the network, without opening the device.

  Background:
    Given the device has Wi-Fi credentials in its settings

  @id:device-lifecycle.connectivity.001 @rule:device.connectivity.signal-bars-from-strength @inferred @source:pico/fw_network.py#wifi_signal_bars @questionable
  Scenario Outline: The Wi-Fi icon shows signal bars matching the received signal strength
    Given the device is connected to Wi-Fi
    And the received signal strength is <rssi>
    When the device refreshes its screen
    Then the Wi-Fi icon in the top bar shows <bars> bars

    Examples:
      | rssi                          | bars |
      | -50 dBm                       | 4    |
      | -55 dBm                       | 4    |
      | -60 dBm                       | 3    |
      | -70 dBm                       | 2    |
      | -80 dBm                       | 1    |
      | -85 dBm                       | 1    |
      | -90 dBm                       | 0    |
      | not reported by the radio     | 0    |
      | unreadable (the radio errors) | 4    |

  @id:device-lifecycle.connectivity.003 @rule:device.connectivity.join-gives-up-after-timeout @inferred @source:pico/fw_network.py#wifi_connect
  Scenario: Joining Wi-Fi gives up after 15 seconds and is retried once at boot
    Given the configured Wi-Fi network does not accept the device
    When the device boots
    Then the device tries to join for up to 15 seconds, twice
    And the device log reads "WiFi: not connected"
    And the device keeps starting without setting its clock from the network

  @id:device-lifecycle.connectivity.004 @rule:device.connectivity.log-full-interface-on-join @inferred @source:pico/fw_network.py#_log_interface
  Scenario Outline: On joining Wi-Fi the log shows address, netmask, gateway and DNS
    Given the Wi-Fi network gives the device address <ip>, netmask <netmask>, gateway <gateway> and DNS <dns>
    When the device joins Wi-Fi
    Then the device log reads "WiFi: connected <ip> netmask <netmask> gateway <gateway> dns <shown_dns>"

    Examples:
      | ip         | netmask       | gateway   | dns        | shown_dns  |
      | 192.0.2.10 | 255.255.255.0 | 192.0.2.1 | 192.0.2.53 | 192.0.2.53 |
      | 192.0.2.10 | 255.255.255.0 | 192.0.2.1 | (none)     | ?          |

  @id:device-lifecycle.connectivity.005 @rule:device.diagnostics.network-blank-when-offline @inferred @source:pico/fw_network.py#interface_summary
  Scenario Outline: The status diagnostics report the network interface only while connected
    Given the device is <state>
    When a client requests /status
    Then the diagnostics network ip, netmask, gateway and dns are <values>

    Examples:
      | state                                                  | values                                                    |
      | connected to Wi-Fi as 192.0.2.10 via gateway 192.0.2.1 | the interface's current address, netmask, gateway and DNS |
      | not connected to Wi-Fi                                 | all empty strings                                         |
