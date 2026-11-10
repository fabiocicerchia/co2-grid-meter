@domain:recommendation @area:advice @from:pico/recommendation
Feature: Advising whether to run now or wait
  Tells a household whether now is a clean, average or dirty time to run flexible loads, by ranking the current grid intensity against the same period last week.

  Background:
    Given the device knows the current grid carbon intensity
    And the device has last week's hourly readings for the period from 48 hours before to 12 hours after this hour

  @id:recommendation.advice.001 @rule:recommendation.advice.verdict-by-weekly-percentile @verified @source:pico/recommendation.py#compute_recommendation @test:tests/test_recommendation.py#test_compute_recommendation_run_now_for_low_percentile @test:tests/test_recommendation.py#test_compute_recommendation_wait_for_high_percentile
  Scenario Outline: The verdict follows where the current intensity ranks among last week's readings
    Given at least 24 of last week's readings are available
    And <share> of last week's readings are lower than the current intensity
    When the device works out its recommendation
    Then the verdict is "<verdict>"
    And the reason is "<reason>"

    Examples:
      | share | verdict | reason           |
      | 10%   | RUN NOW | Cleaner than avg |
      | 25%   | RUN NOW | Cleaner than avg |
      | 40%   | OK      | Around average   |
      | 50%   | OK      | Around average   |
      | 75%   | WAIT    | Dirtier than avg |

  @id:recommendation.advice.002 @rule:recommendation.advice.baseline-required @verified @source:pico/recommendation.py#compute_recommendation @test:tests/test_recommendation.py#test_compute_recommendation_collecting_baseline @questionable
  Scenario: Without a day of last week's readings the device says it is still collecting a baseline
    Given fewer than 24 of last week's readings carry an intensity value
    When the device works out its recommendation
    Then the verdict is "OK"
    And the reason is "Collecting baseline"
    And the next best time is "recheck" with no wait hours
