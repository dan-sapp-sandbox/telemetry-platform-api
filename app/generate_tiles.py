import os
import mercantile
import rasterio
import numpy as np

from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from PIL import Image

RASTER_PATH = "data/worldpop.tif"
OUTPUT_DIR = "tiles/population"

TILE_SIZE = 256

MIN_ZOOM = 0
MAX_ZOOM = 5

WEB_MERCATOR = "EPSG:3857"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def heatmap_gradient(v):

    rgba = np.zeros((v.shape[0], v.shape[1], 4), dtype=np.uint8)

    vf = v.astype(np.float32) / 255.0
    vf = np.power(vf, 0.55)

    vv = (vf * 255).astype(np.uint8)

    r = np.zeros_like(vv)
    g = np.zeros_like(vv)
    b = np.zeros_like(vv)

    m1 = vv < 50
    b[m1] = 80 + vv[m1] * 2

    m2 = (vv >= 50) & (vv < 100)
    g[m2] = vv[m2] * 2
    b[m2] = 255

    m3 = (vv >= 100) & (vv < 150)
    r[m3] = (vv[m3] - 100) * 5
    g[m3] = 255
    b[m3] = 255 - (vv[m3] - 100) * 3

    m4 = (vv >= 150) & (vv < 200)
    r[m4] = 255
    g[m4] = 255 - (vv[m4] - 150) * 3

    m5 = vv >= 200
    r[m5] = 255
    g[m5] = np.clip(
        255 - ((vv[m5] - 200) * 1.5),
        0,
        255
    ).astype(np.uint8)

    alpha = (vf * 255 * 0.9).astype(np.uint8)

    rgba[..., 0] = r
    rgba[..., 1] = g
    rgba[..., 2] = b
    rgba[..., 3] = alpha

    return rgba


with rasterio.open(RASTER_PATH) as src:

    dataset_max = 5000.0

    for z in range(MIN_ZOOM, MAX_ZOOM + 1):

        print(f"Generating zoom {z}")

        for tile in mercantile.tiles(-180, -85, 180, 85, z):

            try:

                bounds = mercantile.xy_bounds(tile)

                dst_transform = from_bounds(
                    bounds.left,
                    bounds.bottom,
                    bounds.right,
                    bounds.top,
                    TILE_SIZE,
                    TILE_SIZE
                )

                destination = np.zeros(
                    (TILE_SIZE, TILE_SIZE),
                    dtype=np.float32
                )

                reproject(
                    source=rasterio.band(src, 1),
                    destination=destination,

                    src_transform=src.transform,
                    src_crs=src.crs,

                    dst_transform=dst_transform,
                    dst_crs=WEB_MERCATOR,

                    resampling=Resampling.bilinear
                )

                data = np.nan_to_num(destination)
                data[data < 0] = 0

                data = np.clip(data, 0, dataset_max)

                data = np.log1p(data)
                data /= np.log1p(dataset_max)

                data = (data * 255).astype(np.uint8)

                rgba = heatmap_gradient(data)

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

            except Exception as e:
                print("failed tile:", tile, e)

print("done")