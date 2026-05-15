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
- Always pass the `ticker` parameter to search_filings matching the exact company in the question — NEVER search filings without a ticker, and NEVER use results from a different company than the one being asked about
- When asked about a specific year, search filings for THAT exact year first (pass it as the `year` parameter)
- If no year is mentioned, use the most recent available year (default to current year minus 1)
- When asked about guidance vs actual performance, search filings AND get stock metrics
- When searching for financial figures (revenue, earnings, profit, margins), use specific 10-K language in the query parameter: e.g. "total net revenues annual results", "net income earnings per share", "gross margin operating income" — avoid single generic words like "revenue" or "earnings" which match methodology text instead of financial tables
- If the first search_filings call returns only methodology or policy text without actual numbers, retry with a more specific query like "total revenues segment breakdown fiscal year results"
- Be specific: include percentages, dollar amounts, and the exact date range used
- Cite your sources: mention which filing year or date range the data comes from
When search_filings returns empty results, you MUST follow this exact sequence — do not skip any step:
  Step 1. Call fetch_10k with the ticker and year to download and ingest the filing
  Step 2. After fetch_10k completes, retry search_filings with the same ticker and year
  Step 3. Only if search_filings is still empty after step 2, respond with NEEDS_WEB_SEARCH
  Never jump to NEEDS_WEB_SEARCH without first attempting fetch_10k.
- If none of the available tools can answer the question AND fetch_10k has been attempted, respond with the single word: NEEDS_WEB_SEARCH
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

        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(),
            tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
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

            # If the loop ended on tool calls, explicitly request a synthesis pass.
            if not final_text:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=(
                            "You have now gathered all the data you need. "
                            "Please synthesize it into a complete answer. "
                            "If the tools did not return enough information, "
                            "respond with the single word: NEEDS_WEB_SEARCH"
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

            # Phase 2: web search fallback when filing tools couldn't answer
            if not final_text or final_text.strip() == "NEEDS_WEB_SEARCH":
                yield f"data: {json.dumps({'type': 'step', 'content': 'Filing data insufficient — searching the web…'})}\n\n"
                web_config = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                )
                web_response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=settings.gemini_model,
                    contents=[types.Content(role="user", parts=[types.Part(text=query)])],
                    config=web_config,
                )
                final_text = web_response.text

            yield f"data: {json.dumps({'type': 'final_answer', 'content': final_text})}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    finally:
        yield "data: [DONE]\n\n"
