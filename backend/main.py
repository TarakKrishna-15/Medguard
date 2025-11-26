# main.py - backend for MediGuard AI
# Save to: D:\medicine-sim\backend\main.py

import asyncio
import json
import time
import uuid
import random
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Try to import your existing Simulator (optional)
try:
    from simulator import Simulator
    SIM_AVAILABLE = True
except Exception:
    Simulator = None
    SIM_AVAILABLE = False

APP = FastAPI(title="MediGuard AI - Backend")

# Allow frontend local dev access
APP.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
FRONTEND_AVAILABLE = FRONTEND_DIR.exists()

if FRONTEND_AVAILABLE:
    # Mount frontend static files
    APP.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    # Also serve static assets (CSS, JS) from root
    APP.mount("/static", StaticFiles(directory=str(FRONTEND_DIR), html=False), name="static")

DB_PATH = str(BASE_DIR / "simulator_alerts.db")

# ----------------- Simple SQLite for alerts -----------------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS alerts (
               id TEXT PRIMARY KEY,
               timestamp REAL,
               level TEXT,
               manufacturer TEXT,
               manufacturer_phone TEXT,
               message TEXT,
               data TEXT
           )"""
    )
    con.commit()
    con.close()

def save_alert_to_db(alert: Dict[str, Any]):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO alerts (id, timestamp, level, manufacturer, manufacturer_phone, message, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            alert.get("id"),
            alert.get("timestamp"),
            alert.get("level"),
            alert.get("manufacturer"),
            alert.get("manufacturer_phone"),
            alert.get("message"),
            alert.get("data"),
        ),
    )
    con.commit()
    con.close()

def load_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, timestamp, level, manufacturer, manufacturer_phone, message, data FROM alerts ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    con.close()
    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "timestamp": r[1],
            "level": r[2],
            "manufacturer": r[3],
            "manufacturer_phone": r[4],
            "message": r[5],
            "data": json.loads(r[6]) if r[6] else None,
        })
    return result

# ----------------- WebSocket manager -----------------
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        payload = json.dumps(message)
        remove = []
        for ws in list(self.active):
            try:
                await ws.send_text(payload)
            except Exception:
                remove.append(ws)
        for r in remove:
            self.disconnect(r)

manager = ConnectionManager()

# ----------------- Pydantic models -----------------
class PredictRequest(BaseModel):
    manufacturer: Optional[str] = None
    expiry_date: Optional[str] = None  # ISO date string expected (YYYY-MM-DD)
    batch: Optional[str] = None


class StreamRequest(BaseModel):
    seconds: int = Field(default=30, ge=5, le=600, description="How long to run the simulator stream")
    interval: float = Field(default=1.0, ge=0.2, le=10.0, description="Delay between simulated events in seconds")

# ----------------- Utility helpers -----------------
def parse_days_to_expiry(expiry_date: Optional[str]) -> Optional[int]:
    """Return days from today to expiry_date. None if unknown/invalid."""
    if not expiry_date:
        return None
    try:
        # keep this simple (no extra timezone handling)
        from datetime import datetime, date
        ed = datetime.fromisoformat(expiry_date).date()
        today = date.today()
        delta = (ed - today).days
        return int(delta)
    except Exception:
        return None

AUTO_ALERT_THRESHOLD = 0.8
WARN_THRESHOLD = 0.5

def heuristic_fake_score(days_to_expiry: Optional[int]) -> float:
    """Simple heuristic for fake-score based on expiry proximity."""
    if days_to_expiry is None:
        # random low suspicion
        return round(random.uniform(0.0, 0.25), 3)
    if days_to_expiry <= 0:
        return 0.95
    if days_to_expiry <= 90:
        return 0.85
    if days_to_expiry <= 120:
        return 0.6
    # further out -> lower suspicion
    return round(random.uniform(0.0, 0.35), 3)

# If you have a simulator with a catalog DataFrame 'df' that includes manufacturer_phone, try to use it
def lookup_manufacturer_phone(manufacturer: Optional[str]):
    if not SIM_AVAILABLE:
        return None
    try:
        sim = APP.state.simulator
        if sim is None:
            return None
        if hasattr(sim, "df") and "manufacturer" in sim.df.columns:
            matches = sim.df[sim.df["manufacturer"].fillna("").astype(str) == str(manufacturer)]
            if not matches.empty and "manufacturer_phone" in sim.df.columns:
                ph = matches["manufacturer_phone"].dropna().astype(str)
                if not ph.empty:
                    return ph.iloc[0]
    except Exception:
        return None
    return None

# ----------------- Alert evaluation logic -----------------
async def evaluate_and_handle_alert(result: Dict[str, Any]):
    """
    Evaluate a single test result and create/persist/broadcast an alert when rules trigger.
    New expiry-based rules:
      - days_to_expiry <= 90  => CRITICAL (3 months)
      - days_to_expiry <= 120 => WARNING  (4 months)
    Also preserves ML-based logic:
      - predicted_fake == 1 or fake_score >= AUTO_ALERT_THRESHOLD => CRITICAL
      - fake_score >= WARN_THRESHOLD => WARNING
    The function returns the alert dict if created, else None.
    """
    days = None
    expiry_raw = result.get("expiry") or result.get("expiry_date") or result.get("exp_date")
    try:
        if expiry_raw:
            from datetime import datetime
            ed = None
            try:
                ed = datetime.fromisoformat(expiry_raw)
            except Exception:
                try:
                    # fallback: pandas
                    import pandas as _pd
                    ed = _pd.to_datetime(expiry_raw, errors="coerce")
                except Exception:
                    ed = None
            if ed:
                from datetime import datetime as _dt
                now = _dt.now()
                if hasattr(ed, "to_pydatetime"):
                    ed_dt = ed.to_pydatetime()
                else:
                    ed_dt = ed if isinstance(ed, _dt) else None
                if ed_dt:
                    days = int((ed_dt - now).days)
    except Exception:
        days = None

    level = None
    reason = None
    if days is not None:
        if days <= 90:
            level = "CRITICAL"
            reason = f"Expiry within 3 months (days_to_expiry={days})"
        elif days <= 120:
            level = "WARNING"
            reason = f"Expiry within 4 months (days_to_expiry={days})"

    score = float(result.get("fake_score", 0.0))
    ml_pred = int(result.get("predicted_fake", 0))

    if level is None:
        if ml_pred == 1 or score >= AUTO_ALERT_THRESHOLD:
            level = "CRITICAL"
            reason = f"ML anomaly (score={score:.3f})"
        elif score >= WARN_THRESHOLD:
            level = "WARNING"
            reason = f"ML suspicious (score={score:.3f})"

    if level is None:
        return None

    manufacturer = result.get("manufacturer", result.get("manufacturer_name") or "Unknown")
    man_phone = result.get("manufacturer_phone")
    if not man_phone:
        man_phone = lookup_manufacturer_phone(manufacturer)

    alert = {
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "level": level,
        "manufacturer": manufacturer,
        "manufacturer_phone": man_phone,
        "message": f"{level}: {reason} | supplier={manufacturer}",
        "data": json.dumps(result)
    }

    # persist and broadcast
    try:
        save_alert_to_db(alert)
    except Exception:
        pass
    # broadcast via WS
    try:
        await manager.broadcast({"event": "alert", "alert": alert})
    except Exception:
        pass

    return alert

# ----------------- Simulator stream task -----------------
async def _stream_simulator_task(run_seconds: int = 30, interval: float = 1.0):
    """
    Emit simulated test_results for `run_seconds` seconds every `interval` seconds.
    Each test_result is evaluated and may generate alerts.
    """
    start = time.time()
    # if a Simulator class exists, use it
    sim = getattr(APP.state, "simulator", None)
    while time.time() - start < run_seconds:
        payload = None
        if sim is not None:
            try:
                sample = sim.sample() if hasattr(sim, "sample") else None
                # expect sample to be a dict-like with fields: manufacturer, expiry or exp_date, batch ...
                payload = dict(sample) if sample is not None else None
            except Exception:
                payload = None

        if payload is None:
            # fallback simple random payload
            days = random.randint(-30, 730)
            from datetime import datetime, timedelta
            expiry_date = (datetime.now() + timedelta(days=days)).isoformat()
            payload = {
                "batch": "SIM" + str(random.randint(1000, 9999)),
                "manufacturer": random.choice(["PharmaCorp", "HealthMeds", "MediCare", "GlobalPharma"]),
                "expiry": expiry_date,
                "test_metrics": {"x": random.random()}
            }

        # compute ML-like scores
        d = parse_days_to_expiry(payload.get("expiry") or payload.get("expiry_date"))
        fake_score = heuristic_fake_score(d)
        predicted_fake = 1 if fake_score >= AUTO_ALERT_THRESHOLD else 0
        payload["fake_score"] = fake_score
        payload["predicted_fake"] = predicted_fake
        payload["days_to_expiry"] = d

        # broadcast test_result
        try:
            await manager.broadcast({"event": "test_result", "payload": payload})
        except Exception:
            pass

        # evaluate and persist/broadcast alert if triggered
        try:
            await evaluate_and_handle_alert({
                "expiry": payload.get("expiry") or payload.get("expiry_date"),
                "manufacturer": payload.get("manufacturer"),
                "fake_score": payload["fake_score"],
                "predicted_fake": payload["predicted_fake"],
            })
        except Exception:
            pass

        await asyncio.sleep(interval)

# ----------------- FastAPI startup -----------------
@APP.on_event("startup")
async def startup_event():
    init_db()
    # instantiate simulator if available
    if SIM_AVAILABLE:
        try:
            APP.state.simulator = Simulator()
        except Exception:
            APP.state.simulator = None
    else:
        APP.state.simulator = None

# ----------------- Endpoints -----------------
@APP.get("/health")
async def health():
    """Health check used by the frontend to know backend is live."""
    return {"status": "ok"}


@APP.get("/", include_in_schema=False)
async def root():
    """Serve the frontend index.html directly."""
    if FRONTEND_AVAILABLE:
        from fastapi.responses import FileResponse
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path), media_type="text/html")
    return RedirectResponse(url="/frontend/")

@APP.post("/predict")
async def predict(req: PredictRequest):
    """
    Predict endpoint. Returns a small JSON with keys:
      - fake_score (0..1)
      - predicted_fake (0/1)
      - manufacturer_phone (optional)
    Heuristic logic based on expiry proximity; replace with real ML inference if available.
    """
    manufacturer = req.manufacturer or "Unknown"
    expiry = req.expiry_date or None
    batch = req.batch or None

    days = parse_days_to_expiry(expiry)
    fake_score = heuristic_fake_score(days)
    predicted_fake = 1 if fake_score >= AUTO_ALERT_THRESHOLD else 0
    manufacturer_phone = lookup_manufacturer_phone(manufacturer)

    result = {
        "manufacturer": manufacturer,
        "batch": batch,
        "expiry_date": expiry,
        "days_to_expiry": days,
        "fake_score": fake_score,
        "predicted_fake": predicted_fake,
        "manufacturer_phone": manufacturer_phone,
    }
    # also evaluate immediately so frontend can get immediate alert if necessary
    try:
        await evaluate_and_handle_alert(result)
    except Exception:
        pass

    return result

# start the simulator stream for some seconds
@APP.post("/start_stream")
async def start_stream(background_tasks: BackgroundTasks, req: StreamRequest = Body(default=None)):
    """
    Starts a short simulator stream in background that emits test_result events and may trigger alerts.
    POST /start_stream with JSON body: {"seconds":60, "interval":1.5}
    """
    payload = req or StreamRequest()
    background_tasks.add_task(_stream_simulator_task, payload.seconds, payload.interval)
    return {"status": "started", "seconds": payload.seconds, "interval": payload.interval}

@APP.get("/alerts")
async def get_alerts(limit: int = 100):
    return load_alerts(limit=limit)


def _alert_to_highrisk(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform stored alerts into a simplified shape the frontend can render.
    """
    data = alert.get("data") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}

    fake_score = float(data.get("fake_score", 0.0))
    quality = max(0, min(100, int(round((1.0 - fake_score) * 100))))
    level = alert.get("level", "WARNING")
    risk = "high" if level == "CRITICAL" else "medium"

    return {
        "id": alert.get("id"),
        "timestamp": alert.get("timestamp"),
        "name": data.get("medicine") or data.get("name") or data.get("product_name") or data.get("manufacturer") or "Unknown",
        "batch": data.get("batch") or data.get("batch_no") or data.get("id") or data.get("batch_id") or "N/A",
        "quality": quality,
        "risk": risk,
        "supplier": alert.get("manufacturer") or data.get("manufacturer") or "Unknown",
        "manufacturer_phone": alert.get("manufacturer_phone") or data.get("manufacturer_phone"),
        "message": alert.get("message")
    }


@APP.get("/highrisk")
async def highrisk(limit: int = 20):
    """
    Return the latest alerts in a frontend-friendly format.
    """
    alerts = load_alerts(limit=limit)
    return [_alert_to_highrisk(a) for a in alerts]

@APP.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint delivering events: {event: 'alert'|'test_result', ...}"""
    await manager.connect(websocket)
    try:
        while True:
            # keep websocket open; optionally receive pings from client
            _ = await websocket.receive_text()
            # do nothing with incoming messages
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        try:
            manager.disconnect(websocket)
        except Exception:
            pass

# ----------------- Run note -----------------
# To run use: uvicorn main:APP --reload --port 8000
# or in PowerShell:
# cd D:\medicine-sim\backend
# uvicorn main:app --host 127.0.0.1 --port 8000 --reload
