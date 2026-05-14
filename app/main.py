from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://www.dan-sapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

with open("app/vessels.json") as f:
    vessels = json.load(f)

@app.get("/api/vessels")
def get_vessels(
    west: float = Query(...),
    south: float = Query(...),
    east: float = Query(...),
    north: float = Query(...)
):
    # filter latitude
    def in_bounds(v):
        lat_ok = south <= v["lat"] <= north

        # handle dateline wrap
        if west <= east:
            lon_ok = west <= v["lon"] <= east
        else:
            lon_ok = v["lon"] >= west or v["lon"] <= east

        return lat_ok and lon_ok

    filtered = list(filter(in_bounds, vessels))

    return filtered[:500]