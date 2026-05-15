import asyncio
from datetime import date
from functools import partial
from typing import Any

import yfinance as yf


def _fetch_sync(ticker: str, start: date, end: date) -> list[dict]:
    df = yf.Ticker(ticker).history(start=str(start), end=str(end))
    if df.empty:
        return []
    df.index = df.index.tz_localize(None)
    return [
        {
            "date": str(row.Index.date()),
            "open": round(row.Open, 2),
            "high": round(row.High, 2),
            "low": round(row.Low, 2),
            "close": round(row.Close, 2),
            "volume": int(row.Volume),
        }
        for row in df.itertuples()
    ]


def _benchmark_return_sync(ticker: str, benchmark: str, start: date, end: date) -> dict:
    t = yf.Ticker(ticker).history(start=str(start), end=str(end))["Close"]
    b = yf.Ticker(benchmark).history(start=str(start), end=str(end))["Close"]
    if t.empty or b.empty:
        return {}
    ticker_return = (t.iloc[-1] - t.iloc[0]) / t.iloc[0] * 100
    benchmark_return = (b.iloc[-1] - b.iloc[0]) / b.iloc[0] * 100
    return {
        "ticker_return_pct": round(ticker_return, 2),
        "benchmark_return_pct": round(benchmark_return, 2),
        "alpha_pct": round(ticker_return - benchmark_return, 2),
    }


async def fetch_price_history(ticker: str, start: date, end: date) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_fetch_sync, ticker, start, end))


async def calculate_returns(ticker: str, start: date, end: date) -> dict:
    rows = await fetch_price_history(ticker, start, end)
    if not rows:
        return {}
    start_price = rows[0]["close"]
    end_price = rows[-1]["close"]
    total_return = (end_price - start_price) / start_price * 100
    return {
        "ticker": ticker.upper(),
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "start_price": start_price,
        "end_price": end_price,
        "total_return_pct": round(total_return, 2),
    }


async def compare_to_benchmark(
    ticker: str, start: date, end: date, benchmark: str = "SPY"
) -> dict:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, partial(_benchmark_return_sync, ticker, benchmark, start, end)
    )
    return {"ticker": ticker.upper(), "benchmark": benchmark, **result}


def _fetch_valuation_sync(ticker: str) -> dict[str, Any]:
    info = yf.Ticker(ticker).info
    if not info or info.get("quoteType") is None:
        return {}

    def _round(v: Any, n: int = 2) -> Any:
        return round(v, n) if isinstance(v, float) else v

    # Analyst consensus: 1.0 = Strong Buy … 5.0 = Strong Sell
    rec_mean = info.get("recommendationMean")
    if rec_mean is not None:
        if rec_mean <= 1.5:
            analyst_consensus = "Strong Buy"
        elif rec_mean <= 2.5:
            analyst_consensus = "Buy"
        elif rec_mean <= 3.5:
            analyst_consensus = "Hold"
        elif rec_mean <= 4.5:
            analyst_consensus = "Sell"
        else:
            analyst_consensus = "Strong Sell"
    else:
        analyst_consensus = None

    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    target_price = info.get("targetMeanPrice")
    upside_pct = None
    if current_price and target_price:
        upside_pct = round((target_price - current_price) / current_price * 100, 1)

    return {
        "current_price": _round(current_price),
        "market_cap": info.get("marketCap"),
        "pe_ratio_trailing": _round(info.get("trailingPE")),
        "pe_ratio_forward": _round(info.get("forwardPE")),
        "pb_ratio": _round(info.get("priceToBook")),
        "eps_trailing": _round(info.get("trailingEps")),
        "eps_forward": _round(info.get("forwardEps")),
        "revenue_growth_yoy": _round(info.get("revenueGrowth")),
        "earnings_growth_yoy": _round(info.get("earningsGrowth")),
        "week_52_high": _round(info.get("fiftyTwoWeekHigh")),
        "week_52_low": _round(info.get("fiftyTwoWeekLow")),
        "analyst_target_price": _round(target_price),
        "analyst_upside_pct": upside_pct,
        "analyst_consensus": analyst_consensus,
        "dividend_yield_pct": _round((info.get("dividendYield") or 0) * 100),
        "beta": _round(info.get("beta")),
    }


async def get_stock_valuation(ticker: str) -> dict:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, partial(_fetch_valuation_sync, ticker))
    return {"ticker": ticker.upper(), **result}
