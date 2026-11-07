@domain:device-display @area:intensity-graph @from:pico/fw-graph
Feature: Drawing the intensity graph on the e-ink panel
  Gives the person looking at the device a 60-hour picture of grid carbon intensity (two days back, twelve hours ahead) against last week's pattern and the clean/dirty cutoffs, so they can see at a glance whether now is a good time.

  Background:
    Given the device timeline shows 48 hours back and 12 hours ahead, one point per hour
    And the green cutoff is the 25th percentile and the yellow cutoff is the 50th percentile

  @id:device-display.intensity-graph.001 @rule:device-display.intensity-graph.current-solid-last-week-dotted @inferred @source:pico/fw_graph.py#draw_graph
  Scenario: The current timeline is a solid line and the same hours last week are a dotted line under it
    Given the device has hourly intensity readings for the current timeline
    And the device has readings for the same hours one week earlier
    When the device redraws its screen
    Then the current timeline is drawn as a solid black line across the graph
    And last week's readings are drawn as a dotted black line on the same hour-for-hour axis
    And both lines share one vertical scale running from the lowest to the highest reading of either line

  @id:device-display.intensity-graph.002 @rule:device-display.intensity-graph.missing-hours-leave-gaps @inferred @source:pico/fw_graph.py#draw_series
  Scenario: Hours without a reading leave a gap in the line instead of being bridged
    Given the current timeline has no reading for one hour between two hours that have readings
    When the device redraws its screen
    Then no line is drawn into or out of the hour without a reading
    And the line resumes from the next pair of consecutive hours that both have readings

  @id:device-display.intensity-graph.003 @rule:device-display.intensity-graph.flat-readings-centred @inferred @source:pico/fw_graph.py#GraphAxes
  Scenario: When every reading is the same the line sits halfway up the graph
    Given every reading on both lines has the same intensity
    When the device redraws its screen
    Then the line is drawn as a horizontal line at mid-height of the plot area

  @id:device-display.intensity-graph.004 @rule:device-display.intensity-graph.threshold-bands-at-percentile-cutoffs @inferred @source:pico/fw_graph.py#draw_threshold_bands @questionable
  Scenario: Red dashed lines mark the green and yellow cutoffs across the graph
    Given the graph has intensity readings to plot
    When the device redraws its screen
    Then a red dashed horizontal line is drawn across the plot at the 25th percentile of the plotted readings
    And a second red dashed horizontal line is drawn at the 50th percentile of the plotted readings

  @id:device-display.intensity-graph.005 @rule:device-display.intensity-graph.day-ticks-and-now-marker @inferred @source:pico/fw_graph.py#draw_day_ticks
  Scenario: The graph marks two days ago, one day ago and now, with a vertical line at now
    Given the graph has a full 60-hour timeline to plot
    When the device redraws its screen
    Then a vertical line runs up the plot at the current hour
    And tick marks along the bottom are labelled "-2d", "-1d" and "now" under the hours 48, 24 and 0 hours before now

  @id:device-display.intensity-graph.006 @rule:device-display.intensity-graph.no-data-empty-frame @inferred @source:pico/fw_graph.py#draw_graph
  Scenario Outline: Without enough readings the graph shows only an empty frame
    Given <readings>
    When the device redraws its screen
    Then <frame> is drawn
    And no intensity lines, cutoff lines or day ticks are drawn

    Examples:
      | readings                                              | frame                                               |
      | the device has no timeline at all                     | an empty outline box at the fixed fallback position |
      | the timeline has hours but none of them has a reading | the empty graph outline                             |
      | the timeline covers only a single hour                | the empty graph outline                             |
