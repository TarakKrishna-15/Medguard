# backend/simulator.py
"""
Simulator engine for medicine testing.

Default data path set to user's Windows path (update if needed).
"""

from typing import Callable, Optional, Iterable, Any
import pandas as pd
import numpy as np
import joblib
import threading
import time
import random
from datetime import datetime
from pathlib import Path
import uuid

# <<< UPDATE: default data path set to your Windows path >>>
DEFAULT_DATA_PATH = r"D:\medicine-sim\data\medicine_dataset_with_phone.xlsx"
DEFAULT_MODEL_PATH = "model.pkl"  # optional; saved by train_model.py

class Simulator:
    def __init__(
        self,
        data_path: str = DEFAULT_DATA_PATH,
        model_path: str = DEFAULT_MODEL_PATH,
        heartbeat_interval: float = 1.0,
        hardware_latency: tuple[float, float] = (0.2, 1.5),
        sensor_channels: int = 3,
        seed: Optional[int] = 42,
    ):
        self.data_path = data_path
        self.model_path = model_path
        self.heartbeat_interval = heartbeat_interval
        self.hardware_latency = hardware_latency
        self.sensor_channels = sensor_channels

        # RNG
        self._rng = random.Random(seed)
        np.random.seed(seed if seed is not None else None)

        # runtime state
        self.lock = threading.RLock()
        self.running_streams: dict[str, dict] = {}

        # load catalog and model
        self._load_catalog()
        self._load_model()

        # fixed demo date (use same baseline when evaluating)
        self.today = pd.to_datetime("2025-11-25")

    def _load_catalog(self):
        p = Path(self.data_path)
        if not p.exists():
            raise FileNotFoundError(f"Catalog file not found at {self.data_path}")
        df = pd.read_excel(self.data_path)
        df.columns = [str(c).strip() for c in df.columns]
        if "manufacturer" not in df.columns:
            df["manufacturer"] = "Unknown"
        if "exp_date" not in df.columns and "expiry" in df.columns:
            df["exp_date"] = df["expiry"]
        if "exp_date" not in df.columns:
            df["exp_date"] = pd.NaT
        df["exp_date_parsed"] = pd.to_datetime(df["exp_date"], errors="coerce")
        self.df = df.reset_index(drop=True)
        self.manufacturers = sorted(self.df["manufacturer"].fillna("Unknown").unique().tolist())

    def _load_model(self):
        try:
            bundle = joblib.load(self.model_path)
            if not isinstance(bundle, dict) or "model" not in bundle:
                print(f"Model file {self.model_path} loaded but does not contain expected keys. Ignoring.")
                self.model_bundle = None
            else:
                self.model_bundle = bundle
                print(f"Loaded model bundle from {self.model_path}.")
        except Exception:
            self.model_bundle = None
            print("No model bundle loaded; using heuristic scoring.")

    def list_schema(self) -> dict:
        return {
            "manufacturers": self.manufacturers,
            "fields": list(self.df.columns),
            "sample_count": len(self.df),
        }

    def _ml_score(self, expiry, manufacturer) -> float:
        if self.model_bundle:
            model = self.model_bundle.get("model")
            encoder = self.model_bundle.get("encoder", None)
            try:
                days = (pd.to_datetime(expiry) - self.today).days
            except Exception:
                days = 36500
            if encoder is not None:
                try:
                    man_enc = int(encoder.transform([manufacturer])[0])
                except Exception:
                    man_enc = max(getattr(encoder, "classes_", [0]).shape[0], 0) + 1
            else:
                man_enc = 0
            X = np.array([[days, man_enc]])
            try:
                if hasattr(model, "decision_function"):
                    raw = -model.decision_function(X)[0]
                    score = 1.0 / (1.0 + np.exp(-4.0 * (raw - 0.0)))
                    return float(np.clip(score, 0.0, 1.0))
                elif hasattr(model, "predict_proba"):
                    return float(model.predict_proba(X)[0][1])
                elif hasattr(model, "predict"):
                    pred = model.predict(X)[0]
                    return float(1.0 if pred == 1 else 0.0)
            except Exception:
                pass

        try:
            ed = pd.to_datetime(expiry)
            days = (ed - self.today).days
        except Exception:
            days = 36500

        score = 0.0
        if days < 0:
            score += 0.5 * (1 - np.exp(max(-3.0, days / 365.0)))
        if manufacturer in (None, "", "Unknown", "nan"):
            score += 0.3
        score += float(np.random.normal(0, 0.05))
        return float(np.clip(score, 0.0, 1.0))

    def simulate_hardware_test(
        self,
        sample_row: Any,
        jitter: float = 0.05,
        noise_level: float = 0.05,
        simulate_failure_rate: float = 0.01,
    ) -> dict:
        min_l, max_l = self.hardware_latency
        duration = self._rng.uniform(min_l, max_l)
        duration *= self._rng.uniform(1.0 - jitter, 1.0 + jitter)
        time.sleep(duration)

        if self._rng.random() < simulate_failure_rate:
            return {
                "status": "ERROR",
                "error_msg": "Hardware timeout or sensor disconnect",
                "duration": duration,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

        if isinstance(sample_row, pd.Series):
            manufacturer = sample_row.get("manufacturer", "Unknown")
            expiry_val = sample_row.get("exp_date_parsed", sample_row.get("exp_date", None))
        elif isinstance(sample_row, dict):
            manufacturer = sample_row.get("manufacturer", "Unknown")
            expiry_val = sample_row.get("exp_date", sample_row.get("exp_date_parsed", None))
        else:
            manufacturer = getattr(sample_row, "manufacturer", "Unknown")
            expiry_val = getattr(sample_row, "exp_date_parsed", None)

        fake_score = self._ml_score(expiry_val, manufacturer)
        base_signal = max(0.05, 1.0 - fake_score)
        raw_sensor = []
        for ch in range(self.sensor_channels):
            drift = 1.0 + 0.02 * (ch - (self.sensor_channels - 1) / 2)
            noise = float(np.random.normal(0.0, noise_level))
            s = base_signal * drift * (1.0 + noise)
            raw_sensor.append(float(np.clip(s, 0.0, 5.0)))

        threshold = 0.7
        predicted_fake = 1 if fake_score >= threshold else 0
        test_result = "FAIL" if predicted_fake == 1 else "PASS"
        if self._rng.random() < 0.01:
            test_result = "PASS" if test_result == "FAIL" else "FAIL"

        return {
            "status": "OK",
            "duration": float(duration),
            "manufacturer": str(manufacturer),
            "expiry": str(expiry_val) if expiry_val is not None else None,
            "fake_score": float(round(fake_score, 4)),
            "predicted_fake": int(predicted_fake),
            "test_result": test_result,
            "raw_sensor": raw_sensor,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def stream_tests(
        self,
        callback: Callable[[dict], None],
        sample_selector: Optional[Callable[[pd.DataFrame], Iterable]] = None,
        interval: float = 0.5,
        run_id: Optional[str] = None,
        max_tests: Optional[int] = None,
    ) -> str:
        stream_id = run_id or str(uuid.uuid4())
        stop_flag = {"stop": False}

        def runner():
            count = 0
            if callable(sample_selector):
                gen = sample_selector(self.df)
            elif isinstance(sample_selector, (list, tuple, np.ndarray, pd.Index)):
                gen = (self.df.iloc[i] for i in sample_selector)
            else:
                def random_gen():
                    while True:
                        yield self.df.sample(1).iloc[0]
                gen = random_gen()

            for sample in gen:
                if stop_flag["stop"]:
                    break
                res = self.simulate_hardware_test(sample)
                res["stream_id"] = stream_id
                res["seq"] = count
                try:
                    callback(res)
                except Exception:
                    pass
                count += 1
                if max_tests is not None and count >= int(max_tests):
                    break
                slept = 0.0
                while slept < interval:
                    if stop_flag["stop"]:
                        break
                    time.sleep(0.1)
                    slept += 0.1
                if stop_flag["stop"]:
                    break

            try:
                callback({"stream_id": stream_id, "event": "stream_ended"})
            except Exception:
                pass
            with self.lock:
                if stream_id in self.running_streams:
                    del self.running_streams[stream_id]

        th = threading.Thread(target=runner, daemon=True)
        with self.lock:
            self.running_streams[stream_id] = {"thread": th, "stop_flag": stop_flag}
        th.start()
        return stream_id

    def stop_stream(self, stream_id: str) -> bool:
        with self.lock:
            info = self.running_streams.get(stream_id)
            if not info:
                return False
            info["stop_flag"]["stop"] = True
            return True

if __name__ == "__main__":
    def demo_callback(msg):
        print("EVENT:", msg)
    print("Starting Simulator demo...")
    sim = Simulator()
    print("Catalog samples:", sim.list_schema()["sample_count"])
    first = sim.df.iloc[0]
    print("Single test result:", sim.simulate_hardware_test(first))
    sid = sim.stream_tests(callback=demo_callback, interval=0.5, max_tests=5)
    while sid in sim.running_streams:
        time.sleep(0.5)
    print("Demo stream finished.")
