import requests
import logging
import time
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from app.config import DELTA_BASE_URL

logger = logging.getLogger(__name__)

CANDLES_ENDPOINT = '/v2/history/candles'
MAX_CANDLES = 2000  # Delta Exchange limit per request
CHUNK_DELAY_MS = 150  # Delay between chunk requests (ms)

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


def get_default_lookback_days(timeframe: str) -> int:
    """
    Get default lookback days based on timeframe.
    
    Args:
        timeframe: UI timeframe (e.g., '15MIN', '1H')
    
    Returns:
        Default lookback days for the timeframe
    """
    timeframe_upper = timeframe.upper()
    
    # Default lookback days based on timeframe
    if timeframe_upper in ['1MIN', '3MIN', '5MIN']:
        return 7
    elif timeframe_upper == '15MIN':
        return 15
    elif timeframe_upper == '30MIN':
        return 30
    elif timeframe_upper == '1H':
        return 60
    elif timeframe_upper == '4H':
        return 90
    elif timeframe_upper == '1D':
        return 180
    else:
        # Default fallback
        return 30


def _fetch_ohlcv_chunk(
    delta_symbol: str,
    delta_resolution: str,
    start: int,
    end: int
) -> List[Dict[str, Any]]:
    """
    Fetch a single chunk of OHLCV data from Delta Exchange (respects 2000 candle limit).
    
    Args:
        delta_symbol: Delta Exchange symbol (already mapped)
        delta_resolution: Delta Exchange resolution (already mapped)
        start: Start timestamp (Unix seconds)
        end: End timestamp (Unix seconds)
    
    Returns:
        List of candle dictionaries or empty list on error
    """
    try:
        url = f"{DELTA_BASE_URL}{CANDLES_ENDPOINT}"
        
        params = {
            'symbol': delta_symbol,
            'resolution': delta_resolution,
            'start': start,
            'end': end
        }
        
        logger.debug(f"Delta Exchange API chunk request: {url} with params: {params}")
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Validate API response success (only if data is a dict)
        if isinstance(data, dict):
            if not data.get('success', True):
                error_msg = data.get('error', {}).get('message', 'Unknown error') if isinstance(data.get('error'), dict) else 'API returned success=false'
                logger.warning(f"Delta Exchange API returned success=false: {error_msg}")
                return []
        
        # SAFELY extract candles from response - handle ALL possible formats
        candles = []
        
        if isinstance(data, list):
            candles = data
        elif isinstance(data, dict):
            result = data.get('result')
            if isinstance(result, list):
                candles = result
            elif isinstance(result, dict):
                candles = result.get('candles', [])
            else:
                candles = data.get('candles', [])
        
        # Ensure candles is a list
        if not isinstance(candles, list):
            return []
        
        # Format candles to standard structure
        formatted_candles = []
        for candle in candles:
            if not isinstance(candle, dict):
                continue
            formatted_candles.append({
                'time': candle.get('time'),
                'open': candle.get('open'),
                'high': candle.get('high'),
                'low': candle.get('low'),
                'close': candle.get('close'),
                'volume': candle.get('volume')
            })
        
        return formatted_candles
        
    except Exception as e:
        logger.error(f"Error fetching OHLCV chunk: {e}")
        return []


def fetch_ohlcv(
    symbol: str,
    resolution: str,
    start: int,
    end: int,
    auto_map: bool = True,
    lookback_days: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV (candlestick) data from Delta Exchange historical API with chunked fetching.
    
    This function automatically maps UI-friendly symbols and timeframes to Delta Exchange format.
    It respects the 2000 candle limit per request by fetching data in chunks.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD' or 'BTCUSD_PERP')
        resolution: Timeframe resolution (e.g., '15MIN' or '15m')
        start: Start timestamp (Unix timestamp in seconds)
        end: End timestamp (Unix timestamp in seconds)
        auto_map: If True, automatically maps UI symbols/timeframes to Delta format (default: True)
        lookback_days: Optional lookback window in days (if None, uses default based on timeframe)
    
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
    
    # Calculate lookback window if not provided
    if lookback_days is None:
        lookback_days = get_default_lookback_days(resolution)
    
    # Adjust start time based on lookback_days (never request unlimited data)
    end_time = datetime.fromtimestamp(end)
    start_time = end_time - timedelta(days=lookback_days)
    adjusted_start = int(start_time.timestamp())
    
    # Use the more restrictive start time (user-provided or calculated)
    actual_start = max(start, adjusted_start)
    
    # Log mapping details
    logger.info(f"Fetching OHLCV from Delta Exchange:")
    logger.info(f"  Original: symbol={original_symbol}, timeframe={original_resolution}")
    logger.info(f"  Mapped: symbol={delta_symbol}, resolution={delta_resolution}")
    logger.info(f"  Lookback window: {lookback_days} days")
    logger.info(f"  Time range: {datetime.fromtimestamp(actual_start)} to {datetime.fromtimestamp(end)}")
    
    try:
        # Calculate timeframe duration in seconds for chunking
        timeframe_seconds = _get_timeframe_seconds(delta_resolution)
        if timeframe_seconds == 0:
            logger.warning(f"Unknown timeframe duration for {delta_resolution}, using single request")
            # Fallback to single request
            candles = _fetch_ohlcv_chunk(delta_symbol, delta_resolution, actual_start, end)
            candle_count = len(candles) if candles else 0
            logger.info(f"Delta Exchange returned {candle_count} candles for {delta_symbol} {delta_resolution} (UI: {original_symbol} {original_resolution})")
            return candles
        
        # Calculate max candles per chunk (slightly less than 2000 for safety)
        max_candles_per_chunk = MAX_CANDLES - 50  # Safety margin
        chunk_duration_seconds = max_candles_per_chunk * timeframe_seconds
        
        # Fetch data in chunks
        all_candles = []
        current_start = actual_start
        chunk_num = 0
        
        while current_start < end:
            chunk_num += 1
            chunk_end = min(current_start + chunk_duration_seconds, end)
            
            logger.debug(f"Fetching chunk {chunk_num}: {datetime.fromtimestamp(current_start)} to {datetime.fromtimestamp(chunk_end)}")
            
            chunk_candles = _fetch_ohlcv_chunk(delta_symbol, delta_resolution, current_start, chunk_end)
            
            if chunk_candles:
                all_candles.extend(chunk_candles)
                logger.debug(f"Chunk {chunk_num} returned {len(chunk_candles)} candles")
            else:
                logger.warning(f"Chunk {chunk_num} returned no candles")
            
            # Move to next chunk
            current_start = chunk_end + 1  # +1 to avoid overlap
            
            # Add delay between chunks to avoid rate limits
            if current_start < end:
                time.sleep(CHUNK_DELAY_MS / 1000.0)
        
        # Remove duplicates and sort by time
        seen_times = set()
        unique_candles = []
        for candle in all_candles:
            candle_time = candle.get('time')
            if candle_time and candle_time not in seen_times:
                seen_times.add(candle_time)
                unique_candles.append(candle)
        
        # Sort by time
        unique_candles.sort(key=lambda c: c.get('time', 0))
        
        candle_count = len(unique_candles)
        logger.info(f"Delta Exchange returned {candle_count} candles (from {chunk_num} chunks) for {delta_symbol} {delta_resolution} (UI: {original_symbol} {original_resolution})")
        
        if not unique_candles:
            logger.warning(f"No candles returned from Delta Exchange for {delta_symbol} {delta_resolution}")
            logger.warning(f"  Original request: symbol={original_symbol}, timeframe={original_resolution}")
            return []
        
        return unique_candles
        
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


def _get_timeframe_seconds(resolution: str) -> int:
    """
    Get timeframe duration in seconds.
    
    Args:
        resolution: Delta Exchange resolution (e.g., '15m', '1h', '1d')
    
    Returns:
        Duration in seconds, or 0 if unknown
    """
    resolution_lower = resolution.lower()
    
    if resolution_lower.endswith('m'):
        # Minutes
        try:
            minutes = int(resolution_lower.replace('m', ''))
            return minutes * 60
        except ValueError:
            return 0
    elif resolution_lower.endswith('h'):
        # Hours
        try:
            hours = int(resolution_lower.replace('h', ''))
            return hours * 3600
        except ValueError:
            return 0
    elif resolution_lower.endswith('d'):
        # Days
        try:
            days = int(resolution_lower.replace('d', ''))
            return days * 86400
        except ValueError:
            return 0
    else:
        return 0

