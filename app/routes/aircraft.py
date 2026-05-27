from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
import asyncio
router = APIRouter()
import os
from dotenv import load_dotenv
load_dotenv()
import requests
import json
import glob
from supabase import create_client
from pathlib import Path
import psycopg2

def get_conn():
  return psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT"),
  )

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

@router.websocket("/ws/aircraft")
async def aircraft_ws(websocket: WebSocket):
    await websocket.accept()

    conn = None
    cur = None

    bounds = None
    bounds_version = 0
    last_bounds_version_sent = -1

    current_time = None
    last_snapshot = None

    SIM_SPEED = 1.0
    TICK = 0.5

    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT MIN(snapshot_time)
            FROM aircraft_positions
        """)
        current_time = cur.fetchone()[0]

        if not current_time:
            return

        async def receiver():
            nonlocal bounds, bounds_version

            while True:
                data = await websocket.receive_json()
                bounds = data
                bounds_version += 1

        async def streamer():
            nonlocal current_time, last_snapshot, last_bounds_version_sent

            while True:
                await asyncio.sleep(TICK)

                if not bounds:
                    continue

                west = bounds["west"]
                east = bounds["east"]
                south = bounds["south"]
                north = bounds["north"]

                current_time += SIM_SPEED * TICK

                cur.execute("""
                    SELECT MIN(snapshot_time)
                    FROM aircraft_positions
                    WHERE snapshot_time > %s
                """, (current_time,))

                next_snapshot = cur.fetchone()[0]

                bounds_changed = (bounds_version != last_bounds_version_sent)

                snapshot_changed = (
                    next_snapshot is not None
                    and (last_snapshot is None or next_snapshot != last_snapshot)
                )

                should_send = (
                    bounds_changed
                    or (next_snapshot is not None and next_snapshot != last_snapshot)
                )

                if not should_send:
                    continue

                last_bounds_version_sent = bounds_version
                last_snapshot = next_snapshot

                query = """
                WITH latest AS (
                    SELECT DISTINCT ON (icao)
                        icao,
                        callsign,
                        origin_country,
                        lon,
                        lat,
                        altitude_m,
                        velocity_mps,
                        heading_deg,
                        vertical_rate,
                        on_ground,
                        snapshot_time
                    FROM aircraft_positions
                    WHERE snapshot_time <= %s
                    ORDER BY icao, snapshot_time DESC
                )
                SELECT *
                FROM latest
                WHERE lon BETWEEN %s AND %s
                  AND lat BETWEEN %s AND %s
                  AND COALESCE(on_ground, FALSE) = FALSE
                  AND COALESCE(velocity_mps, 0) > 1
                LIMIT 1000;
                """

                cur.execute(query, (
                    current_time,
                    west, east, south, north
                ))

                rows = cur.fetchall()

                aircraft = [
                    {
                        "icao": r[0],
                        "callsign": r[1],
                        "origin_country": r[2],
                        "lon": r[3],
                        "lat": r[4],
                        "altitude_m": r[5],
                        "velocity_mps": r[6],
                        "heading_deg": r[7],
                        "vertical_rate": r[8],
                        "on_ground": r[9],
                        "snapshot_time": r[10],
                    }
                    for r in rows
                ]

                await websocket.send_json(aircraft)

        await asyncio.gather(receiver(), streamer())

    except WebSocketDisconnect:
        print("[WS] disconnected")

    except Exception as e:
        print("[WS ERROR]", e)

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()