@domain:device-display @area:languages @from:pico/i18n
Feature: Showing device text in the configured language
  Lets a non-English owner read the e-ink panel in their own language, and makes sure a missing or broken translation never leaves a line blank or loses the reading.

  Background:
    Given the device ships the languages English ("en") and Italian ("it")

  @id:device-display.languages.001 @rule:device-display.languages.configured-language-shown @verified @source:pico/i18n.py#t @test:tests/test_i18n.py#test_english_by_default @test:tests/test_i18n.py#test_a_shipped_locale @test:tests/test_i18n.py#test_formatting_arguments
  Scenario Outline: The panel speaks the configured language
    Given the device language is set to "<language>"
    And the current reading is in the cleanest quarter of last week's readings
    When the device refreshes its panel
    Then the verdict reads "<verdict>"
    And the reason given with the verdict reads "<reason>"
    And the reading line reads "<co2_line>"

    Examples:
      | language | verdict | reason             | co2_line       |
      | en       | RUN NOW | Cleaner than avg   | CO2: 412 g/kWh |
      | it       | ORA     | Meglio della media | CO2: 412 g/kWh |

  @id:device-display.languages.002 @rule:device-display.languages.unknown-language-falls-back-to-english @verified @source:pico/i18n.py#set_language @test:tests/test_i18n.py#test_an_unknown_language_falls_back_to_english @test:tests/test_i18n.py#test_the_fallback_is_reported_not_silent @test:tests/test_i18n.py#test_case_and_whitespace_are_tolerated @questionable
  Scenario Outline: An unsupported language falls back to English and the boot log says so
    Given the device language is set to "<configured>"
    When the device boots
    Then the panel text is in <shown>
    And the boot log <log>

    Examples:
      | configured | shown   | log                                             |
      | kli        | English | reads "Unknown language 'kli', using en"        |
      | (empty)    | English | reads "Unknown language '', using en"           |
      | it         | Italian | has no language warning                         |
      | IT         | Italian | still reads "Unknown language 'IT', using it"   |

  @id:device-display.languages.003 @rule:device-display.languages.never-blank-line @verified @source:pico/i18n.py#t @test:tests/test_i18n.py#test_a_missing_key_renders_the_english_default @test:tests/test_i18n.py#test_an_unknown_key_renders_the_key_not_a_blank
  Scenario Outline: A missing translation shows English text instead of a blank line
    Given the device language is set to "it"
    And the text "<text>" <availability>
    When the device refreshes its panel
    Then that line reads "<shown>"

    Examples:
      | text            | availability                       | shown           |
      | offline label   | has no Italian translation         | Offline         |
      | label.new_thing | has no translation in any language | label.new_thing |

  @id:device-display.languages.004 @rule:device-display.languages.broken-translation-keeps-reading @verified @source:pico/i18n.py#t @test:tests/test_i18n.py#test_a_locale_with_broken_placeholders_falls_back_to_english
  Scenario: A translation with broken placeholders still shows the reading in English
    Given the device language is set to "it"
    And the Italian CO2 line has lost its number placeholder
    When the device shows a reading of 412 g/kWh
    Then the reading line reads "CO2: 412 g/kWh"

  @id:device-display.languages.005 @rule:device-display.languages.translated-verdict-keeps-styling @inferred @source:pico/display.py#draw_current_panel
  Scenario Outline: A good verdict in any language is not drawn as a warning
    Given the device language is set to "<language>"
    And the verdict is "<verdict>"
    When the device refreshes its panel
    Then the verdict panel is drawn <style>

    Examples:
      | language | verdict | style                         |
      | it       | ORA     | in black, showing the verdict |
      | it       | OK      | in black, showing the verdict |
      | it       | ATTENDI | in red, showing the wait line |

  @id:device-display.languages.006 @rule:device-display.languages.baseline-text-untranslated @inferred @source:pico/recommendation.py#compute_recommendation @questionable
  Scenario: While collecting a baseline, the reason line stays in English on a non-English device
    Given the device language is set to "it"
    And the device has fewer than 24 hourly readings from last week
    When the device refreshes its panel
    Then the verdict reads "OK"
    And the recommendation's reason is the English "Collecting baseline", which the panel does not draw because the verdict is not a warning
