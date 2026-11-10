@domain:device-lifecycle @area:connectivity @from:pico/http
Feature: Keeping the device online and reachable
  Assures the operator that the device keeps its clock right and keeps answering on the network through Wi-Fi drops and idle clients, and shows what happens after an unexpected error.

  Background:
    Given the device is running and serving on its configured port

  @id:device-lifecycle.connectivity.006 @rule:device-lifecycle.connectivity.wifi-reconnect-resumes-service @inferred @source:pico/http.py#ensure_connected
  Scenario: After Wi-Fi drops the device reconnects, resets its clock and answers again
    Given the device's Wi-Fi connection has dropped
    When the device notices the drop on its next loop
    Then it rejoins Wi-Fi
    And it resets its clock from network time
    And it answers web requests again on the configured port
    And if rejoining fails it stops answering and retries about a second later

  @id:device-lifecycle.connectivity.008 @rule:device-lifecycle.connectivity.silent-client-dropped @inferred @source:pico/http.py#get_connection
  Scenario: A client that connects but never sends a request cannot freeze the device
    Given a browser has opened a connection to the device and sends nothing
    When 5 seconds pass
    Then the device drops that connection without replying
    And the display keeps refreshing and other clients are answered

  @id:device-lifecycle.connectivity.009 @rule:device-lifecycle.connectivity.server-recovers-after-loop-error @inferred @source:pico/http.py#serve_forever @questionable
  Scenario: After an unexpected error in its loop the device stops answering until Wi-Fi drops
    Given Wi-Fi stays connected
    And a client disconnects mid-reply, so sending both the reply and the error reply fails
    When the device's loop hits that error
    Then the device stops accepting web requests
    And the display keeps refreshing
    And web requests are answered again only after the next Wi-Fi reconnect or a reboot
