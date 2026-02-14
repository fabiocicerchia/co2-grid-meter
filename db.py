
import sqlite3

def connect(path="readings.sqlite"):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS readings(ts TEXT PRIMARY KEY, ci REAL)"
    )
    return conn

def insert(ts, ci):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO readings VALUES (?,?)", (ts, ci))

def latest():
    with connect() as c:
        r = c.execute(
            "SELECT ts, ci FROM readings ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return r
