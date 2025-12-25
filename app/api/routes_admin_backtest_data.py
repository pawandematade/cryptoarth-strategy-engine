"""
Admin Backtest Data Management API Routes
Admin-only endpoints for managing backtest candle data in aibacktest_<SYMBOL> tables.

CRITICAL: Uses backtest_candle_storage.py service - NO direct DB access.
"""
from fastapi import APIRouter, HTTPException, status, Query, Body, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from app.services.backtest_candle_storage import (
    create_table_if_not_exists,
    insert_candles,
    get_candles,
    get_table_name,
    table_exists,
    delete_candles
)
from app.feed.delta_history import fetch_ohlcv, _get_timeframe_seconds

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum date range (30 days in seconds)
MAX_RANGE_SECONDS = 30 * 24 * 60 * 60


# Request/Response Models
class InsertBacktestDataRequest(BaseModel):
    """Request model for inserting backtest data"""
    symbol: str = Field(..., description="Trading symbol (e.g., 'BTCUSD')")
    from_time: int = Field(..., description="Start timestamp (Unix seconds)")
    to_time: int = Field(..., description="End timestamp (Unix seconds)")
    overwrite: bool = Field(default=False, description="If True, replace existing candles")
    timeframe: str = Field(default="1h", description="Timeframe for candles (e.g., '1h', '15m')")
    dry_run: bool = Field(default=False, description="If True, validate and count only, do NOT insert")
    
    @validator('symbol')
    def validate_symbol(cls, v):
        """Validate symbol format"""
        if not v or not isinstance(v, str):
            raise ValueError("Symbol must be a non-empty string")
        # Sanitize: uppercase, remove special chars
        sanitized = v.upper().replace('-', '').replace('_', '').replace(' ', '')
        if not sanitized:
            raise ValueError("Invalid symbol format")
        return sanitized
    
    @validator('from_time', 'to_time')
    def validate_timestamp(cls, v):
        """Validate timestamp"""
        if not isinstance(v, int) or v <= 0:
            raise ValueError("Timestamp must be a positive integer")
        return v
    
    @validator('to_time')
    def validate_time_range(cls, v, values):
        """Validate time range"""
        if 'from_time' in values and v < values['from_time']:
            raise ValueError("to_time must be >= from_time")
        if 'from_time' in values:
            range_seconds = v - values['from_time']
            if range_seconds > MAX_RANGE_SECONDS:
                raise ValueError(f"Date range exceeds maximum ({MAX_RANGE_SECONDS // (24 * 60 * 60)} days)")
        return v


class DeleteBacktestDataRequest(BaseModel):
    """Request model for deleting backtest data"""
    symbol: str = Field(..., description="Trading symbol (e.g., 'BTCUSD')")
    from_time: int = Field(..., description="Start timestamp (Unix seconds)")
    to_time: int = Field(..., description="End timestamp (Unix seconds)")
    
    @validator('symbol')
    def validate_symbol(cls, v):
        """Validate symbol format"""
        if not v or not isinstance(v, str):
            raise ValueError("Symbol must be a non-empty string")
        sanitized = v.upper().replace('-', '').replace('_', '').replace(' ', '')
        if not sanitized:
            raise ValueError("Invalid symbol format")
        return sanitized
    
    @validator('from_time', 'to_time')
    def validate_timestamp(cls, v):
        """Validate timestamp"""
        if not isinstance(v, int) or v <= 0:
            raise ValueError("Timestamp must be a positive integer")
        return v
    
    @validator('to_time')
    def validate_time_range(cls, v, values):
        """Validate time range"""
        if 'from_time' in values and v < values['from_time']:
            raise ValueError("to_time must be >= from_time")
        if 'from_time' in values:
            range_seconds = v - values['from_time']
            if range_seconds > MAX_RANGE_SECONDS:
                raise ValueError(f"Date range exceeds maximum ({MAX_RANGE_SECONDS // (24 * 60 * 60)} days)")
        return v


@router.post("/admin/backtest-data/insert")
async def insert_backtest_data(
    request: InsertBacktestDataRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Admin endpoint to insert backtest candle data for a date range.
    
    CRITICAL: Uses backtest_candle_storage service - NO direct DB access.
    
    Args:
        request: InsertBacktestDataRequest with symbol, from_time, to_time, overwrite, timeframe, dry_run
        authorization: Authorization header (admin required)
    
    Returns:
        JSONResponse with success status, inserted count, skipped count
    """
    # Admin authentication check
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # TODO: Add admin role verification here
    # For now, any authenticated user can access - should be restricted to admin users only
    
    try:
        symbol = request.symbol
        from_time = request.from_time
        to_time = request.to_time
        overwrite = request.overwrite
        timeframe = request.timeframe
        
        logger.info(
            f"[Admin] Insert backtest data request: symbol={symbol}, "
            f"from={datetime.fromtimestamp(from_time)}, to={datetime.fromtimestamp(to_time)}, "
            f"overwrite={overwrite}, timeframe={timeframe}"
        )
        
        # Ensure table exists
        if not create_table_if_not_exists(symbol):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create table for symbol {symbol}"
            )
        
        # Fetch candle data from Delta Exchange
        logger.info(f"[Admin] Fetching candles from Delta Exchange: {symbol} {timeframe}")
        candles = fetch_ohlcv(
            symbol=symbol,
            resolution=timeframe,
            start=from_time,
            end=to_time,
            auto_map=True
        )
        
        if not candles:
            logger.warning(f"[Admin] No candles fetched from Delta Exchange for {symbol}")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "symbol": symbol,
                    "inserted": 0,
                    "skipped": 0,
                    "message": "No candles available for the specified date range"
                }
            )
        
        logger.info(f"[Admin] Fetched {len(candles)} candles from Delta Exchange")
        
        # DRY RUN MODE: Only validate and count, do NOT insert
        if request.dry_run:
            # If overwrite=False, check existing candles and filter out duplicates
            if not overwrite:
                existing_candles = get_candles(symbol, start_time=from_time, end_time=to_time)
                existing_times = {candle['time'] for candle in existing_candles}
                
                # Filter out candles that already exist
                new_candles = [c for c in candles if c['time'] not in existing_times]
                skipped_count = len(candles) - len(new_candles)
                expected_insert_count = len(new_candles)
            else:
                expected_insert_count = len(candles)
                skipped_count = 0
            
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "symbol": symbol,
                    "dry_run": True,
                    "expected_insert": expected_insert_count,
                    "skipped": skipped_count,
                    "total_fetched": len(candles),
                    "message": f"Dry run: Would insert {expected_insert_count} candles, skip {skipped_count}"
                }
            )
        
        # NORMAL MODE: Insert candles
        # If overwrite=False, check existing candles and filter out duplicates
        if not overwrite:
            existing_candles = get_candles(symbol, start_time=from_time, end_time=to_time)
            existing_times = {candle['time'] for candle in existing_candles}
            
            # Filter out candles that already exist
            new_candles = [c for c in candles if c['time'] not in existing_times]
            skipped_count = len(candles) - len(new_candles)
            
            if new_candles:
                inserted_count = insert_candles(symbol, new_candles)
            else:
                inserted_count = 0
                logger.info(f"[Admin] All {len(candles)} candles already exist, skipping insert")
        else:
            # Overwrite mode: insert all candles (ON DUPLICATE KEY UPDATE handles replacement)
            inserted_count = insert_candles(symbol, candles)
            skipped_count = 0
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "symbol": symbol,
                "inserted": inserted_count,
                "skipped": skipped_count,
                "message": "Backtest data inserted successfully"
            }
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"[Admin] Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[Admin] Error inserting backtest data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/admin/backtest-data/status")
async def check_backtest_data_status(
    symbol: str = Query(..., description="Trading symbol (e.g., 'BTCUSD')"),
    from_time: int = Query(..., description="Start timestamp (Unix seconds)"),
    to_time: int = Query(..., description="End timestamp (Unix seconds)"),
    timeframe: str = Query(default="1h", description="Timeframe for candles (e.g., '1h', '15m')"),
    authorization: Optional[str] = Header(None)
):
    """
    Admin endpoint to check backtest data availability and identify missing days.
    
    CRITICAL: Uses backtest_candle_storage service - NO direct DB access.
    Calculates missing times based on expected candle interval.
    
    Args:
        symbol: Trading symbol
        from_time: Start timestamp (Unix seconds)
        to_time: End timestamp (Unix seconds)
        timeframe: Timeframe for candles (e.g., '1h', '15m') - used to calculate expected interval
        authorization: Authorization header (admin required)
    
    Returns:
        JSONResponse with available_times and missing_times
    """
    # Admin authentication check
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # TODO: Add admin role verification here
    # For now, any authenticated user can access - should be restricted to admin users only
    
    try:
        # Validate inputs
        if not symbol or not isinstance(symbol, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Symbol must be a non-empty string"
            )
        
        symbol = symbol.upper().replace('-', '').replace('_', '').replace(' ', '')
        
        if not isinstance(from_time, int) or from_time <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="from_time must be a positive integer"
            )
        
        if not isinstance(to_time, int) or to_time <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="to_time must be a positive integer"
            )
        
        if to_time < from_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="to_time must be >= from_time"
            )
        
        range_seconds = to_time - from_time
        if range_seconds > MAX_RANGE_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Date range exceeds maximum ({MAX_RANGE_SECONDS // (24 * 60 * 60)} days)"
            )
        
        logger.info(
            f"[Admin] Check data status: symbol={symbol}, "
            f"from={datetime.fromtimestamp(from_time)}, to={datetime.fromtimestamp(to_time)}"
        )
        
        # Check if table exists
        table_name = get_table_name(symbol)
        if not table_exists(table_name):
            logger.warning(f"[Admin] Table {table_name} does not exist")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "symbol": symbol,
                    "available_times": [],
                    "missing_times": [],
                    "message": f"Table {table_name} does not exist"
                }
            )
        
        # Get existing candles
        existing_candles = get_candles(symbol, start_time=from_time, end_time=to_time)
        available_times = {candle['time'] for candle in existing_candles}
        
        # Calculate expected candle interval from timeframe
        # Map timeframe to Delta Exchange resolution format
        timeframe_map = {
            '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
            '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h', '8h': '8h', '12h': '12h',
            '1d': '1d', '3d': '3d', '1w': '1w', '1M': '1M'
        }
        delta_resolution = timeframe_map.get(timeframe.lower(), timeframe.lower())
        interval_seconds = _get_timeframe_seconds(delta_resolution)
        
        # Calculate all expected timestamps in the range
        expected_times = set()
        if interval_seconds > 0:
            current_time = from_time
            while current_time <= to_time:
                expected_times.add(current_time)
                current_time += interval_seconds
        else:
            # If interval cannot be determined, use available times as expected
            logger.warning(f"[Admin] Cannot determine interval for timeframe {timeframe}, using available times only")
            expected_times = available_times.copy()
        
        # Calculate missing times (expected but not available)
        missing_times = sorted(expected_times - available_times)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "symbol": symbol,
                "timeframe": timeframe,
                "interval_seconds": interval_seconds,
                "available_times": sorted(available_times),
                "missing_times": missing_times,
                "total_available": len(available_times),
                "total_expected": len(expected_times),
                "total_missing": len(missing_times),
                "coverage_percent": round((len(available_times) / len(expected_times) * 100) if expected_times else 0, 2),
                "message": f"Found {len(available_times)}/{len(expected_times)} candles ({len(missing_times)} missing)"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Admin] Error checking backtest data status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.delete("/admin/backtest-data/delete")
async def delete_backtest_data(
    request: DeleteBacktestDataRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Admin endpoint to delete backtest candle data for a date range.
    
    CRITICAL: Uses backtest_candle_storage service - NO direct DB access.
    Deletes only matching candles - does NOT drop table.
    
    Args:
        request: DeleteBacktestDataRequest with symbol, from_time, to_time
        authorization: Authorization header (admin required)
    
    Returns:
        JSONResponse with success status and deleted count
    """
    # Admin authentication check
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # TODO: Add admin role verification here
    # For now, any authenticated user can access - should be restricted to admin users only
    
    try:
        symbol = request.symbol
        from_time = request.from_time
        to_time = request.to_time
        
        logger.info(
            f"[Admin] Delete backtest data request: symbol={symbol}, "
            f"from={datetime.fromtimestamp(from_time)}, to={datetime.fromtimestamp(to_time)}"
        )
        
        # Use service function for delete (transaction-safe, no direct DB access)
        deleted_count = delete_candles(symbol, start_time=from_time, end_time=to_time)
        
        if deleted_count == 0:
            table_name = get_table_name(symbol)
            if not table_exists(table_name):
                logger.warning(f"[Admin] Table {table_name} does not exist, nothing to delete")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "success": True,
                        "symbol": symbol,
                        "deleted": 0,
                        "message": f"Table {table_name} does not exist"
                    }
                )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "symbol": symbol,
                "deleted": deleted_count,
                "message": f"Deleted {deleted_count} candles successfully"
            }
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"[Admin] Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[Admin] Error deleting backtest data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

