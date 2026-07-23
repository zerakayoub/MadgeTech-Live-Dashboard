import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

load_dotenv()

MADGETECH_URL = "https://cloud.madgetech.com/browserapi"
USERAUTH = os.getenv("MADGETECH_USERAUTH", "").strip()
LOGGER_ID = int(os.getenv("MADGETECH_LOGGER_ID", "9986"))
LOGGER_SERIAL = os.getenv("MADGETECH_LOGGER_SERIAL", "R69882").strip()
CLOUD_POLL_SECONDS = max(float(os.getenv("CLOUD_POLL_SECONDS", "60")), 1.0)
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))

app = Flask(__name__)

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {
    "ok": False,
    "error": "Waiting for first reading",
    "fetched_at": None,
}


def find_unit_value(channel: dict[str, Any], unit_name: str) -> float | None:
    for unit in channel.get("uvs", []):
        if unit.get("ub") == unit_name:
            value = unit.get("val")
            return float(value) if value is not None else None
    return None


def parse_logger(payload: dict[str, Any]) -> dict[str, Any]:
    groups = (
        payload.get("data", {})
        .get("lgl", {})
        .get("LoggerGroups", [])
    )

    def walk(group_list: list[dict[str, Any]]):
        for group in group_list:
            for logger in group.get("Loggers", {}).get("lis", []):
                yield logger
            yield from walk(group.get("LoggerGroups", []))

    selected = None
    for logger in walk(groups):
        info = logger.get("info", {})
        if info.get("luid") == LOGGER_ID or logger.get("SerialNum") == LOGGER_SERIAL:
            selected = logger
            break

    if selected is None:
        raise RuntimeError(
            f"Logger not found. Expected cloud ID {LOGGER_ID} or serial {LOGGER_SERIAL}."
        )

    info = selected.get("info", {})
    readings = selected.get("rdgs", [])
    logger_alarms = info.get("alarms", [])
    if not readings:
        raise RuntimeError("Logger was found, but no readings were returned.")

    latest = readings[0]
    channels = {channel.get("ut"): channel for channel in latest.get("cvs", [])}

    temperature_f = find_unit_value(channels.get("Temperature", {}), "DegreesF")
    temperature_c = find_unit_value(channels.get("Temperature", {}), "DegreesC")
    humidity = find_unit_value(channels.get("RelativeHumidity", {}), "PercentRH")
    pressure_psia = find_unit_value(channels.get("AbsolutePressure", {}), "PSIA")

    timestamp_ms = latest.get("jsts")
    reading_time = None
    if timestamp_ms:
        reading_time = datetime.fromtimestamp(
            float(timestamp_ms) / 1000, tz=timezone.utc
        ).isoformat()

    # MadgeTech RSSI is not a direct percentage. Keep the raw value.
    return {
        "ok": True,
        "name": info.get("dvcid") or LOGGER_SERIAL,
        "serial": info.get("sernum") or LOGGER_SERIAL,
        "model": info.get("model"),
        "temperature_f": temperature_f,
        "temperature_c": temperature_c,
        "humidity_rh": humidity,
        "pressure_psia": pressure_psia,
        "battery_percent": info.get("batt"),
        "rssi_raw": info.get("rssi"),
        "connected": bool(info.get("connected") and info.get("rlyconnected")),
        "reading_interval_seconds": info.get("rdgratesecs"),
        "reading_time_utc": reading_time,
        "cloud_age_seconds": info.get("dsage"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "alarms": logger_alarms,
        "alarm_active": len(logger_alarms) > 0,
        "alarm_count": len(logger_alarms)
    }


def fetch_reading() -> dict[str, Any]:
    if not USERAUTH:
        raise RuntimeError(
            "MADGETECH_USERAUTH is missing. Copy .env.example to .env and add a fresh token."
        )

    # This reproduces the request observed in the browser's Network tab.
    form_data = {
        "_seq": "3",
        "fcn": "AccountListLoggerGroups",
        "userauth": USERAUTH,
        "loggergroupid": "0",
        "getdetaildata": "false",
        "hierarchical": "true",
        "rdginfo": json.dumps([{"Key": LOGGER_ID, "Value": 1}]),
    }

    response = requests.post(
        MADGETECH_URL,
        data=form_data,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={
            "Accept": "application/json",
            "User-Agent": "MadgeTech-Wall-Dashboard/1.0",
        },
    )
    response.raise_for_status()
    body = response.json()

    if body.get("apirslt") != 1:
        raise RuntimeError(
            f"MadgeTech returned an error: {body.get('apirsltName', 'Unknown error')}"
        )

    return parse_logger(body)


def poll_loop() -> None:
    global _cache
    while True:
        try:
            new_value = fetch_reading()
        except Exception as exc:
            new_value = {
                "ok": False,
                "error": str(exc),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

        with _cache_lock:
            _cache = new_value

        time.sleep(CLOUD_POLL_SECONDS)


@app.get("/")
def dashboard():
    return render_template("index.html")


@app.get("/api/current")
def current():
    with _cache_lock:
        return jsonify(_cache)


if __name__ == "__main__":
    worker = threading.Thread(target=poll_loop, daemon=True)
    worker.start()
    app.run(host="0.0.0.0", port=5000, debug=False)
