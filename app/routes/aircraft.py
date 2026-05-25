from fastapi import APIRouter, Query
router = APIRouter()
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2

def get_conn():
  return psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT"),
  )


OPENSKY_URL = (
    "https://opensky-network.org/api/states/all"
)


@router.get("/adsb-aircraft")
def get_adsb_aircraft(
    lamin: float = Query(...),
    lomin: float = Query(...),
    lamax: float = Query(...),
    lomax: float = Query(...),
):
    try:
        params = {
            "lamin": lamin,
            "lomin": lomin,
            "lamax": lamax,
            "lomax": lomax,
        }

        response = requests.get(
            OPENSKY_URL,
            params=params,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:
        return {
            "error": str(e)
        }

@router.get("/get-aircraft")
def get_aircraft():
    conn = get_conn()
    cur = conn.cursor()

    try:
        query = """
        SELECT id, name, route_id, speed_mps, start_offset_seconds, route_offset_meters
        FROM aircraft
        LIMIT 500;
        """

        cur.execute(query)
        rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "name": r[1],
                "routeId": r[2],
                "speedMps": r[3],
                "startOffsetSeconds": r[4],
                "routeOffsetMeters": r[5],
            }
            for r in rows
        ]

    finally:
        cur.close()
        conn.close()

@router.get("/get-air-routes")
def get_air_routes():
    conn = get_conn()
    cur = conn.cursor()

    try:
        query = """
        SELECT id, name, points
        FROM air_routes
        LIMIT 500;
        """

        cur.execute(query)
        rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "name": r[1],
                "points": r[2],
            }
            for r in rows
        ]

    finally:
        cur.close()
        conn.close()