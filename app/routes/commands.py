from fastapi import APIRouter

from app.models.commands import CommandRequest
from app.services.openai_service import resolve_command

router = APIRouter()

@router.post("/commands")
async def commands(payload: CommandRequest):
    result = await resolve_command(payload)
    return result