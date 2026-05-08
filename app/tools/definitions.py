# Raw function declarations — consumed by types.Tool(function_declarations=TOOL_DECLARATIONS)
TOOL_DECLARATIONS = [
    {
        "name": "get_stock_metrics",
        "description": (
            "Get stock price return metrics for a company over a date range. "
            "Returns start/end price, total return %, and comparison to S&P 500."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol e.g. AAPL, MSFT, TSLA",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["ticker", "start_date", "end_date"],
        },
    },
    {
        "name": "get_stock_history",
        "description": (
            "Get daily OHLCV (open, high, low, close, volume) stock price history. "
            "Use this when the user wants to see price trends over time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
            },
            "required": ["ticker", "start_date", "end_date"],
        },
    },
    {
        "name": "search_filings",
        "description": (
            "Search through ingested 10-K SEC filings using semantic similarity. "
            "Use this to find what management said about revenue guidance, risk factors, "
            "strategy, earnings, or any other topic in their annual reports."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query e.g. 'revenue guidance 2023'",
                },
                "ticker": {
                    "type": "string",
                    "description": "Filter results to a specific company ticker (optional)",
                },
                "year": {
                    "type": "integer",
                    "description": "Filter results to a specific fiscal year (optional). If the user mentions a year, always pass it here.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of passages to return, default 5",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "compare_to_benchmark",
        "description": (
            "Compare a stock's return against a benchmark index to compute alpha. "
            "Default benchmark is SPY (S&P 500 ETF). Use for questions like "
            "'did Apple outperform the market?'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol to evaluate"},
                "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                "benchmark": {"type": "string", "description": "Benchmark ticker, default SPY"},
            },
            "required": ["ticker", "start_date", "end_date"],
        },
    },
]
