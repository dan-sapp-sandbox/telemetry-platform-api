from openai import OpenAI
from app.models.commands import CommandRequest, CommandResponse
import os
from dotenv import load_dotenv
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="sc-intelligence")


def geocode(query: str):
    location = geolocator.geocode(query)
    if not location:
        return None

    return {
        "lat": location.latitude,
        "lon": location.longitude,
        "display_name": location.address,
    }


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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": payload.prompt},
        ],
        tools=TOOLS,
    )

    tool_call = next(
        (item for item in response.output if item.type == "function_call"),
        None
    )

    if not tool_call:
        return CommandResponse(action=None, args={})

    args = json.loads(tool_call.arguments)
    query = args.get("query")

    geo = geocode(query)

    if not geo:
        return CommandResponse(action=None, args={})

    return CommandResponse(
        action="center_map",
        args={
            "query": query,
            "lat": geo["lat"],
            "lon": geo["lon"],
        },
    )