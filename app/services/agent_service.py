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

For buy / hold / sell questions:
1. Call get_stock_valuation to get current price, P/E, 52-week range, analyst target, and consensus
2. Call search_filings to retrieve recent revenue growth, earnings, risks, and management outlook from the 10-K
3. Call compare_to_benchmark to check whether the stock has outperformed or underperformed the market
4. Synthesise a structured recommendation using this format:

   **Recommendation: BUY / HOLD / SELL**

   | Factor | Signal | Detail |
   |---|---|---|
   | Valuation (P/E) | Cheap / Fair / Expensive | forward P/E vs sector / history |
   | Price vs 52-week range | Near low / Mid-range / Near high | % from 52w high/low |
   | Analyst consensus | Buy / Hold / Sell | mean score + implied upside |
   | Revenue growth | Positive / Flat / Negative | % from 10-K or yfinance |
   | Market performance | Outperform / Underperform | alpha vs S&P 500 |

   **Rationale:** 2-3 sentences citing specific numbers from the tools.
   **Key risks:** Bullet the top 2-3 risks from the 10-K risk factors section.
   **Disclaimer:** This is AI-generated analysis, not financial advice.

Weigh the signals: if valuation is cheap AND growth is positive AND analyst consensus is Buy → BUY.
If the stock is near its 52-week high with a stretched P/E and weak growth → SELL or HOLD.
When signals conflict, default to HOLD and explain the tension.
"""

MAX_TOOL_ROUNDS = 8

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
            final_text = response.text
            # Gemini returns None text when the last turn ended on tool calls.
            # Explicitly request a synthesis pass.
            if not final_text:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=(
                            "You have now gathered all the data you need. "
                            "Please synthesize it into a complete buy/hold/sell recommendation "
                            "using the structured table format specified in your instructions."
                        ))],
                    )
                )
                followup = await asyncio.to_thread(
                    client.models.generate_content,
                    model=settings.gemini_model,
                    contents=contents,
                    config=config,
                )
                final_text = followup.text
            yield f"data: {json.dumps({'type': 'final_answer', 'content': final_text})}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    finally:
        yield "data: [DONE]\n\n"
