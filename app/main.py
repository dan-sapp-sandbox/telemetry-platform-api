from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles

from app.routes.commands import router as commands_router
from app.routes.vessels import router as vessels_router
from app.routes.aircraft import router as aircraft_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://www.dan-sapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.mount(
#     "/tiles",
#     StaticFiles(directory="tiles"),
#     name="tiles"
# )

app.include_router(commands_router, prefix="/api/ai")
app.include_router(vessels_router, prefix="/api/vessels")
app.include_router(aircraft_router, prefix="/api/aircraft")
