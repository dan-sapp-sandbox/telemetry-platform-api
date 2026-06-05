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

    CHUNK_MS = 30_000
    INIT_WINDOW_MS = 5 * 60 * 1000

    try:
        conn = get_conn()
        cur = conn.cursor()

        print("[AIS WS] started")

        async def receiver():
            nonlocal bounds

            while True:
                bounds = await websocket.receive_json()

        async def send_chunk(start_ms, end_ms, label):
            west = bounds["west"]
            east = bounds["east"]
            south = bounds["south"]
            north = bounds["north"]

            query = """
            SELECT
                mmsi,
                timestamp_ms,
                lat,
                lon,
                sog,
                cog,
                heading,
                ship_name,
                nav_status,
                rot
            FROM ais_position_reports
            WHERE timestamp_ms BETWEEN %s AND %s
              AND lon BETWEEN %s AND %s
              AND lat BETWEEN %s AND %s
            ORDER BY mmsi, timestamp_ms ASC
            """

            cur.execute(
                query,
                (
                    start_ms,
                    end_ms,
                    west,
                    east,
                    south,
                    north,
                ),
            )

            rows = cur.fetchall()

            by_mmsi = {}

            for r in rows:
                mmsi = r[0]

                if mmsi not in by_mmsi:
                    by_mmsi[mmsi] = []

                by_mmsi[mmsi].append(
                    {
                        "mmsi": r[0],
                        "timestamp_ms": r[1],
                        "lat": r[2],
                        "lon": r[3],
                        "sog": r[4],
                        "cog": r[5],
                        "heading": r[6],
                        "ship_name": r[7],
                        "nav_status": r[8],
                        "rot": r[9],
                    }
                )

            await websocket.send_json(
                {
                    "type": label.lower(),
                    "start_time": start_ms,
                    "end_time": end_ms,
                    "snapshots": by_mmsi,
                }
            )

            print(
                f"[AIS WS] {label}: "
                f"vessels={len(by_mmsi)} "
                f"total_points={len(rows)}"
            )

        async def streamer():
            nonlocal bounds

            while not bounds:
                await asyncio.sleep(0.1)

            cur.execute("""
                SELECT
                    MIN(timestamp_ms),
                    MAX(timestamp_ms)
                FROM ais_position_reports
            """)

            first_timestamp, max_timestamp = cur.fetchone()

            if first_timestamp is None:
                print("[AIS WS] no AIS data")
                return

            first_timestamp = (
                first_timestamp // CHUNK_MS
            ) * CHUNK_MS

            init_end = min(
                first_timestamp + INIT_WINDOW_MS,
                max_timestamp,
            )

            await send_chunk(
                first_timestamp,
                init_end,
                "INIT",
            )

            last_sent_end = init_end

            while last_sent_end < max_timestamp:
                await asyncio.sleep(CHUNK_MS / 1000)

                chunk_end = min(
                    last_sent_end + CHUNK_MS,
                    max_timestamp,
                )

                await send_chunk(
                    last_sent_end,
                    chunk_end,
                    "APPEND",
                )

                last_sent_end = chunk_end

            print("[AIS WS] reached end of dataset")

        await asyncio.gather(
            receiver(),
            streamer(),
        )

    except WebSocketDisconnect:
        print("[AIS WS] disconnected")

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()