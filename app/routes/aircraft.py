from fastapi import APIRouter, Query
router = APIRouter()
import os
from dotenv import load_dotenv
load_dotenv()
import requests
import json
import glob
from supabase import create_client
from pathlib import Path

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

@router.get("/get-aircraft")
def get_aircraft(
    lon_min: float = Query(...),
    lon_max: float = Query(...),
    lat_min: float = Query(...),
    lat_max: float = Query(...)
):
    try:
        # 1. Pull recent data (important for performance)
        res = supabase.table("aircraft_positions") \
            .select("*") \
            .gte("lon", lon_min) \
            .lte("lon", lon_max) \
            .gte("lat", lat_min) \
            .lte("lat", lat_max) \
            .order("snapshot_time", desc=True) \
            .limit(10000) \
            .execute()

        rows = res.data

        # 2. Keep only latest record per aircraft
        latest = {}

        for r in rows:
            icao = r["icao"]

            # first hit is newest because of desc order
            if icao not in latest:
                latest[icao] = r

        return list(latest.values())

    except Exception as e:
        return {"error": str(e)}

def transform_state(snapshot_time, s):
    return {
        "snapshot_time": snapshot_time,

        "icao": s[0],
        "callsign": (s[1] or "").strip() or None,
        "origin_country": s[2],

        "last_contact": s[4],

        "lon": s[5],
        "lat": s[6],

        "altitude_m": s[7],
        "geo_altitude_m": s[13],

        "velocity_mps": s[9],
        "heading_deg": s[10],
        "vertical_rate": s[11],

        "on_ground": s[8],
        "spi": s[15],
        "position_source": s[16],

        "squawk": s[14],
    }

def chunked(lst, size=500):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "opensky_raw"

@router.post("/ingest-opensky")
def ingest_opensky():
    total = 0

    files = sorted((DATA_DIR).glob("*.json"))

    print("DATA_DIR =", DATA_DIR)
    print("FILES FOUND =", len(files))

    for path in files:
        with open(path, "r") as f:
            data = json.load(f)

        snapshot_time = data["time"]
        states = data.get("states", [])

        rows = []

        for s in states:
            if not s or len(s) < 17:
                continue

            if s[5] is None or s[6] is None:
                continue

            rows.append(transform_state(snapshot_time, s))

        for batch in chunked(rows, 500):
            supabase.table("aircraft_positions").insert(batch).execute()
            total += len(batch)

    return {
        "files_processed": len(files),
        "rows_inserted": total
    }