import requests
import logging
import time
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from engine.config import DELTA_BASE_URL

logger = logging.getLogger(__name__)

CANDLES_ENDPOINT = '/v2/history/candles'
MAX_CANDLES_PER_REQUEST = 2000  # Delta Exchange hard limit per request
CHUNK_DELAY_MS = 250  # Delay between chunk requests (200-300ms range, using 250ms)
MAX_RETRIES = 3  # Maximum retries for rate limit errors
INITIAL_BACKOFF_SECONDS = 1  # Initial backoff time for exponential backoff

# Symbol mapping: UI-friendly symbols → Delta Exchange symbols
# NOTE: BTCUSD and ETHUSD are used EXACTLY as-is (NO _PERP suffix per requirements)
SYMBOL_MAP = {
    'BTCUSDT': 'BTCUSDT_PERP',  # Only non-standard symbols need mapping
    # BTCUSD and ETHUSD are passed through as-is
}

# Timeframe mapping: UI-friendly timeframes → Delta Exchange resolutions
TIMEFRAME_MAP = {
    '1MIN': '1m',
    '3MIN': '3m',  # Note: May not be supported by Delta, will be validated
    '5MIN': '5m',
    '15MIN': '15m',
    '30MIN': '30m',
    '1H': '1h',
    '2H': '2h',
    '4H': '4h',
    '6H': '6h',
    '1D': '1d',
    '1W': '1w',
    # Add more mappings as needed
    # Format: 'UI_TIMEFRAME': 'DELTA_RESOLUTION'
}


def map_symbol_to_delta(ui_symbol: str) -> str:
    """
    Map UI-friendly symbol to Delta Exchange symbol format.
    
    NOTE: BTCUSD and ETHUSD are used EXACTLY as-is (NO _PERP suffix per requirements)
    
    Args:
        ui_symbol: UI symbol (e.g., 'BTCUSD')
    
    Returns:
        Delta Exchange symbol (e.g., 'BTCUSD' for BTCUSD, 'BTCUSD_PERP' only if mapped)
        Returns original symbol if no mapping found
    """
    # BTCUSD and ETHUSD are passed through as-is (no _PERP suffix)
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
    elif timeframe_upper == '2H':
        return 90
    elif timeframe_upper == '4H':
        return 90
    elif timeframe_upper == '6H':
        return 120
    elif timeframe_upper == '1D':
        return 180
    elif timeframe_upper == '1W':
        return 365
    else:
        # Default fallback
        return 30


def _fetch_ohlcv_chunk(
    delta_symbol: str,
    delta_resolution: str,
    start: int,
    end: int,
    retry_count: int = 0
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Fetch a single chunk of OHLCV data from Delta Exchange (respects 2000 candle limit).
    
    Args:
        delta_symbol: Delta Exchange symbol (already mapped, e.g., 'BTCUSD')
        delta_resolution: Delta Exchange resolution (already mapped, e.g., '15m')
        start: Start timestamp (Unix seconds)
        end: End timestamp (Unix seconds)
        retry_count: Current retry attempt (for rate limit handling)
    
    Returns:
        Tuple of (candles_list, is_empty_response)
        - candles_list: List of candle dictionaries or empty list
        - is_empty_response: True if API returned empty array [] (no data exists), False otherwise
    """
    try:
        url = f"{DELTA_BASE_URL}{CANDLES_ENDPOINT}"
        
        params = {
            'symbol': delta_symbol,
            'resolution': delta_resolution,
            'start': start,
            'end': end
        }
        
        logger.debug(f"API chunk request: {url} with params: symbol={delta_symbol}, resolution={delta_resolution}, start={start}, end={end}")
        
        response = requests.get(url, params=params, timeout=30)
        
        # Handle HTTP 429 (Rate Limit)
        if response.status_code == 429:
            if retry_count < MAX_RETRIES:
                # Read X-RATE-LIMIT-RESET header if available
                reset_time = response.headers.get('X-RATE-LIMIT-RESET')
                if reset_time:
                    try:
                        reset_timestamp = int(reset_time)
                        wait_seconds = max(reset_timestamp - int(time.time()), 1)
                        logger.warning(f"Rate limit hit. Waiting {wait_seconds} seconds (from X-RATE-LIMIT-RESET header)")
                        time.sleep(wait_seconds)
                    except (ValueError, TypeError):
                        # Fallback to exponential backoff
                        wait_seconds = INITIAL_BACKOFF_SECONDS * (2 ** retry_count)
                        logger.warning(f"Rate limit hit. Waiting {wait_seconds} seconds (exponential backoff)")
                        time.sleep(wait_seconds)
                else:
                    # Exponential backoff if no reset header
                    wait_seconds = INITIAL_BACKOFF_SECONDS * (2 ** retry_count)
                    logger.warning(f"Rate limit hit. Waiting {wait_seconds} seconds (exponential backoff)")
                    time.sleep(wait_seconds)
                
                # Retry the request
                return _fetch_ohlcv_chunk(delta_symbol, delta_resolution, start, end, retry_count + 1)
            else:
                logger.error(f"Rate limit exceeded after {MAX_RETRIES} retries")
                return ([], False)  # Not an empty response, but an error
        
        # Raise for other HTTP errors
        response.raise_for_status()
        
        data = response.json()
        
        # Validate API response success (only if data is a dict)
        if isinstance(data, dict):
            if not data.get('success', True):
                error_msg = data.get('error', {}).get('message', 'Unknown error') if isinstance(data.get('error'), dict) else 'API returned success=false'
                logger.warning(f"API returned success=false: {error_msg}")
                return ([], False)  # Not an empty response, but an error
        
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
            logger.warning(f"API returned non-list candles format: {type(candles)}")
            return ([], False)
        
        # CRITICAL: Empty array [] means "NO DATA EXISTS" - stop fetching
        if len(candles) == 0:
            logger.info(f"API returned empty array [] - no data exists for this time range")
            return ([], True)  # is_empty_response = True
        
        # Format candles to standard structure
        formatted_candles = []
        for candle in candles:
            if not isinstance(candle, dict):
                logger.warning(f"Skipping invalid candle format (not a dict): {type(candle)}")
                continue
            
            # Validate required fields
            candle_time = candle.get('time')
            if candle_time is None:
                logger.warning(f"Skipping candle with missing 'time' field")
                continue
            
            formatted_candles.append({
                'time': candle_time,
                'open': candle.get('open'),
                'high': candle.get('high'),
                'low': candle.get('low'),
                'close': candle.get('close'),
                'volume': candle.get('volume')
            })
        
        logger.debug(f"Fetched {len(formatted_candles)} candles for chunk")
        return (formatted_candles, False)  # is_empty_response = False
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return ([], False)  # Not an empty response, but an error
    except Exception as e:
        logger.error(f"Unexpected error fetching OHLCV chunk: {e}", exc_info=True)
        return ([], False)  # Not an empty response, but an error


def fetch_ohlcv(
    symbol: str,
    resolution: str,
    start: int,
    end: int,
    auto_map: bool = True,
    lookback_days: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    PRODUCTION-GRADE historical candle fetcher for backtesting.
    
    Implements forward pagination with proper empty response handling and rate limit management.
    This function is ONLY for backtesting (not live trading).
    
    PAGINATION STRATEGY:
    - Uses forward pagination with start and end timestamps (Unix seconds)
    - Never requests more than 2000 candles in one call
    - Calculates chunk size as: chunk_seconds = resolution_seconds * 2000
    
    EMPTY RESPONSE HANDLING:
    - If API returns empty array [], treats it as "NO DATA EXISTS"
    - STOPS further requests immediately
    - Does NOT retry empty responses
    
    RATE LIMIT HANDLING:
    - Handles HTTP 429 with exponential backoff
    - Reads X-RATE-LIMIT-RESET header if available
    - Does NOT retry on empty []
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD' - NO _PERP suffix per requirements)
        resolution: Timeframe resolution (e.g., '15MIN' or '15m')
        start: Start timestamp (Unix timestamp in seconds)
        end: End timestamp (Unix timestamp in seconds)
        auto_map: If True, automatically maps UI symbols/timeframes to Delta format (default: True)
        lookback_days: Optional lookback window in days (if None, uses default based on timeframe)
    
    Returns:
        List of candle dictionaries with keys: time, open, high, low, close, volume
        Returns empty list on error or when no data exists
    
    Raises:
        None - All errors are handled internally, returns empty list (never crashes server)
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
    logger.info(f"Fetching historical candles for backtesting:")
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
            chunk_candles, is_empty = _fetch_ohlcv_chunk(delta_symbol, delta_resolution, actual_start, end)
            candle_count = len(chunk_candles) if chunk_candles else 0
            logger.info(f"Fetched {candle_count} candles for {delta_symbol} {delta_resolution} (UI: {original_symbol} {original_resolution})")
            return chunk_candles
        
        # Calculate chunk size: chunk_seconds = resolution_seconds * 2000
        chunk_duration_seconds = MAX_CANDLES_PER_REQUEST * timeframe_seconds
        
        logger.info(f"Chunk strategy: {MAX_CANDLES_PER_REQUEST} candles per chunk, {chunk_duration_seconds} seconds per chunk")
        
        # Fetch data in chunks using FORWARD pagination
        all_candles = []
        current_start = actual_start
        chunk_num = 0
        
        while current_start < end:
            chunk_num += 1
            chunk_end = min(current_start + chunk_duration_seconds, end)
            
            logger.info(f"Fetching chunk {chunk_num}: {datetime.fromtimestamp(current_start)} to {datetime.fromtimestamp(chunk_end)}")
            
            # Fetch chunk with rate limit handling
            chunk_candles, is_empty_response = _fetch_ohlcv_chunk(
                delta_symbol, 
                delta_resolution, 
                current_start, 
                chunk_end
            )
            
            # CRITICAL: Empty array [] means "NO DATA EXISTS" - STOP fetching
            if is_empty_response:
                logger.info(f"Chunk {chunk_num} returned empty array [] - no data exists. Stopping fetch loop.")
                break  # Stop further requests immediately
            
            # Append candles if we got data
            if chunk_candles:
                all_candles.extend(chunk_candles)
                logger.info(f"Chunk {chunk_num} returned {len(chunk_candles)} candles")
            else:
                # Empty list but not an empty response (could be an error)
                logger.warning(f"Chunk {chunk_num} returned no candles (not empty response, may be error)")
            
            # Move to next chunk: forward pagination
            current_start = chunk_end + 1  # +1 to avoid overlap
            
            # Add delay between chunks to avoid rate limits (200-300ms range)
            if current_start < end:
                time.sleep(CHUNK_DELAY_MS / 1000.0)
        
        # Deduplicate candles using candle time as unique key
        seen_times = set()
        unique_candles = []
        for candle in all_candles:
            candle_time = candle.get('time')
            if candle_time is not None and candle_time not in seen_times:
                seen_times.add(candle_time)
                unique_candles.append(candle)
        
        # Sort candles by ascending time before backtest
        unique_candles.sort(key=lambda c: c.get('time', 0))
        
        candle_count = len(unique_candles)
        logger.info(f"Total candles fetched: {candle_count} (from {chunk_num} chunks) for {delta_symbol} {delta_resolution} (UI: {original_symbol} {original_resolution})")
        
        if not unique_candles:
            logger.warning(f"No candles collected for {delta_symbol} {delta_resolution}")
            logger.warning(f"  Original request: symbol={original_symbol}, timeframe={original_resolution}")
            return []
        
        return unique_candles
        
    except requests.exceptions.RequestException as e:
        # Handle HTTP errors, network errors, timeout
        logger.error(f"API request failed: {e}")
        logger.error(f"  Requested: symbol={delta_symbol}, resolution={delta_resolution}")
        logger.error(f"  Original: symbol={original_symbol}, timeframe={original_resolution}")
        return []  # Never crash, return empty list
    except (KeyError, ValueError, TypeError) as e:
        # Handle JSON parsing errors, missing keys, type errors
        logger.error(f"API response parsing error: {e}")
        logger.error(f"  Requested: symbol={delta_symbol}, resolution={delta_resolution}")
        return []  # Never crash, return empty list
    except Exception as e:
        # Handle any other unexpected errors
        logger.error(f"Unexpected error fetching OHLCV: {e}", exc_info=True)
        return []  # Never crash, return empty list


def _get_timeframe_seconds(resolution: str) -> int:
    """
    Get timeframe duration in seconds.
    
    Args:
        resolution: Delta Exchange resolution (e.g., '15m', '1h', '1d', '1w')
    
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
    elif resolution_lower.endswith('w'):
        # Weeks
        try:
            weeks = int(resolution_lower.replace('w', ''))
            return weeks * 604800  # 7 days * 86400 seconds
        except ValueError:
            return 0
    else:
        return 0

