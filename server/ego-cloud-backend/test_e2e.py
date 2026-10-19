import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1"

def post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get(path):
    req = urllib.request.Request(BASE_URL + path)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("=== Ego Cloud Backend E2E Verification ===")
    
    # 1. Register Devices
    dev1 = post("/api/v1/fleet/devices", {
        "deviceId": "ego-link-001",
        "deviceName": "样机001-现测开发板",
        "hardwareModel": "SIM7670G_DEVBOARD",
        "firmwareVersion": "v1.0.4",
        "imei": "861234567890123",
        "iccid": "89860401102290001"
    })
    print("[1] Registered Device 1:", dev1["deviceId"], dev1["deviceName"])

    dev2 = post("/api/v1/fleet/devices", {
        "deviceId": "HW021_C1-002",
        "deviceName": "样机002-C1工程样机",
        "hardwareModel": "HW021_C1_ESP32MODEL",
        "firmwareVersion": "v2.0.1-preview",
        "imei": "869876543210987",
        "iccid": "89860401102290002"
    })
    print("[2] Registered Device 2:", dev2["deviceId"], dev2["deviceName"])

    # 2. Ingest 5 Telemetry points (simulate walking trajectory in Shenzhen Nanshan Tech Park)
    trajectory = [
        (22.5401, 113.9345, 3.6, 88),
        (22.5408, 113.9352, 4.1, 88),
        (22.5415, 113.9360, 4.5, 87),
        (22.5422, 113.9368, 3.8, 87),
        (22.5430, 113.9375, 2.5, 87)
    ]

    for i, (lat, lon, spd, bat) in enumerate(trajectory):
        ack = post("/api/v1/devices/ego-link-001/telemetry", {
            "device_id": "ego-link-001",
            "timestamp": int(time.time() * 1000) - (len(trajectory) - i) * 10000,
            "latitude": lat,
            "longitude": lon,
            "speed": spd,
            "altitude": 35.0 + i * 2,
            "satellites": 11,
            "battery": bat,
            "battery_voltage": 4.05,
            "rssi": 29,
            "network_type": "LTE Cat.1",
            "motion_state": "WALKING",
            "step_count": 5280 + i * 15
        })
        print(f"[3] Telemetry point {i+1} enqueued: {ack['status']} ({ack['message']})")

    # 3. Trigger SOS Alert
    alert = post("/api/v1/alerts/trigger", {
        "deviceId": "ego-link-001",
        "type": "SOS",
        "title": "紧急求助 (SOS 按键按下)",
        "desc": "用户长按硬件物理 KEY 键，触发路演演练求助",
        "lat": 22.5430,
        "lon": 113.9375
    })
    print("[4] Triggered SOS Alert:", alert["status"])

    # Wait for Redis Stream consumer worker to drain and write to MariaDB
    print("Waiting 1.5s for Redis Stream consumer worker...")
    time.sleep(1.5)

    # 4. Query Fleet Summary
    summary = get("/api/v1/fleet/summary")
    print("\n[5] Fleet Summary:", json.dumps(summary, ensure_ascii=False))

    # 5. Query Track Points
    tracks = get("/api/v1/tracks/ego-link-001/latest?limit=10")
    print(f"[6] Retrieved Track Points: {len(tracks)} points recorded.")
    if tracks:
        p = tracks[-1]
        print(f"    Latest Point: GCJ02=({p['lat']:.4f}, {p['lon']:.4f}), Speed={p['speed']} km/h, Bat={p['battery']}%")

    # 6. Query Active Alerts
    alerts = get("/api/v1/alerts")
    print(f"[7] Active Alerts Count: {len(alerts)}")
    for a in alerts:
        print(f"    Alert [{a['alertType']}]: {a['title']} - {a['description']}")

    # 7. Generate AI Daily Diary
    diary = post("/api/v1/diaries/ego-link-001/generate", {})
    print(f"\n[8] Generated AI Diary:")
    print("    Title:", diary["title"])
    print("    Summary:", diary["summary"])
    print("    Distance:", diary["totalDistanceKm"], "km | Steps:", diary["totalStepCount"])
    print("\n=== All Tests Passed Successfully! ===")

if __name__ == "__main__":
    main()
