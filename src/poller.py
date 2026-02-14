
import time
import random
from datetime import datetime
from db import insert
from ledbar import LedBar12
from plot import build_plot
from recommender import recommend
from eink import update_eink

def run():
    leds = LedBar12()
    while True:
        ci = random.randint(120, 500)
        ts = datetime.utcnow().isoformat()
        insert(ts, ci)
        leds.set_by_intensity(ci)
        build_plot(datetime.utcnow())
        verdict = recommend(ci)
        update_eink(ci, verdict)
        print(ci, verdict)
        time.sleep(10)

if __name__ == "__main__":
    run()
