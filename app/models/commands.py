from pydantic import BaseModel
from typing import Dict, Any, List, Optional


class Tool(BaseModel):
    name: str
    description: str
    parameters: Dict[str, str]

class CommandRequest(BaseModel):
    prompt: str

class CommandResponse(BaseModel):
    action: Optional[str]
    args: Dict[str, Any]