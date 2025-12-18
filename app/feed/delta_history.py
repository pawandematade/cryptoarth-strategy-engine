import requests
from typing import List, Dict, Optional, Any
from app.config import DELTA_BASE_URL

CANDLES_ENDPOINT = '/v2/history/candles'
MAX_CANDLES = 2000


def fetch_ohlcv(
    symbol: str,
    resolution: str,
    start: int,
    end: int
) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV (candlestick) data from Delta Exchange historical API.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
        resolution: Timeframe resolution (e.g., '1', '5', '15', '60', '240', '1D')
        start: Start timestamp (Unix timestamp in seconds)
        end: End timestamp (Unix timestamp in seconds)
    
    Returns:
        List of candle dictionaries with keys: time, open, high, low, close, volume
        Returns empty list on error or empty result
    
    Raises:
        None - All errors are handled internally, returns empty list
    """
    try:
        url = f"{DELTA_BASE_URL}{CANDLES_ENDPOINT}"
        
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'start': start,
            'end': end
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Validate API response success
        if not data.get('success', False):
            return []
        
        # Extract candles from response
        result = data.get('result', {})
        candles = result.get('candles', [])
        
        if not candles:
            return []
        
        # Format candles to standard structure
        formatted_candles = []
        for candle in candles:
            formatted_candles.append({
                'time': candle.get('time'),
                'open': candle.get('open'),
                'high': candle.get('high'),
                'low': candle.get('low'),
                'close': candle.get('close'),
                'volume': candle.get('volume')
            })
        
        return formatted_candles
        
    except requests.exceptions.RequestException:
        # Handle HTTP errors, network errors, timeout
        return []
    except (KeyError, ValueError, TypeError):
        # Handle JSON parsing errors, missing keys, type errors
        return []
    except Exception:
        # Handle any other unexpected errors
        return []

