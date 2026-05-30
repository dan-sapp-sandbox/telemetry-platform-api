import os
import sys
import time
import random
import requests
import numpy as np

LAT_STEP = 2
LON_STEP = 2

OUTPUT_FILE = "weather_grid.npz"

latitudes = np.arange(-88, 89, LAT_STEP)
longitudes = np.arange(-180, 181, LON_STEP)

# ---------------------------------------------------
# Safety guard
# ---------------------------------------------------

if os.path.exists(OUTPUT_FILE):
    print(f"{OUTPUT_FILE} already exists. Delete to rebuild.")
    sys.exit(0)

temps = np.full(
    (len(latitudes), len(longitudes)),
    np.nan,
    dtype=np.float32,
)

print("building weather grid")
print(f"{len(latitudes)} rows x {len(longitudes)} cols = {temps.size:,} samples")

# ---------------------------------------------------
# Request helper
# ---------------------------------------------------

def fetch_row(lat, lon_list):

    lat_list = [str(lat)] * len(lon_list)

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={','.join(lat_list)}"
        f"&longitude={','.join(map(str, lon_list))}"
        "&current=temperature_2m"
    )

    # first try
    r = requests.get(url, timeout=60)

    if r.status_code == 429:
        print("429 hit → cooling down 30s")
        time.sleep(30)

        r = requests.get(url, timeout=60)

    r.raise_for_status()

    data = r.json()

    if isinstance(data, dict):
        return [data]

    return data

# ---------------------------------------------------
# Build grid
# ---------------------------------------------------

for yi, lat in enumerate(latitudes):

    print(f"row {yi+1}/{len(latitudes)} (lat={lat})")

    lon_list = longitudes.tolist()

    if not np.isnan(temps[yi]).all():
        continue

    try:
        data = fetch_row(lat, lon_list)

        for xi, item in enumerate(data):
            try:
                temps[yi, xi] = item["current"]["temperature_2m"]
            except Exception:
                temps[yi, xi] = np.nan

    except Exception as e:
        print("FAILED ROW:", lat, e)
        sys.exit(1)

    np.savez_compressed(
        OUTPUT_FILE,
        temps=temps,
        latitudes=latitudes,
        longitudes=longitudes,
    )

    print("checkpoint saved")

    # THIS is the important part
    time.sleep(30 + random.uniform(0, 2))

# ---------------------------------------------------
# Done
# ---------------------------------------------------

print("\ncomplete")
print("valid:", np.count_nonzero(~np.isnan(temps)))
print("min:", np.nanmin(temps))
print("max:", np.nanmax(temps))
print("mean:", np.nanmean(temps))