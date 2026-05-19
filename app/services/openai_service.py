from openai import OpenAI
from app.models.commands import CommandRequest, CommandResponse
import os
from dotenv import load_dotenv
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ------------------------------------------------------------
# TOOL DEFINITIONS (backend-owned, not passed from frontend)
# ------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "name": "center_map",
        "description": (
            "Centers the map on a geographic location such as a city, "
            "country, region, continent, or ocean."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Geographic place name such as 'Paris', 'Japan', "
                        "'Europe', 'Indian Ocean', etc."
                    ),
                }
            },
            "required": ["query"],
        },
    }
]


# ------------------------------------------------------------
# SYSTEM PROMPT
# ------------------------------------------------------------

SYSTEM_PROMPT = """
You are a geospatial command router.

Your job is to convert user input into map actions.

RULES:
- If the user mentions ANY geographic location (city, country, region, ocean, continent), use the center_map tool.
- Do NOT answer questions.
- Do NOT provide explanations.
- Only return tool calls when possible.
- If no valid location is found, return no tool call.
""".strip()


# ------------------------------------------------------------
# MAIN RESOLVER
# ------------------------------------------------------------

async def resolve_command(payload: CommandRequest) -> CommandResponse:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": payload.prompt,
            },
        ],
        tools=TOOLS,
    )

    # ------------------------------------------------------------
    # Extract tool call safely
    # ------------------------------------------------------------

    tool_call = None

    for item in response.output:
        if getattr(item, "type", None) == "function_call":
            tool_call = item
            break

    # ------------------------------------------------------------
    # No tool triggered
    # ------------------------------------------------------------

    if not tool_call:
        return CommandResponse(action=None, args={})

    # ------------------------------------------------------------
    # Parse arguments
    # ------------------------------------------------------------

    try:
        args = json.loads(tool_call.arguments)
    except Exception:
        args = {}

    return CommandResponse(
        action=tool_call.name,
        args=args,
    )