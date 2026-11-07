@domain:configuration @area:shared-utilities @from:pico/textutil
Feature: Reading provider timestamps and fitting device text
  Serves device owners: provider readings land at the right hour on the timeline, provider queries go out intact, and error text on the e-ink panel stays readable.

  @id:configuration.shared-utilities.001 @rule:shared.timestamps.offsets-resolve-to-utc @verified @source:pico/textutil.py#iso_z_to_epoch @test:tests/test_textutil.py#test_utc_z @test:tests/test_textutil.py#test_fractional_seconds_are_dropped_not_rejected @test:tests/test_textutil.py#test_positive_offset_is_subtracted @test:tests/test_textutil.py#test_negative_offset_is_added @test:tests/test_textutil.py#test_minutes_in_the_offset_count @test:tests/test_textutil.py#test_missing_seconds_default_to_zero
  Scenario Outline: Provider timestamps are placed at the same UTC instant whatever their zone notation
    Given a provider reports a reading stamped "<stamp>"
    When the device reads the reading's time
    Then the reading is placed at <utc_instant>

    Examples:
      | stamp                     | utc_instant          |
      | 2026-01-01T00:00:00Z      | 2026-01-01 00:00 UTC |
      | 2026-01-01T00:00:00.000Z  | 2026-01-01 00:00 UTC |
      | 2026-01-01T01:00:00+01:00 | 2026-01-01 00:00 UTC |
      | 2025-12-31T19:00:00-05:00 | 2026-01-01 00:00 UTC |
      | 2026-01-01T05:30:00+05:30 | 2026-01-01 00:00 UTC |
      | 2026-01-01T00:00Z         | 2026-01-01 00:00 UTC |

  @id:configuration.shared-utilities.002 @rule:shared.timestamps.malformed-reading-is-skipped @verified @source:pico/textutil.py#iso_z_to_epoch @test:tests/test_textutil.py#test_garbage_is_none_rather_than_an_exception
  Scenario Outline: A reading with an unreadable timestamp is left out of the history instead of stopping the refresh
    Given a provider's history contains a reading stamped "<stamp>" alongside well-formed readings
    When the device builds the intensity history
    Then the reading stamped "<stamp>" is not in the history
    And the well-formed readings are still shown

    Examples:
      | stamp                |
      | (empty)              |
      | not a timestamp      |
      | 2026-13-45T99:99:99Z |

  @id:configuration.shared-utilities.003 @rule:shared.timestamps.compact-offset-ignored @inferred @source:pico/textutil.py#_split_zone @questionable
  Scenario: A timestamp whose offset has no colon is read as UTC
    Given a provider reports a reading stamped "2026-01-01T01:00:00+0100"
    When the device reads the reading's time
    Then the reading is placed at 2026-01-01 01:00 UTC, one hour later than the instant it names

  @id:configuration.shared-utilities.004 @rule:shared.query.reserved-characters-escaped @verified @source:pico/textutil.py#urlencode_simple @test:tests/test_textutil.py#test_pairs_are_joined_and_both_sides_escaped
  Scenario Outline: Query values sent to providers keep their meaning when they contain reserved characters
    Given a provider request carries the parameter "<name>" with the value "<value>"
    When the device builds the provider request
    Then the query string contains "<encoded>"

    Examples:
      | name | value   | encoded           |
      | a b  | c&d     | a%20b=c%26d       |
      | zone | 100%    | zone=100%25       |
      | q    | a=b+c?# | q=a%3Db%2Bc%3F%23 |

  @id:configuration.shared-utilities.005 @rule:display.text.error-detail-wraps-between-words @verified @source:pico/textutil.py#wrap_lines @test:tests/test_textutil.py#test_breaks_between_words_within_the_width @test:tests/test_textutil.py#test_short_text_is_one_line_and_long_text_stops_at_the_limit @test:tests/test_textutil.py#test_a_word_longer_than_the_line_is_cut_not_dropped
  Scenario Outline: Error details on the e-ink screen break between words within the panel width
    Given the device has no reading to show
    When the e-ink panel shows the detail "<detail>"
    Then the detail appears as the lines <lines>

    Examples:
      | detail                                     | lines                                            |
      | No reading yet - first fetch still running | "No reading yet - first fetch" / "still running" |
      | ready                                      | "ready"                                          |
      | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (35 x) | 29 x / 6 x                                       |

  @id:configuration.shared-utilities.006 @rule:display.text.overflow-beyond-last-line-dropped @verified @source:pico/textutil.py#wrap_lines @test:tests/test_textutil.py#test_short_text_is_one_line_and_long_text_stops_at_the_limit @questionable
  Scenario: Text that does not fit in the allowed lines is dropped without any marker
    Given an error detail is longer than three 29-character lines
    When the e-ink panel shows the detail
    Then exactly three lines are shown
    And the rest of the text is not shown and nothing shows that it was cut
