import json
from openai import OpenAI
from app.models.commands import CommandRequest, CommandResponse
import os
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
  You are a command router.

  Pick the best matching tool from the list.
  Only return a valid structured response.
  If user intent matches a tool, you MUST select it.

  If not execute as a normal ChatGPT query and return response
""".strip()

async def resolve_command(payload: CommandRequest) -> CommandResponse:
    tools_text = "\n\n".join(
        [
            f"""
                {tool.name}
                - description: {tool.description}
                - params: {json.dumps(tool.parameters)}
            """.strip()
            for tool in payload.tools
        ]
    )

    response = client.responses.parse(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": f"""
                    User request:
                    {payload.prompt}

                    Tools:
                    {tools_text}
                """.strip(),
            },
        ],
        text_format={
            "type": "json_schema",
            "name": "command",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {
                        "type": ["string", "null"],
                    },
                    "args": {
                        "type": "object",
                    },
                },
                "required": ["action", "args"],
            },
        },
    )

    parsed = response.output_parsed

    if not parsed:
        return CommandResponse(action=None, args={})

    return CommandResponse(**parsed)