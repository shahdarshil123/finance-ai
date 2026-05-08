from datetime import date

from fastapi import APIRouter, HTTPException

from app.services.stock_service import (
    calculate_returns,
    compare_to_benchmark,
    fetch_price_history,
)

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/{ticker}/history")
async def get_stock_history(ticker: str, start: date, end: date):
    data = await fetch_price_history(ticker, start, end)
    if not data:
        raise HTTPException(status_code=404, detail=f"No price data found for {ticker}")
    return {"ticker": ticker.upper(), "data": data}


@router.get("/{ticker}/metrics")
async def get_stock_metrics(ticker: str, start: date, end: date):
    returns = await calculate_returns(ticker, start, end)
    if not returns:
        raise HTTPException(status_code=404, detail=f"No price data found for {ticker}")
    benchmark = await compare_to_benchmark(ticker, start, end)
    return {**returns, "benchmark_comparison": benchmark}
