@domain:device-display @area:panel-driver @from:pico/epd-driver
Feature: Showing a frame on the e-ink panel
  Serves the device owner, who needs each rendered reading to appear whole and in the orientation they configured on the tri-colour panel.

  Background:
    Given the device has a Waveshare 2.13" tri-colour (black, white, red) e-ink panel attached

  @id:device-display.panel-driver.001 @rule:device-display.panel.orientation-fills-whole-panel @verified @source:pico/epd_driver.py#EPD_2in13_B_V4_Landscape @test:tests/test_epd_driver.py#test_portrait_constructs_and_sends_its_own_data_entry_mode @test:tests/test_epd_driver.py#test_framebuffers_are_transposed_between_orientations @test:tests/test_epd_driver.py#test_framebuffer_geometry_fills_its_buffer_exactly @test:tests/test_epd_driver.py#test_init_sequences_differ_only_in_the_data_entry_mode @questionable
  Scenario Outline: The panel draws the full frame in the configured orientation
    Given the device is configured for <orientation> display
    When the device draws a new frame
    Then the panel fills a <drawing_area> pixel area
    And the frame is neither clipped nor garbled

    Examples:
      | orientation | drawing_area        |
      | portrait    | 128 wide x 250 tall |
      | landscape   | 250 wide x 128 tall |

  @id:device-display.panel-driver.002 @rule:device-display.panel.both-colours-then-refresh @verified @source:pico/epd_driver.py#EPD_2in13_B_V4_Portrait @test:tests/test_epd_driver.py#test_display_sends_each_plane_in_its_layouts_order
  Scenario: A new frame shows its black and red layers together after one refresh
    Given a frame has been drawn with black and red content
    When the device draws the new frame
    Then the panel receives the black layer and then the red layer
    And the panel refreshes once, after both layers
    And the panel shows the new black and red content in place of the old frame
