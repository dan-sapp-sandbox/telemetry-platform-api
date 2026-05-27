from pydantic import BaseModel
from typing import Optional, List


class AISVessel(BaseModel):
    mmsi: int

    timestamp: int

    latitude: float
    longitude: float

    sog: Optional[float] = None
    cog: Optional[float] = None
    heading: Optional[float] = None

    navStatus: Optional[int] = None
    rot: Optional[float] = None

    shipName: Optional[str] = None


class AISIngestRequest(BaseModel):
    captureSessionId: str
    vessels: List[AISVessel]