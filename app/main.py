from fastapi import FastAPI

app = FastAPI()

@app.get("/api/vessels")
def get_vessels():
    return [{"id": "test", "lat": 0, "lon": 0}]