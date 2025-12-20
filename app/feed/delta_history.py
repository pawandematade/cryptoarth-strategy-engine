import requests
import logging
from typing import List, Dict, Optional, Any, Tuple
from app.config import DELTA_BASE_URL

logger = logging.getLogger(__name__)

CANDLES_ENDPOINT = '/v2/history/candles'
MAX_CANDLES = 2000

# Symbol mapping: UI-friendly symbols → Delta Exchange symbols
SYMBOL_MAP = {
    'BTCUSD': 'BTCUSD_PERP',
    'ETHUSD': 'ETHUSD_PERP',
    'BTCUSDT': 'BTCUSDT_PERP',
    # Add more mappings as needed
    # Format: 'UI_SYMBOL': 'DELTA_SYMBOL'
}

# Timeframe mapping: UI-friendly timeframes → Delta Exchange resolutions
TIMEFRAME_MAP = {
    '1MIN': '1m',
    '3MIN': '3m',  # Note: May not be supported by Delta, will be validated
    '5MIN': '5m',
    '15MIN': '15m',
    '30MIN': '30m',
    '1H': '1h',
    '4H': '4h',
    '1D': '1d',
    # Add more mappings as needed
    # Format: 'UI_TIMEFRAME': 'DELTA_RESOLUTION'
}


def map_symbol_to_delta(ui_symbol: str) -> str:
    """
    Map UI-friendly symbol to Delta Exchange symbol format.
    
    Args:
        ui_symbol: UI symbol (e.g., 'BTCUSD')
    
    Returns:
        Delta Exchange symbol (e.g., 'BTCUSD_PERP')
        Returns original symbol if no mapping found
    """
    mapped = SYMBOL_MAP.get(ui_symbol.upper(), ui_symbol.upper())
    if mapped != ui_symbol.upper():
        logger.debug(f"Symbol mapping: {ui_symbol} → {mapped}")
    return mapped


def map_timeframe_to_delta(ui_timeframe: str) -> str:
    """
    Map UI-friendly timeframe to Delta Exchange resolution format.
    
    Args:
        ui_timeframe: UI timeframe (e.g., '15MIN')
    
    Returns:
        Delta Exchange resolution (e.g., '15m')
        Returns original timeframe if no mapping found
    
    Raises:
        ValueError: If timeframe is not supported (e.g., '3MIN' may not be supported)
    """
    mapped = TIMEFRAME_MAP.get(ui_timeframe.upper())
    if not mapped:
        # If no mapping found, try to convert common formats
        if ui_timeframe.upper().endswith('MIN'):
            # Extract number and add 'm' suffix
            num = ui_timeframe.upper().replace('MIN', '').strip()
            mapped = f"{num}m"
            logger.warning(f"No explicit mapping for {ui_timeframe}, using derived: {mapped}")
        else:
            # Return as-is if no pattern matches
            mapped = ui_timeframe.upper()
            logger.warning(f"No mapping found for timeframe: {ui_timeframe}, using as-is: {mapped}")
    else:
        logger.debug(f"Timeframe mapping: {ui_timeframe} → {mapped}")
    
    return mapped


def fetch_ohlcv(
    symbol: str,
    resolution: str,
    start: int,
    end: int,
    auto_map: bool = True
) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV (candlestick) data from Delta Exchange historical API.
    
    This function automatically maps UI-friendly symbols and timeframes to Delta Exchange format.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD' or 'BTCUSD_PERP')
        resolution: Timeframe resolution (e.g., '15MIN' or '15m')
        start: Start timestamp (Unix timestamp in seconds)
        end: End timestamp (Unix timestamp in seconds)
        auto_map: If True, automatically maps UI symbols/timeframes to Delta format (default: True)
    
    Returns:
        List of candle dictionaries with keys: time, open, high, low, close, volume
        Returns empty list on error or empty result
    
    Raises:
        None - All errors are handled internally, returns empty list
    """
    # Store original values for logging
    original_symbol = symbol
    original_resolution = resolution
    
    # Map UI values to Delta Exchange format
    if auto_map:
        delta_symbol = map_symbol_to_delta(symbol)
        delta_resolution = map_timeframe_to_delta(resolution)
    else:
        delta_symbol = symbol
        delta_resolution = resolution
    
    # Log mapping details
    logger.info(f"Fetching OHLCV from Delta Exchange:")
    logger.info(f"  Original: symbol={original_symbol}, timeframe={original_resolution}")
    logger.info(f"  Mapped: symbol={delta_symbol}, resolution={delta_resolution}")
    
    try:
        url = f"{DELTA_BASE_URL}{CANDLES_ENDPOINT}"
        
        params = {
            'symbol': delta_symbol,
            'resolution': delta_resolution,
            'start': start,
            'end': end
        }
        
        logger.debug(f"Delta Exchange API request: {url} with params: {params}")
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Validate API response success (only if data is a dict)
        if isinstance(data, dict):
            if not data.get('success', True):  # Default to True if 'success' key doesn't exist
                error_msg = data.get('error', {}).get('message', 'Unknown error') if isinstance(data.get('error'), dict) else 'API returned success=false'
                logger.warning(f"Delta Exchange API returned success=false: {error_msg}")
                logger.warning(f"  Requested: symbol={delta_symbol}, resolution={delta_resolution}")
                return []
        
        # SAFELY extract candles from response - handle ALL possible formats
        candles = []
        
        if isinstance(data, list):
            # Case 1: Response is a list directly (candles array)
            candles = data
            logger.debug(f"Delta Exchange returned list directly (not wrapped in dict)")
        elif isinstance(data, dict):
            # Case 2: Response is a dict - check multiple possible locations
            result = data.get('result')
            
            if isinstance(result, list):
                # Case 2a: result is a list (candles array)
                candles = result
                logger.debug(f"Delta Exchange returned candles in data['result'] (list)")
            elif isinstance(result, dict):
                # Case 2b: result is a dict, check for 'candles' key
                candles = result.get('candles', [])
                logger.debug(f"Delta Exchange returned candles in data['result']['candles']")
            else:
                # Case 2c: result doesn't exist or is None, check for 'candles' at top level
                candles = data.get('candles', [])
                if candles:
                    logger.debug(f"Delta Exchange returned candles in data['candles'] (top level)")
                else:
                    logger.debug(f"Delta Exchange response structure: data keys = {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        else:
            # Case 3: Unexpected response type
            logger.warning(f"Delta Exchange returned unexpected response type: {type(data)}")
            logger.warning(f"  Response: {str(data)[:200]}...")  # Log first 200 chars
            return []
        
        # Ensure candles is a list (safety check)
        if not isinstance(candles, list):
            logger.warning(f"Delta Exchange returned candles as non-list type: {type(candles)}")
            return []
        
        candle_count = len(candles) if candles else 0
        logger.info(f"Delta Exchange returned {candle_count} candles for {delta_symbol} {delta_resolution} (UI: {original_symbol} {original_resolution})")
        
        if not candles:
            logger.warning(f"No candles returned from Delta Exchange for {delta_symbol} {delta_resolution}")
            logger.warning(f"  Original request: symbol={original_symbol}, timeframe={original_resolution}")
            return []
        
        # Format candles to standard structure
        formatted_candles = []
        for candle in candles:
            # Safety check: ensure candle is a dict before calling .get()
            if not isinstance(candle, dict):
                logger.warning(f"Skipping invalid candle format (not a dict): {type(candle)}")
                continue
            
            formatted_candles.append({
                'time': candle.get('time'),
                'open': candle.get('open'),
                'high': candle.get('high'),
                'low': candle.get('low'),
                'close': candle.get('close'),
                'volume': candle.get('volume')
            })
        
        logger.info(f"Successfully formatted {len(formatted_candles)} candles")
        return formatted_candles
        
    except requests.exceptions.RequestException as e:
        # Handle HTTP errors, network errors, timeout
        logger.error(f"Delta Exchange API request failed: {e}")
        logger.error(f"  Requested: symbol={delta_symbol}, resolution={delta_resolution}")
        logger.error(f"  Original: symbol={original_symbol}, timeframe={original_resolution}")
        return []
    except (KeyError, ValueError, TypeError) as e:
        # Handle JSON parsing errors, missing keys, type errors
        logger.error(f"Delta Exchange API response parsing error: {e}")
        logger.error(f"  Requested: symbol={delta_symbol}, resolution={delta_resolution}")
        return []
    except Exception as e:
        # Handle any other unexpected errors
        logger.error(f"Unexpected error fetching OHLCV from Delta Exchange: {e}", exc_info=True)
        return []

