import time, uuid, json
from db import save_alert

# recommended thresholds
AUTO_ALERT_THRESHOLD = 0.8         # score >= 0.8 => high severity alert
WARN_THRESHOLD = 0.6               # 0.6 - 0.8 -> warning

def evaluate_and_alert(result, notify_callback=None):
    # result is simulator test dict
    score = result.get("fake_score", 0)
    manufacturer = result.get("manufacturer")
    # Default: if predicted_fake is set or score above threshold => create alert
    if result.get("predicted_fake", 0) == 1 or score >= AUTO_ALERT_THRESHOLD:
        level = "CRITICAL"
        msg = f"High likelihood of fake medicine detected from {manufacturer} (score={score:.3f})"
    elif score >= WARN_THRESHOLD:
        level = "WARNING"
        msg = f"Suspicious medicine detected from {manufacturer} (score={score:.3f})"
    else:
        return None  # no alert

    alert = {
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "level": level,
        "manufacturer": manufacturer,
        "message": msg,
        "data": json.dumps(result)
    }
    # persist
    save_alert(alert)
    # optional: send to websocket clients via callback
    if notify_callback:
        notify_callback({"event": "alert", "alert": alert})
    return alert
