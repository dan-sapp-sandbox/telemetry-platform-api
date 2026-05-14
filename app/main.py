from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()

def get_conn():
  return psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT"),
  )

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://www.dan-sapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/vessels")
def get_vessels(
    west: float = Query(...),
    south: float = Query(...),
    east: float = Query(...),
    north: float = Query(...)
):
    conn = get_conn()
    cur = conn.cursor()

    query = """
    SELECT id, name, type, lat, lon, heading, speed
    FROM vessels
    WHERE ST_Within(
        geom,
        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
    )
    LIMIT 500;
    """

    cur.execute(query, (west, south, east, north))
    rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "name": r[1],
            "type": r[2],
            "lat": r[3],
            "lon": r[4],
            "heading": r[5],
            "speed": r[6],
        }
        for r in rows
    ]
