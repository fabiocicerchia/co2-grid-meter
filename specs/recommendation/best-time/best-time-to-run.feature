@domain:recommendation @area:best-time @from:pico/recommendation
Feature: Telling the user when the next cleanest hour is
  Gives a household a concrete time to run a postponed load, predicted from the cleanest hour in the same 12-hour stretch last week.

  Background:
    Given at least 24 of last week's readings are available

  @id:recommendation.best-time.001 @rule:recommendation.best-time.cleanest-hour-next-12h @inferred @source:pico/recommendation.py#_compute_next_best @questionable
  Scenario: The best time is the hour that was cleanest in the same next 12 hours last week
    Given the current intensity is not among the cleanest quarter of last week's readings
    And exactly one week ago, the reading 3 hours later than now was the lowest in the following 12 hours
    When the device works out its recommendation
    Then the next best time reads "in 3h (<local time 3 hours from now>)"
    And the wait is 3 hours

  @id:recommendation.best-time.002 @rule:recommendation.best-time.run-now-means-now @inferred @source:pico/recommendation.py#compute_recommendation
  Scenario: When it is a good time to run, the best time is now
    Given no more than a quarter of last week's readings are lower than the current intensity
    When the device works out its recommendation
    Then the verdict is "RUN NOW"
    And the next best time is "Now"
    And the wait is 0 hours

  @id:recommendation.best-time.003 @rule:recommendation.best-time.no-forecast-recheck @inferred @source:pico/recommendation.py#_compute_next_best @questionable
  Scenario Outline: Without last week's readings for the coming hours the device asks to recheck
    Given <share> of last week's readings are lower than the current intensity
    And none of last week's readings fall in the same 12 hours ahead
    When the device works out its recommendation
    Then the verdict is "<verdict>"
    And the next best time is "recheck"
    And the wait is <wait>

    Examples:
      | share | verdict | wait      |
      | 40%   | OK      | 0 hours   |
      | 75%   | WAIT    | not given |
