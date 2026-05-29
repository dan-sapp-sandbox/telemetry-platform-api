from fastapi import APIRouter
from fastapi.responses import Response
import math
import requests
import io
from PIL import Image

router = APIRouter()

TILE_SIZE = 256
GRID = 16


# ---------------------------------------------------
# Tile bounds
# ---------------------------------------------------
def tile_bounds(x, y, z):
    n = 2.0 ** z

    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    lat_max = math.degrees(
        math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    )

    lat_min = math.degrees(
        math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    )

    return lon_min, lat_min, lon_max, lat_max


# ---------------------------------------------------
# Color ramp
# ---------------------------------------------------
def color(temp):
    if temp is None:
        return (0, 0, 0, 0)

    if temp <= -10:
        return (0, 80, 255, 180)

    if temp <= 0:
        return (0, 180, 255, 180)

    if temp <= 10:
        return (0, 255, 120, 180)

    if temp <= 20:
        return (255, 255, 0, 180)

    if temp <= 30:
        return (255, 140, 0, 180)

    return (255, 0, 0, 180)


# ---------------------------------------------------
# Weather tile endpoint
# ---------------------------------------------------
@router.get("/tiles/{z}/{x}/{y}.png")
def weather_tile(z: int, x: int, y: int):

    min_lon, min_lat, max_lon, max_lat = tile_bounds(x, y, z)

    # ---------------------------------------------------
    # Build coordinate lists
    # ---------------------------------------------------
    lats = []
    lons = []

    for gy in range(GRID):
        lat = max_lat - (gy / (GRID - 1)) * (max_lat - min_lat)
        lats.append(round(lat, 4))

    for gx in range(GRID):
        lon = min_lon + (gx / (GRID - 1)) * (max_lon - min_lon)
        lons.append(round(lon, 4))

    lat_str = ",".join(map(str, lats))
    lon_str = ",".join(map(str, lons))

    # ---------------------------------------------------
    # ONE Open-Meteo request
    # ---------------------------------------------------
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat_str}"
        f"&longitude={lon_str}"
        "&current=temperature_2m"
    )

    r = requests.get(url, timeout=10)

    if r.status_code != 200:
        return Response(status_code=500)

    data = r.json()

    # ---------------------------------------------------
    # Open-Meteo returns array of results
    # ---------------------------------------------------
    temps = []

    try:
        for item in data:
            temps.append(item["current"]["temperature_2m"])
    except Exception:
        return Response(status_code=500)

    # ---------------------------------------------------
    # Convert flat temps -> 2D grid
    # ---------------------------------------------------
    samples = []

    idx = 0

    for gy in range(GRID):
        row = []

        for gx in range(GRID):
            row.append(temps[idx])
            idx += 1

        samples.append(row)

    # ---------------------------------------------------
    # Create image
    # ---------------------------------------------------
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE))
    pixels = img.load()

    # ---------------------------------------------------
    # Bilinear interpolation
    # ---------------------------------------------------
    for py in range(TILE_SIZE):

        ny = py / TILE_SIZE
        sy = ny * (GRID - 1)

        y0 = int(math.floor(sy))
        y1 = min(y0 + 1, GRID - 1)

        fy = sy - y0

        for px in range(TILE_SIZE):

            nx = px / TILE_SIZE
            sx = nx * (GRID - 1)

            x0 = int(math.floor(sx))
            x1 = min(x0 + 1, GRID - 1)

            fx = sx - x0

            t00 = samples[y0][x0]
            t10 = samples[y0][x1]
            t01 = samples[y1][x0]
            t11 = samples[y1][x1]

            top = t00 * (1 - fx) + t10 * fx
            bottom = t01 * (1 - fx) + t11 * fx

            temp = top * (1 - fy) + bottom * fy

            pixels[px, py] = color(temp)

    # ---------------------------------------------------
    # Return PNG
    # ---------------------------------------------------
    buf = io.BytesIO()

    img.save(buf, format="PNG")

    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="image/png"
    )
