import os
import mercantile
import rasterio
import numpy as np

from rasterio.windows import from_bounds
from PIL import Image

RASTER_PATH = "data/worldpop.tif"
OUTPUT_DIR = "tiles/population"

TILE_SIZE = 256

MIN_ZOOM = 0
MAX_ZOOM = 5

os.makedirs(OUTPUT_DIR, exist_ok=True)


with rasterio.open(RASTER_PATH) as src:

    for z in range(MIN_ZOOM, MAX_ZOOM + 1):

        print(f"Generating zoom {z}")

        for tile in mercantile.tiles(-180, -85, 180, 85, z):

            bounds = mercantile.bounds(tile)

            try:
                window = from_bounds(
                    bounds.west,
                    bounds.south,
                    bounds.east,
                    bounds.north,
                    src.transform
                )

                data = src.read(
                    1,
                    window=window,
                    out_shape=(TILE_SIZE, TILE_SIZE),
                    resampling=rasterio.enums.Resampling.average
                )

                # --- CLEANUP / NORMALIZATION ---
                data = np.nan_to_num(data)
                data[data < 0] = 0

                data = np.log1p(data)

                if data.max() > 0:
                    data = data / data.max()

                data = (data * 255).astype(np.uint8)

                # --- IMAGE BUFFER ---
                rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)

                # --- COLOR RAMP ---
                for i in range(TILE_SIZE):
                    for j in range(TILE_SIZE):

                        v = data[i, j]

                        if v <= 0:
                            continue

                        # gamma correction
                        v = (v / 255.0) ** 0.55
                        v = int(v * 255)

                        # heatmap gradient
                        if v < 50:
                            r, g, b = 0, 0, 80 + v * 2

                        elif v < 100:
                            r, g, b = 0, v * 2, 255

                        elif v < 150:
                            r, g, b = (v - 100) * 5, 255, 255 - (v - 100) * 3

                        elif v < 200:
                            r, g, b = 255, 255 - (v - 150) * 3, 0

                        else:
                            r, g, b = 255, int(255 - (v - 200) * 1.5), 0

                        a = int(v * 0.9)

                        rgba[i, j] = [r, g, b, a]

                img = Image.fromarray(rgba, mode="RGBA")

                tile_dir = os.path.join(
                    OUTPUT_DIR,
                    str(z),
                    str(tile.x)
                )

                os.makedirs(tile_dir, exist_ok=True)

                tile_path = os.path.join(tile_dir, f"{tile.y}.png")

                img.save(tile_path)

            except Exception as e:
                print("failed tile:", tile, e)

print("done")