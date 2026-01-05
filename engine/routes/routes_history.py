from fastapi import APIRouter, Query, HTTPException
from core.feed.delta_history import fetch_ohlcv

router = APIRouter()


@router.get("/history/candles")
def get_candles(
    symbol: str = Query(..., description="Trading symbol (e.g., BTCUSD)"),
    resolution: str = Query(..., description="Timeframe resolution (e.g., 1, 5, 15, 60, 240, 1D)"),
    start: int = Query(..., description="Start timestamp (Unix seconds)"),
    end: int = Query(..., description="End timestamp (Unix seconds)")
):
    """
    Get historical OHLCV candle data from Delta Exchange.
    
    Returns:
        dict: JSON with symbol, resolution, and candles array
    """
    # Validate parameters
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol is required")
    
    if not resolution or not resolution.strip():
        raise HTTPException(status_code=400, detail="Resolution is required")
    
    if start <= 0 or end <= 0:
        raise HTTPException(status_code=400, detail="Start and end must be positive integers")
    
    if start >= end:
        raise HTTPException(status_code=400, detail="Start timestamp must be less than end timestamp")
    
    # Fetch candles
    candles = fetch_ohlcv(symbol.strip(), resolution.strip(), start, end)
    
    return {
        "symbol": symbol.strip(),
        "resolution": resolution.strip(),
        "candles": candles
    }

