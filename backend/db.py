import sqlite3
from pathlib import Path

DB_PATH = "simulator.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        timestamp REAL,
        level TEXT,
        manufacturer TEXT,
        message TEXT,
        data TEXT
    )
    """)
    conn.commit()
    conn.close()

def save_alert(alert):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO alerts (id,timestamp,level,manufacturer,message,data) VALUES (?,?,?,?,?)",
              (alert["id"], alert["timestamp"], alert["level"], alert["manufacturer"], alert["message"], alert.get("data","")))
    conn.commit()
    conn.close()
