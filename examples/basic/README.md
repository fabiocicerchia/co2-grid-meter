# Basic Example

What it shows: full dashboard + mock Pico running locally, no hardware.

## Run

```sh
pip install -r requirements.txt
./start.sh
```

Then open `http://127.0.0.1:5000/` — it shows current carbon intensity, a
48h trend, and the GO/WAIT recommendation, all served from the mock Pico's
simulated data.
