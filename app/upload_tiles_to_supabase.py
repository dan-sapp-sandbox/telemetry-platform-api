import os
import time
from supabase import create_client, ClientOptions
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(
        postgrest_client_timeout=300,
        storage_client_timeout=300
    )
)

BUCKET = "tiles"
BASE_DIR = "tiles/population"

def upload_file(local_path, remote_path, retries=3):
    for i in range(retries):
        try:
            with open(local_path, "rb") as f:
                supabase.storage.from_("tiles").upload(
                    remote_path,
                    f,
                    file_options={
                        "content-type": "image/png",
                        "upsert": "true",
                    },
                )
            return
        except Exception as e:
            print(f"retry {i+1} failed:", remote_path, e)
            time.sleep(2)

    print("FAILED:", remote_path)


for z in os.listdir(BASE_DIR):
    z_path = os.path.join(BASE_DIR, z)

    if not os.path.isdir(z_path):
        continue

    for x in os.listdir(z_path):
        x_path = os.path.join(z_path, x)

        if not os.path.isdir(x_path):
            continue

        for y_file in os.listdir(x_path):

            if not y_file.endswith(".png"):
                continue

            local_path = os.path.join(x_path, y_file)

            remote_path = f"population/{z}/{x}/{y_file}"

            print("uploading", remote_path)

            upload_file(local_path, remote_path)

print("done")