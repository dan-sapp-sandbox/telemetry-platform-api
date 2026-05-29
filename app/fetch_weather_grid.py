import time
import requests
import numpy as np

LAT_STEP = 4
LON_STEP = 4

OUTPUT_FILE = "weather_grid.npz"

latitudes = np.arange(-88, 89, LAT_STEP)
longitudes = np.arange(-180, 181, LON_STEP)

temps = np.zeros(
    (len(latitudes), len(longitudes)),
    dtype=np.float32
)

print("building weather grid")

# ---------------------------------------------------
# Batch requests per latitude row
# ---------------------------------------------------

for yi, lat in enumerate(latitudes):

    print(f"row {yi+1}/{len(latitudes)}")

    lat_list = []
    lon_list = []

    for lon in longitudes:

        lat_list.append(str(lat))
        lon_list.append(str(lon))

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={','.join(lat_list)}"
        f"&longitude={','.join(lon_list)}"
        "&current=temperature_2m"
    )

    try:

        r = requests.get(url, timeout=30)

        data = r.json()

        # API returns list for batch mode
        if not isinstance(data, list):
            print("bad response:", data)
            continue

        for xi, item in enumerate(data):

            try:
                temps[yi, xi] = item["current"]["temperature_2m"]

            except:
                temps[yi, xi] = np.nan

    except Exception as e:

        print("request failed:", lat, e)

    time.sleep(0.25)

print("saving grid")

np.savez_compressed(
    OUTPUT_FILE,
    temps=temps,
    latitudes=latitudes,
    longitudes=longitudes,
)

print("done")