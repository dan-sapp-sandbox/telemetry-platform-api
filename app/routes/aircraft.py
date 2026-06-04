from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
import asyncio
router = APIRouter()
import os
from dotenv import load_dotenv
load_dotenv()
import json
import glob
from supabase import create_client
from pathlib import Path
import psycopg2
from datetime import timedelta

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

    CHUNK_SECONDS = 120
    APPEND_THRESHOLD = 30

    try:
        conn = get_conn()
        cur = conn.cursor()

        # BIGINT epoch start
        cur.execute("""
            SELECT MIN(snapshot_time)
            FROM adsb_playback
        """)
        playback_time = cur.fetchone()[0]

        if playback_time is None:
            await websocket.close()
            return

        async def receiver():
            nonlocal bounds
            while True:
                bounds = await websocket.receive_json()

        async def streamer():
            nonlocal playback_time

            last_sent_end = playback_time

            while True:
                await asyncio.sleep(1)

                if not bounds:
                    continue

                # ensure we stay ahead of playback window
                if last_sent_end - playback_time > APPEND_THRESHOLD:
                    continue

                chunk_end = last_sent_end + CHUNK_SECONDS

                west = bounds["west"]
                east = bounds["east"]
                south = bounds["south"]
                north = bounds["north"]

                # FIXED SQL (removed trailing comma + fixed schema alignment)
                query = """
                SELECT
                    icao,
                    snapshot_time,
                    lat,
                    lon,
                    altitude_m,
                    velocity_mps,
                    heading_deg,
                    callsign,
                    origin_country
                FROM adsb_playback
                WHERE snapshot_time BETWEEN %s AND %s
                  AND lon BETWEEN %s AND %s
                  AND lat BETWEEN %s AND %s
                ORDER BY snapshot_time ASC
                """

                cur.execute(query, (
                    last_sent_end,
                    chunk_end,
                    west, east,
                    south, north
                ))

                rows = cur.fetchall()

                aircraft = [
                    {
                        "icao": r[0],
                        "snapshot_time": r[1],
                        "lat": r[2],
                        "lon": r[3],
                        "altitude_m": r[4],
                        "velocity_mps": r[5],
                        "heading_deg": r[6],
                        "callsign": r[7],
                        "origin_country": r[8],
                    }
                    for r in rows
                ]

                await websocket.send_json({
                    "type": "append",
                    "start_time": last_sent_end,
                    "end_time": chunk_end,
                    "aircraft": aircraft
                })

                last_sent_end = chunk_end

        await asyncio.gather(receiver(), streamer())

    except WebSocketDisconnect:
        print("[WS] disconnected")

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()