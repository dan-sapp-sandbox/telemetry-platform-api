from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
import asyncio
import os
from dotenv import load_dotenv
import psycopg2
from supabase import create_client
from app.models.ais import AISVessel, AISIngestRequest

router = APIRouter()
load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

def get_conn():
  return psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT"),
  )

def transform_vessel(capture_session_id: str, vessel: AISVessel):
    return {
        "capture_session_id": capture_session_id,

        "timestamp_ms": vessel.timestamp,

        "mmsi": vessel.mmsi,

        "ship_name": vessel.shipName,

        "lat": vessel.latitude,
        "lon": vessel.longitude,

        "sog": vessel.sog,
        "cog": vessel.cog,
        "heading": vessel.heading,

        "nav_status": vessel.navStatus,
        "rot": vessel.rot,
    }


def chunked(lst, size=500):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


@router.post("/ingest-ais")
def ingest_ais(payload: AISIngestRequest):
    rows = []

    for vessel in payload.vessels:
        rows.append(
            transform_vessel(
                payload.captureSessionId,
                vessel
            )
        )

    inserted = 0

    for batch in chunked(rows, 500):
        supabase.table("ais_position_reports") \
            .insert(batch) \
            .execute()

        inserted += len(batch)

    return {
        "capture_session_id": payload.captureSessionId,
        "rows_inserted": inserted
    }

@router.websocket("/ws/ais")
async def ais_ws(websocket: WebSocket):
    await websocket.accept()

    conn = None
    cur = None

    bounds = None

    WINDOW_MS = 30_000
    INIT_WINDOW_MS = 5 * 60 * 1000

    last_sent_time = None

    try:
        conn = get_conn()
        cur = conn.cursor()

        print("[AIS WS] started")

        # start time
        cur.execute("""
            SELECT MIN(timestamp_ms)
            FROM ais_position_reports
        """)
        start_time = cur.fetchone()[0]

        if not start_time:
            print("[AIS WS] no data")
            return

        start_time = (start_time // WINDOW_MS) * WINDOW_MS

        async def receiver():
            nonlocal bounds

            print("[AIS WS] receiver started")

            while True:
                bounds = await websocket.receive_json()
                print(f"[AIS WS] bounds updated: {bounds}")

        async def send_window(start_ms, end_ms, label):
            west = bounds["west"]
            east = bounds["east"]
            south = bounds["south"]
            north = bounds["north"]

            print(f"[AIS WS] {label}: {start_ms} → {end_ms}")

            query = """
            WITH latest AS (
                SELECT DISTINCT ON (mmsi)
                    mmsi,
                    ship_name,
                    lon,
                    lat,
                    sog,
                    cog,
                    heading,
                    nav_status,
                    rot,
                    timestamp_ms
                FROM ais_position_reports
                WHERE timestamp_ms <= %s
                ORDER BY mmsi, timestamp_ms DESC
            )
            SELECT *
            FROM latest
            WHERE lon BETWEEN %s AND %s
              AND lat BETWEEN %s AND %s
            LIMIT 1000;
            """

            cur.execute(query, (
                end_ms,
                west, east,
                south, north
            ))

            rows = cur.fetchall()

            print(f"[AIS WS] rows ({label}) = {len(rows)}")

            vessels = [
                {
                    "mmsi": r[0],
                    "ship_name": r[1],
                    "lon": r[2],
                    "lat": r[3],
                    "sog": r[4],
                    "cog": r[5],
                    "heading": r[6],
                    "nav_status": r[7],
                    "rot": r[8],
                    "timestamp_ms": r[9],
                }
                for r in rows
            ]

            await websocket.send_json({
                "type": label,
                "start": start_ms,
                "end": end_ms,
                "vessels": vessels
            })

        async def streamer():
            nonlocal last_sent_time

            print("[AIS WS] streamer started")

            # wait for bounds first
            while not bounds:
                await asyncio.sleep(0.1)

            print("[AIS WS] initial bounds locked")

            # INIT: 5 minute chunk
            last_sent_time = start_time

            init_end = last_sent_time + INIT_WINDOW_MS

            await send_window(last_sent_time, init_end, "INIT")

            last_sent_time = init_end

            # LOOP: 30 second chunks
            while True:
                await asyncio.sleep(30)

                if not bounds:
                    continue

                next_end = last_sent_time + WINDOW_MS

                await send_window(last_sent_time, next_end, "APPEND")

                last_sent_time = next_end

        await asyncio.gather(receiver(), streamer())

    except WebSocketDisconnect:
        print("[AIS WS] disconnected")

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()