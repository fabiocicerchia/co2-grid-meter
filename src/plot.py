
import matplotlib.pyplot as plt
from datetime import datetime
from config import Config

def build_plot(now):
    plt.figure()
    plt.plot([0,1,2],[100,200,150])
    plt.title("CO2 intensity (demo)")
    plt.savefig(Config.PLOT_PATH)
    plt.close()
    return Config.PLOT_PATH
