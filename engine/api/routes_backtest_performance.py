"""
Backtest Performance Read-Only APIs

CRITICAL: These APIs ONLY READ from database tables created in Step-4.
NO computation, NO inserts, NO updates.

APIs:
1. GET /auth/strategy/{strategy_id}/performance/summary - Latest backtest summary
2. GET /auth/strategy/{strategy_id}/performance/daily - Daily performance chart data
3. GET /auth/strategy/{strategy_id}/performance/trades - Trade-by-trade details (paginated)
"""

from fastapi import APIRouter, HTTPException, status, Query, Depends, Header
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, asc
from common.db import get_db
from engine.models import (
    Strategy,
    StrategyBacktestSummary,
    StrategyBacktestDaily,
    StrategyBacktestTrades,
    User
)
from engine.core.services.user_sync_service import get_or_sync_user
import logging
from datetime import datetime
import requests

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_strategy_access(
    db: Session,
    strategy_id: int,
    authorization: Optional[str] = None
) -> Strategy:
    """
    Verify that strategy exists and user has access.
    
    Access is granted if:
    - User owns the strategy (strategy.user_id == user.external_user_id), OR
    - User is vendor (user.is_vendor == True), OR
    - User is admin (check via auth backend or is_admin field if exists)
    
    Args:
        db: Database session
        strategy_id: Strategy ID
        authorization: Authorization header (Bearer token)
    
    Returns:
        Strategy object
    
    Raises:
        HTTPException: If strategy not found, access denied, or auth backend unavailable
    """
    # 1. Verify strategy exists
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy with ID {strategy_id} not found"
        )
    
    # 2. Verify authorization header provided
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # 3. Get user from auth backend and sync to local DB
    try:
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate user"
            )
    except requests.exceptions.RequestException as e:
        # Auth backend unavailable - FAIL FAST
        logger.error(f"Auth backend unavailable: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth backend unavailable. Cannot verify access without user authentication."
        )
    except ValueError as e:
        # User not found or invalid token
        logger.warning(f"User authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authorization token"
        )
    
    # 4. Check access: owner, vendor, or admin
    has_access = False
    
    # Check if user owns the strategy - Business tables store external_user_id in user_id column
    if strategy.user_id == user.external_user_id:
        has_access = True
        logger.debug(f"User {user.external_user_id} owns strategy {strategy_id}")
    
    # Check if user is vendor
    if not has_access and user.is_vendor:
        has_access = True
        logger.debug(f"User {user.id} is vendor, granted access to strategy {strategy_id}")
    
    # Check if user is admin (via auth backend user data)
    if not has_access:
        try:
            # Check raw_user_json for admin role
            raw_user_data = user.raw_user_json
            if raw_user_data:
                # Check for admin role in user data (common patterns)
                is_admin = (
                    raw_user_data.get("is_admin") == True or
                    raw_user_data.get("is_staff") == True or
                    raw_user_data.get("role") == "admin" or
                    raw_user_data.get("user_type") == "admin"
                )
                if is_admin:
                    has_access = True
                    logger.debug(f"User {user.id} is admin, granted access to strategy {strategy_id}")
        except Exception as e:
            logger.debug(f"Could not check admin status from user data: {e}")
    
    # 5. Deny access if none of the conditions met
    if not has_access:
        logger.warning(f"Access denied: User {user.id} does not have access to strategy {strategy_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this strategy"
        )
    
    return strategy


def _verify_backtest_run_id(
    db: Session,
    strategy_id: int,
    backtest_run_id: str
) -> bool:
    """
    Verify that backtest_run_id belongs to the given strategy.
    
    Args:
        db: Database session
        strategy_id: Strategy ID
        backtest_run_id: Backtest run ID to verify
    
    Returns:
        True if valid, False otherwise
    """
    # Check if any record exists with this strategy_id and backtest_run_id
    summary = db.query(StrategyBacktestSummary).filter(
        and_(
            StrategyBacktestSummary.strategy_id == strategy_id,
            StrategyBacktestSummary.backtest_run_id == backtest_run_id
        )
    ).first()
    
    return summary is not None


@router.get("/auth/strategy/{strategy_id}/performance/summary")
def get_strategy_performance_summary(
    strategy_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get latest backtest performance summary for a strategy.
    
    Reads from: strategy_backtest_summary
    Returns: Single latest row ordered by created_at DESC
    
    Args:
        strategy_id: Strategy ID
        db: Database session
    
    Returns:
        {
            "success": true,
            "data": {
                "strategy_id": 123,
                "symbol": "BTCUSD",
                "timeframe": "1h",
                "net_pnl": 1200.45,
                "max_drawdown": -320.10,
                "win_rate": 0.62,
                "profit_factor": 1.85,
                "total_trades": 140,
                "backtest_run_id": "uuid"
            }
        }
    """
    try:
        # Verify strategy access (includes user authentication and ownership checks)
        _verify_strategy_access(db, strategy_id, authorization)
        
        # Fetch latest backtest summary
        summary = db.query(StrategyBacktestSummary).filter(
            StrategyBacktestSummary.strategy_id == strategy_id
        ).order_by(desc(StrategyBacktestSummary.created_at)).first()
        
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No backtest data found for strategy {strategy_id}"
            )
        
        # Format response
        return {
            "success": True,
            "data": {
                "strategy_id": summary.strategy_id,
                "symbol": summary.symbol,
                "timeframe": summary.timeframe,
                "net_pnl": float(summary.net_pnl) if summary.net_pnl is not None else None,
                "max_drawdown": float(summary.max_drawdown) if summary.max_drawdown is not None else None,
                "win_rate": float(summary.win_rate) if summary.win_rate is not None else None,
                "profit_factor": float(summary.profit_factor) if summary.profit_factor is not None else None,
                "total_trades": summary.total_trades,
                "winning_trades": summary.winning_trades,
                "losing_trades": summary.losing_trades,
                "from_time": summary.from_time,
                "to_time": summary.to_time,
                "backtest_run_id": summary.backtest_run_id,
                "created_at": summary.created_at.isoformat() if summary.created_at else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching performance summary for strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/auth/strategy/{strategy_id}/performance/daily")
def get_strategy_performance_daily(
    strategy_id: int,
    backtest_run_id: Optional[str] = Query(None, description="Backtest run ID (optional, uses latest if not provided)"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get daily performance chart data for a strategy.
    
    Reads from: strategy_backtest_daily
    Filters by: strategy_id, backtest_run_id (if provided)
    Orders by: date ASC
    
    Args:
        strategy_id: Strategy ID
        backtest_run_id: Optional backtest run ID (uses latest if not provided)
        db: Database session
    
    Returns:
        {
            "success": true,
            "data": [
                {
                    "date": "2025-01-10",
                    "daily_pnl": 120.5,
                    "cumulative_pnl": 560.3,
                    "drawdown": -80.2
                }
            ]
        }
    """
    try:
        # Verify strategy access (includes user authentication and ownership checks)
        _verify_strategy_access(db, strategy_id, authorization)
        
        # If backtest_run_id not provided, get latest from summary
        if not backtest_run_id:
            latest_summary = db.query(StrategyBacktestSummary).filter(
                StrategyBacktestSummary.strategy_id == strategy_id
            ).order_by(desc(StrategyBacktestSummary.created_at)).first()
            
            if not latest_summary:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No backtest data found for strategy {strategy_id}"
                )
            
            backtest_run_id = latest_summary.backtest_run_id
        else:
            # Verify backtest_run_id belongs to strategy
            if not _verify_backtest_run_id(db, strategy_id, backtest_run_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Backtest run {backtest_run_id} not found for strategy {strategy_id}"
                )
        
        # Fetch daily performance data
        daily_records = db.query(StrategyBacktestDaily).filter(
            and_(
                StrategyBacktestDaily.strategy_id == strategy_id,
                StrategyBacktestDaily.backtest_run_id == backtest_run_id
            )
        ).order_by(asc(StrategyBacktestDaily.date)).all()
        
        if not daily_records:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No daily performance data found for strategy {strategy_id} (run_id: {backtest_run_id})"
            )
        
        # Format response
        data = []
        for record in daily_records:
            data.append({
                "date": record.date.isoformat() if record.date else None,
                "daily_pnl": float(record.daily_pnl) if record.daily_pnl is not None else None,
                "cumulative_pnl": float(record.cumulative_pnl) if record.cumulative_pnl is not None else None,
                "drawdown": float(record.drawdown) if record.drawdown is not None else None
            })
        
        return {
            "success": True,
            "backtest_run_id": backtest_run_id,
            "data": data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching daily performance for strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/auth/strategy/{strategy_id}/performance/trades")
def get_strategy_performance_trades(
    strategy_id: int,
    backtest_run_id: Optional[str] = Query(None, description="Backtest run ID (optional, uses latest if not provided)"),
    limit: int = Query(50, ge=1, le=500, description="Number of trades to return"),
    offset: int = Query(0, ge=0, description="Number of trades to skip"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get trade-by-trade backtest details (paginated).
    
    Reads from: strategy_backtest_trades
    Filters by: strategy_id, backtest_run_id (if provided)
    Orders by: entry_time ASC
    Applies pagination: limit + offset
    
    Args:
        strategy_id: Strategy ID
        backtest_run_id: Optional backtest run ID (uses latest if not provided)
        limit: Number of trades to return (1-500, default: 50)
        offset: Number of trades to skip (default: 0)
        db: Database session
    
    Returns:
        {
            "success": true,
            "total": 432,
            "limit": 50,
            "offset": 0,
            "backtest_run_id": "uuid",
            "data": [
                {
                    "entry_time": "2025-01-10T09:30:00Z",
                    "exit_time": "2025-01-10T10:15:00Z",
                    "side": "BUY",
                    "entry_price": 42000.5,
                    "exit_price": 42120.8,
                    "pnl": 120.3,
                    "pnl_percent": 0.28,
                    "exit_reason": "TARGET",
                    "holding_time_seconds": 2700
                }
            ]
        }
    """
    try:
        # Verify strategy access (includes user authentication and ownership checks)
        _verify_strategy_access(db, strategy_id, authorization)
        
        # If backtest_run_id not provided, get latest from summary
        if not backtest_run_id:
            latest_summary = db.query(StrategyBacktestSummary).filter(
                StrategyBacktestSummary.strategy_id == strategy_id
            ).order_by(desc(StrategyBacktestSummary.created_at)).first()
            
            if not latest_summary:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No backtest data found for strategy {strategy_id}"
                )
            
            backtest_run_id = latest_summary.backtest_run_id
        else:
            # Verify backtest_run_id belongs to strategy
            if not _verify_backtest_run_id(db, strategy_id, backtest_run_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Backtest run {backtest_run_id} not found for strategy {strategy_id}"
                )
        
        # Build query
        query = db.query(StrategyBacktestTrades).filter(
            and_(
                StrategyBacktestTrades.strategy_id == strategy_id,
                StrategyBacktestTrades.backtest_run_id == backtest_run_id
            )
        )
        
        # Get total count (for pagination metadata)
        total = query.count()
        
        # Apply ordering and pagination
        trades = query.order_by(asc(StrategyBacktestTrades.entry_time)).offset(offset).limit(limit).all()
        
        # Format response
        data = []
        for trade in trades:
            data.append({
                "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
                "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                "side": trade.side.value if trade.side else None,
                "entry_price": float(trade.entry_price) if trade.entry_price is not None else None,
                "exit_price": float(trade.exit_price) if trade.exit_price is not None else None,
                "quantity": float(trade.quantity) if trade.quantity is not None else None,
                "pnl": float(trade.pnl) if trade.pnl is not None else None,
                "pnl_percent": float(trade.pnl_percent) if trade.pnl_percent is not None else None,
                "exit_reason": trade.exit_reason,
                "holding_time_seconds": trade.holding_time_seconds
            })
        
        return {
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "backtest_run_id": backtest_run_id,
            "data": data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching trades for strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

