import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import date

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.tools.definitions import TOOL_DECLARATIONS
from app.tools.executors import execute_tool

settings = get_settings()


def _build_system_prompt() -> str:
    today = date.today().isoformat()
    return f"""You are a financial analysis assistant specializing in stock performance and SEC 10-K filings.

Today's date is {today}.

When answering questions:
- Always use the available tools to fetch real data before forming an answer
- When asked about a specific year, search filings for THAT exact year first (pass it as the `year` parameter)
- When asked about guidance vs actual performance, search filings AND get stock metrics
- Be specific: include percentages, dollar amounts, and the exact date range used
- Cite your sources: mention which filing year or date range the data comes from
- If a search returns no results, retry without the year filter before concluding data is unavailable
- If data is unavailable or filings haven't been ingested, say so clearly
"""

MAX_TOOL_ROUNDS = 5

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def run_agent(query: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    try:
        client = _get_client()

        tool = types.Tool(function_declarations=TOOL_DECLARATIONS)
        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(),
            tools=[tool],
        )

        # Conversation history — we manage this manually
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part(text=query)])
        ]

        response = None

        for _ in range(MAX_TOOL_ROUNDS + 1):
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=settings.gemini_model,
                contents=contents,
                config=config,
            )

            model_content = response.candidates[0].content
            contents.append(model_content)

            fn_parts = [
                p for p in model_content.parts
                if p.function_call is not None and p.function_call.name
            ]

            if not fn_parts:
                break

            tool_result_parts: list[types.Part] = []

            for part in fn_parts:
                name = part.function_call.name
                args = dict(part.function_call.args)

                yield f"data: {json.dumps({'type': 'tool_call', 'tool': name, 'args': args})}\n\n"

                result = await execute_tool(name, args, db)

                yield f"data: {json.dumps({'type': 'tool_result', 'tool': name, 'result': result})}\n\n"

                tool_result_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=name,
                            response={"result": json.dumps(result, default=str)},
                        )
                    )
                )

            # Tool results go back as a user turn
            contents.append(types.Content(role="user", parts=tool_result_parts))

        if response is not None:
            yield f"data: {json.dumps({'type': 'final_answer', 'content': response.text})}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    finally:
        yield "data: [DONE]\n\n"
