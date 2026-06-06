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
    first_time = None
    last_time = None

    INIT_WINDOW_SECONDS = 120

    db_lock = asyncio.Lock()

    try:
        conn = get_conn()
        cur = conn.cursor()

        print("[AIRCRAFT WS] started")

        async def send_chunk(start_t, end_t, label):
            nonlocal bounds

            if not bounds:
                return

            async with db_lock:
                cur.execute("""
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
                    ORDER BY icao, snapshot_time ASC
                """, (
                    start_t,
                    end_t,
                    bounds["west"],
                    bounds["east"],
                    bounds["south"],
                    bounds["north"]
                ))

                rows = cur.fetchall()

            by_icao = {}

            for r in rows:
                by_icao.setdefault(r[0], []).append({
                    "icao": r[0],
                    "snapshot_time": r[1],
                    "lat": r[2],
                    "lon": r[3],
                    "altitude_m": r[4],
                    "velocity_mps": r[5],
                    "heading_deg": r[6],
                    "callsign": r[7],
                    "origin_country": r[8],
                })

            await websocket.send_json({
                "type": label.lower(),
                "start_time": start_t,
                "end_time": end_t,
                "snapshots": by_icao,
            })

            print(
                f"[AIRCRAFT WS] {label} "
                f"aircraft={len(by_icao)} "
                f"points={len(rows)} "
                f"window={start_t}->{end_t}"
            )

        async def receiver():
            nonlocal bounds, first_time, last_time

            first_bounds = True

            while True:
                new_bounds = await websocket.receive_json()
                bounds = new_bounds

                print("[AIRCRAFT WS] bounds update")

                if first_bounds:
                    first_bounds = False
                    continue

                if first_time is None or last_time is None:
                    continue

                await send_chunk(
                    first_time,
                    last_time,
                    "BOUNDS_UPDATE"
                )

        async def streamer():
            nonlocal bounds, first_time, last_time

            print("[AIRCRAFT WS] streamer started")

            while bounds is None:
                await asyncio.sleep(0.05)

            async with db_lock:
                cur.execute("""
                    SELECT MIN(snapshot_time), MAX(snapshot_time)
                    FROM adsb_playback
                """)

                first_time, max_time = cur.fetchone()

            if first_time is None:
                print("[AIRCRAFT WS] no data")
                return

            first_time = (first_time // 60) * 60

            init_end = first_time + INIT_WINDOW_SECONDS

            await send_chunk(
                first_time,
                init_end,
                "INIT"
            )

            last_time = init_end

            while last_time < max_time:

                async with db_lock:
                    cur.execute("""
                        SELECT MIN(snapshot_time)
                        FROM adsb_playback
                        WHERE snapshot_time > %s
                    """, (last_time,))

                    next_time = cur.fetchone()[0]

                if not next_time:
                    break

                await asyncio.sleep(
                    max(0.5, next_time - last_time)
                )

                await send_chunk(
                    last_time,
                    next_time,
                    "APPEND"
                )

                last_time = next_time

            print("[AIRCRAFT WS] finished")

        await asyncio.gather(
            receiver(),
            streamer()
        )

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()