import os
import mercantile
import numpy as np

from PIL import Image

INPUT_FILE = "weather_grid.npz"

OUTPUT_DIR = "tiles/weather/current"

TILE_SIZE = 256

MIN_ZOOM = 0
MAX_ZOOM = 5

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------
# Load cached weather grid
# ---------------------------------------------------

print("loading weather grid")

data = np.load(INPUT_FILE)

temps = data["temps"]
latitudes = data["latitudes"]
longitudes = data["longitudes"]

LAT_STEP = latitudes[1] - latitudes[0]
LON_STEP = longitudes[1] - longitudes[0]

print("grid loaded")


# ---------------------------------------------------
# Bilinear sampling
# ---------------------------------------------------

def sample_temp(lat, lon):

    gx = (lon + 180) / LON_STEP
    gy = (lat + 88) / LAT_STEP

    x0 = int(np.floor(gx))
    y0 = int(np.floor(gy))

    x1 = min(x0 + 1, len(longitudes) - 1)
    y1 = min(y0 + 1, len(latitudes) - 1)

    x0 = max(0, x0)
    y0 = max(0, y0)

    fx = gx - x0
    fy = gy - y0

    t00 = temps[y0, x0]
    t10 = temps[y0, x1]
    t01 = temps[y1, x0]
    t11 = temps[y1, x1]

    vals = [t00, t10, t01, t11]

    if any(np.isnan(v) for v in vals):
        valid = [v for v in vals if not np.isnan(v)]

        if not valid:
            return np.nan

        return float(np.mean(valid))

    top = t00 * (1 - fx) + t10 * fx
    bottom = t01 * (1 - fx) + t11 * fx

    return top * (1 - fy) + bottom * fy


# ---------------------------------------------------
# FINAL COLOR RAMP
# ---------------------------------------------------

def color(temp):

    if temp is None or np.isnan(temp):
        return (0, 0, 0, 0)

    t = max(-30.0, min(40.0, float(temp)))

    n = (t + 30.0) / 70.0

    # balanced perceptual curve
    n = n ** 0.9

    STOPS = [
        (0.00, (80, 0, 120)),
        (0.15, (0, 80, 255)),
        (0.35, (0, 220, 255)),
        (0.50, (0, 255, 120)),
        (0.65, (255, 255, 0)),
        (0.82, (255, 170, 0)),
        (1.00, (255, 0, 60)),
    ]

    for i in range(len(STOPS) - 1):

        s0, c0 = STOPS[i]
        s1, c1 = STOPS[i + 1]

        if n >= s0 and n <= s1:

            u = (n - s0) / (s1 - s0)

            r = int(c0[0] + (c1[0] - c0[0]) * u)
            g = int(c0[1] + (c1[1] - c0[1]) * u)
            b = int(c0[2] + (c1[2] - c0[2]) * u)

            return (r, g, b, 180)

    return (255, 0, 60, 180)


# ---------------------------------------------------
# Generate tiles
# ---------------------------------------------------

for z in range(MIN_ZOOM, MAX_ZOOM + 1):

    print(f"zoom {z}")

    for tile in mercantile.tiles(-180, -85, 180, 85, z):

        bounds = mercantile.bounds(tile)

        rgba = np.zeros(
            (TILE_SIZE, TILE_SIZE, 4),
            dtype=np.uint8
        )

        for py in range(TILE_SIZE):

            lat = bounds.north - (
                py / TILE_SIZE
            ) * (bounds.north - bounds.south)

            for px in range(TILE_SIZE):

                lon = bounds.west + (
                    px / TILE_SIZE
                ) * (bounds.east - bounds.west)

                temp = sample_temp(lat, lon)

                rgba[py, px] = color(temp)

        img = Image.fromarray(rgba, mode="RGBA")

        tile_dir = os.path.join(
            OUTPUT_DIR,
            str(z),
            str(tile.x)
        )

        os.makedirs(tile_dir, exist_ok=True)

        tile_path = os.path.join(
            tile_dir,
            f"{tile.y}.png"
        )

        img.save(tile_path)

        print("saved", z, tile.x, tile.y)

print("done")