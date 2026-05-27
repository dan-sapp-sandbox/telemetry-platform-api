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
    bounds_version = 0

    current_time = None

    SIM_SPEED = 1.0
    TICK_MS = 1000  # 1 second simulation step

    BATCH_MS = 15_000
    last_sent_window = None

    try:
        conn = get_conn()
        cur = conn.cursor()

        # start at earliest AIS timestamp
        cur.execute("""
            SELECT MIN(timestamp_ms)
            FROM ais_position_reports
        """)
        current_time = cur.fetchone()[0]

        if not current_time:
            return

        # align to batch boundary
        current_time = (current_time // BATCH_MS) * BATCH_MS

        # 🔥 IMPORTANT FIX: prime forward so first send isn't empty
        current_time += TICK_MS

        async def receiver():
            nonlocal bounds, bounds_version

            while True:
                data = await websocket.receive_json()
                bounds = data
                bounds_version += 1

        async def streamer():
            nonlocal current_time, last_sent_window

            while True:
                await asyncio.sleep(0.5)

                if not bounds:
                    continue

                west = bounds["west"]
                east = bounds["east"]
                south = bounds["south"]
                north = bounds["north"]

                # advance simulation
                current_time += SIM_SPEED * TICK_MS

                window = current_time // BATCH_MS

                # only emit once per 15s bucket
                if window == last_sent_window:
                    continue

                last_sent_window = window

                window_time = window * BATCH_MS

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
                  AND (sog > 0.5)
                LIMIT 3000;
                """

                cur.execute(query, (
                    window_time,
                    west, east, south, north
                ))

                rows = cur.fetchall()

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

                await websocket.send_json(vessels)

        await asyncio.gather(receiver(), streamer())

    except WebSocketDisconnect:
        print("[WS] AIS disconnected")

    except Exception as e:
        print("[WS ERROR]", e)

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()