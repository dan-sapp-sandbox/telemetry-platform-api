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
            "Centers the map on a geographic location and suggests a camera altitude "
            "appropriate for the scale of the place."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Place name like city, country, ocean, etc.",
                },
                "camera_altitude_m": {
                    "type": "number",
                    "description": (
                        "Recommended camera altitude in meters. "
                        "Represents appropriate zoom level for the place scale."
                    ),
                }
            },
            "required": ["query", "camera_altitude_m"],
        },
    },
    {
        "type": "function",
        "name": "show_vessel_layer",
        "description": (
            "Enable the vessel/ship/boat AIS data layer."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "show_aircraft_layer",
        "description": (
            "Enable the aircraft/plane ADS-B data layer."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


# ------------------------------------------------------------
# SYSTEM PROMPT
# ------------------------------------------------------------

SYSTEM_PROMPT = """
You are a geospatial command router.

Your job is to convert user input into map actions.

RULES:
- If the user mentions ANY geographic location, use the center_map tool.
- If the user mentions boats, ships, shipping, maritime traffic, vessels, AIS, etc., use show_vessel_layer.
- If the user mentions planes, aircraft, flights, aviation, ADS-B, etc., use show_aircraft_layer.
- You MUST estimate an appropriate camera_altitude_m based on the scale of the place:
    - small landmark / building: 500m - 5,000m
    - city: 20,000m - 150,000m
    - region/state: 100,000m - 500,000m
    - country: 300,000m - 2,000,000m
    - continent/ocean: 2,000,000m - 10,000,000m
- Do NOT answer questions.
- Do NOT explain anything.
- Only return tool calls.
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

    tool_calls = [
        item
        for item in response.output
        if item.type == "function_call"
    ]

    if not tool_calls:
        return CommandResponse(actions=[])

    actions = []

    for tool_call in tool_calls:
        if tool_call.name == "show_vessel_layer":
            actions.append({
                "action": "show_vessel_layer",
                "args": {}
            })

        elif tool_call.name == "show_aircraft_layer":
            actions.append({
                "action": "show_aircraft_layer",
                "args": {}
            })

        elif tool_call.name == "center_map":
            args = json.loads(tool_call.arguments)

            query = args.get("query")
            if not query:
                continue

            geo = geocode(query)
            if not geo:
                continue

            actions.append({
                "action": "center_map",
                "args": {
                    "query": query,
                    "lat": geo["lat"],
                    "lon": geo["lon"],
                    "camera_altitude_m": args.get("camera_altitude_m"),
                }
            })

    return CommandResponse(actions=actions)