
from flask import Flask, send_file
from config import Config

app = Flask(__name__)

@app.route("/plot")
def plot():
    return send_file(Config.PLOT_PATH)

@app.route("/eink")
def eink():
    return send_file(Config.EINK_PREVIEW_PATH)

app.run("0.0.0.0", 8080)
