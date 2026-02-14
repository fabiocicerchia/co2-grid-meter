
from gpiozero import LED
from config import Config

class LedBar12:
    def __init__(self):
        self.greens = [LED(p) for p in Config.LED_GREEN_PINS]
        self.yellows = [LED(p) for p in Config.LED_YELLOW_PINS]
        self.reds = [LED(p) for p in Config.LED_RED_PINS]

    def off(self):
        for g in self.greens + self.yellows + self.reds:
            g.off()

    def set_by_intensity(self, ci):
        self.off()
        if ci <= Config.GREEN_MAX:
            n = int(4 * ci / Config.GREEN_MAX)
            for i in range(n):
                self.greens[i].on()
        elif ci <= Config.YELLOW_MAX:
            for g in self.greens:
                g.on()
            n = int(4 * (ci - Config.GREEN_MAX) / (Config.YELLOW_MAX - Config.GREEN_MAX))
            for i in range(n):
                self.yellows[i].on()
        else:
            for g in self.greens:
                g.on()
            for y in self.yellows:
                y.on()
            n = int(4 * (ci - Config.YELLOW_MAX) / (Config.RED_MAX - Config.YELLOW_MAX))
            for i in range(min(4, n)):
                self.reds[i].on()
