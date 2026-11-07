@domain:device-web @area:data-api @from:pico/http
Feature: Restricting device access with an API token
  Lets an operator on an untrusted network require a bearer token before the device reveals its data, pages or network details, while home installs stay open.

  Background:
    Given the device is serving its web interface on the local network

  @id:device-web.data-api.008 @rule:device-web.access.open-without-token @verified @source:pico/http.py#authorized @test:tests/test_http_auth.py#test_no_token_configured_leaves_every_route_open @test:tests/test_http_auth.py#test_a_whitespace_only_token_is_no_token
  Scenario Outline: With no token configured every route answers without credentials
    Given the device has <configured token> as its API token
    When a client requests <path> without an Authorization header
    Then the response status is 200

    Examples:
      | configured token        | path           |
      | no                      | /system-info   |
      | no                      | /status        |
      | no                      | /em/window.csv |
      | no                      | /html/         |
      | only whitespace ("   ") | /status        |

  @id:device-web.data-api.009 @rule:device-web.access.token-required-on-every-route @verified @source:pico/http.py#process_http_request @test:tests/test_http_auth.py#test_a_configured_token_is_required_on_every_route @test:tests/test_http_auth.py#test_system_info_discloses_nothing_without_the_token @test:tests/test_http_auth.py#test_unknown_paths_are_refused_before_they_are_looked_up @test:tests/test_http_auth.py#test_handle_http_request_threads_the_header_through
  Scenario Outline: With a token configured every route, known or not, requires it
    Given the device has the API token "s3cret-token"
    When a client requests <path> with <authorization>
    Then the response status is <status>
    And a refused response does not contain the device's IP address

    Examples:
      | path           | authorization                      | status |
      | /system-info   | no Authorization header            | 401    |
      | /system-info   | Authorization: Bearer s3cret-token | 200    |
      | /status        | no Authorization header            | 401    |
      | /status        | Authorization: Bearer s3cret-token | 200    |
      | /em/window.csv | no Authorization header            | 401    |
      | /html/         | no Authorization header            | 401    |
      | /html/         | Authorization: Bearer s3cret-token | 200    |
      | /no-such-route | no Authorization header            | 401    |

  @id:device-web.data-api.010 @rule:device-web.access.uniform-refusal @verified @source:pico/http.py#authorized @test:tests/test_http_auth.py#test_every_wrong_credential_gets_the_same_answer
  Scenario Outline: Every wrong credential gets the same refusal
    Given the device has the API token "s3cret-token"
    When a client requests /status with <authorization>
    Then the response status is 401
    And the response body is {"error": "Unauthorized"}

    Examples:
      | authorization                      |
      | no Authorization header            |
      | Authorization: Bearer wrong-token- |
      | Authorization: Bearer s3cret-toke  |
      | Authorization: Basic s3cret-token  |
      | Authorization: s3cret-token        |
      | Authorization: Bearer              |

  @id:device-web.data-api.011 @rule:device-web.access.token-matching-tolerance @verified @source:pico/http.py#authorized @test:tests/test_http_auth.py#test_the_scheme_is_case_insensitive @test:tests/test_http_auth.py#test_whitespace_around_the_configured_token_is_ignored @test:tests/test_http_auth.py#test_a_non_string_token_is_enforced_as_its_text
  Scenario Outline: The token matches regardless of scheme case, surrounding whitespace or settings type
    Given the device's API token is set to <configured token> in its settings
    When a client requests /status with <authorization>
    Then the response status is <status>

    Examples:
      | configured token  | authorization                      | status |
      | "s3cret-token"    | Authorization: bearer s3cret-token | 200    |
      | " s3cret-token\n" | Authorization: Bearer s3cret-token | 200    |
      | " s3cret-token\n" | no Authorization header            | 401    |
      | 123456 (a number) | Authorization: Bearer 123456       | 200    |
      | 123456 (a number) | no Authorization header            | 401    |
      | true (a boolean)  | Authorization: Bearer True         | 200    |
