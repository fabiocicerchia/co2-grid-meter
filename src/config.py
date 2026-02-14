
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    LAT = 41.9028
    LON = 12.4964

    POLL_EVERY_S = 300

    GREEN_MAX = 200
    YELLOW_MAX = 350
    RED_MAX = 500

    LED_GREEN_PINS = (5, 6, 13, 19)
    LED_YELLOW_PINS = (12, 16, 20, 21)
    LED_RED_PINS = (17, 27, 22, 23)

    DB_PATH = "readings.sqlite"
    PLOT_PATH = "static/plot.png"
    EINK_PREVIEW_PATH = "static/eink.png"
