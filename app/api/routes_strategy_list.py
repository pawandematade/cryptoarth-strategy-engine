"""
Strategy List API Routes
Provides endpoints for Template and History tabs.

TEMPLATE TAB: GET /strategies
- Returns: strategy blueprints (id, name, status, created_by, updated_at)
- NO PnL, NO run logs

HISTORY TAB: GET /strategy-runs
- Returns: execution/backtest history (strategy_name, run_source, pnl, trades, created_at)
- Read-only execution logs
"""
from fastapi import APIRouter, HTTPException, Header, Depends, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
import logging

from app.database import get_db
from app.models import Strategy, StrategyVersion, StrategyExecution, User
from app.services.user_sync_service import get_or_sync_user

logger = logging.getLogger(__name__)

router = APIRouter()


class StrategyListItem(BaseModel):
    """Strategy item for Template tab"""
    id: int
    name: str
    status: str
    created_by: str  # 'ai' or 'manual'
    updated_at: datetime
    strategy_code: str
    description: Optional[str] = None


class StrategyListResponse(BaseModel):
    """Response model for GET /strategies"""
    success: bool
    strategies: List[StrategyListItem]
    total: int


class StrategyDetailResponse(BaseModel):
    """Response model for GET /strategies/{id}"""
    success: bool
    strategy: Dict[str, Any]
    message: Optional[str] = None


class StrategyRunItem(BaseModel):
    """Strategy run item for History tab"""
    id: int
    strategy_id: int
    strategy_name: str
    strategy_code: str
    execution_mode: str  # 'template', 'paper', or 'live'
    run_source: str  # 'template', 'paper', 'live', 'ai_backtest', or 'manual_backtest'
    pnl: Optional[float] = None
    trades: Optional[int] = None
    created_at: datetime
    status: Optional[str] = None


class StrategyRunsResponse(BaseModel):
    """Response model for GET /strategy-runs"""
    success: bool
    runs: List[StrategyRunItem]
    total: int


@router.get("/strategies", response_model=StrategyListResponse)
def get_strategies(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Get all strategies for Template tab.
    
    Returns strategy blueprints (no PnL, no run logs).
    Used by Template tab to show strategy cards.
    
    Args:
        authorization: Authorization header (Bearer token)
        db: Database session
        limit: Maximum number of strategies to return
        offset: Number of strategies to skip
    
    Returns:
        StrategyListResponse with strategies list
    """
    try:
        # Sync user from auth backend
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Failed to authenticate user")
        
        # CRITICAL: Get ALL strategies for this user (draft + active + paused + archived)
        # NO status filtering - Template tab must show all strategies
        strategies = db.query(Strategy).filter(
            Strategy.user_id == user.id
        ).order_by(desc(Strategy.updated_at)).offset(offset).limit(limit).all()
        
        # Get total count (all statuses)
        total = db.query(Strategy).filter(Strategy.user_id == user.id).count()
        
        # Build response
        strategy_items = []
        for strategy in strategies:
            # Get status as string (handle Enum)
            status_str = strategy.status.value if hasattr(strategy.status, 'value') else str(strategy.status)
            
            # Handle created_by - use default if NULL (for existing records)
            created_by = strategy.created_by if strategy.created_by else 'manual'
            
            strategy_items.append(StrategyListItem(
                id=strategy.id,
                name=strategy.name,
                status=status_str,
                created_by=created_by,
                updated_at=strategy.updated_at,
                strategy_code=strategy.strategy_code,
                description=strategy.description
            ))
        
        return StrategyListResponse(
            success=True,
            strategies=strategy_items,
            total=total
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/strategies/{strategy_id}", response_model=StrategyDetailResponse)
def get_strategy_by_id(
    strategy_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get a specific strategy by ID with full details.
    
    Returns strategy with latest version payload for editing/loading.
    Used when clicking a strategy from Template tab.
    
    Args:
        strategy_id: Strategy ID
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        StrategyDetailResponse with full strategy details
    """
    try:
        # Sync user from auth backend
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Failed to authenticate user")
        
        # Get strategy by ID
        strategy = db.query(Strategy).filter(
            Strategy.id == strategy_id,
            Strategy.user_id == user.id  # CRITICAL: Verify ownership
        ).first()
        
        if not strategy:
            raise HTTPException(
                status_code=404,
                detail=f"Strategy with ID {strategy_id} not found or access denied"
            )
        
        # Get latest version with strategy_payload
        latest_version = db.query(StrategyVersion).filter(
            StrategyVersion.strategy_id == strategy_id
        ).order_by(desc(StrategyVersion.version)).first()
        
        if not latest_version:
            raise HTTPException(
                status_code=404,
                detail=f"No version found for strategy {strategy_id}"
            )
        
        # Get status as string (handle Enum)
        status_str = strategy.status.value if hasattr(strategy.status, 'value') else str(strategy.status)
        
        # Handle created_by - use default if NULL
        created_by = strategy.created_by if strategy.created_by else 'manual'
        
        # Build strategy response with full details
        # CRITICAL: Frontend expects response.data.strategy to be the strategy JSON payload
        # The strategy_payload from StrategyVersion IS the strategy JSON
        # We return it directly as the 'strategy' field
        strategy_payload = latest_version.strategy_payload.copy() if isinstance(latest_version.strategy_payload, dict) else latest_version.strategy_payload
        
        # Add metadata fields to strategy payload (if not already present)
        if isinstance(strategy_payload, dict):
            strategy_payload["id"] = strategy.id
            strategy_payload["strategy_code"] = strategy.strategy_code
            strategy_payload["strategy_id"] = strategy.id  # For compatibility
            strategy_payload["version"] = latest_version.version
            if strategy_payload.get("name") is None:
                strategy_payload["name"] = strategy.name
            if strategy_payload.get("description") is None:
                strategy_payload["description"] = strategy.description
        
        return StrategyDetailResponse(
            success=True,
            strategy=strategy_payload,  # CRITICAL: Return strategy_payload directly (frontend expects this)
            message="Strategy loaded successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy by ID: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/strategy-runs", response_model=StrategyRunsResponse)
def get_strategy_runs(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
    strategy_id: Optional[int] = Query(None, description="Filter by strategy ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Get strategy execution/backtest history for History tab.
    
    Returns execution logs (run_source, pnl, trades, created_at).
    Used by History tab to show execution history.
    
    Args:
        authorization: Authorization header (Bearer token)
        db: Database session
        strategy_id: Optional filter by strategy ID
        limit: Maximum number of runs to return
        offset: Number of runs to skip
    
    Returns:
        StrategyRunsResponse with runs list
    """
    try:
        # Sync user from auth backend
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Failed to authenticate user")
        
        # Build query - only get executions for user's strategies
        query = db.query(StrategyExecution).join(Strategy).filter(
            Strategy.user_id == user.id
        )
        
        # Filter by strategy_id if provided
        if strategy_id:
            query = query.filter(StrategyExecution.strategy_id == strategy_id)
        
        # Get executions ordered by created_at (newest first)
        executions = query.order_by(desc(StrategyExecution.created_at)).offset(offset).limit(limit).all()
        
        # Get total count
        total_query = db.query(StrategyExecution).join(Strategy).filter(Strategy.user_id == user.id)
        if strategy_id:
            total_query = total_query.filter(StrategyExecution.strategy_id == strategy_id)
        total = total_query.count()
        
        # Build response - FLAT structure (no nested objects)
        run_items = []
        for execution in executions:
            # Get status as string (handle Enum)
            status_str = execution.status.value if hasattr(execution.status, 'value') else str(execution.status)
            
            # Get execution_mode as string
            execution_mode_str = execution.execution_mode.value if hasattr(execution.execution_mode, 'value') else str(execution.execution_mode)
            
            # CRITICAL: Use execution's own pnl and trades fields
            # These are updated by paper trade service and signal service
            pnl = None
            try:
                if execution.pnl:
                    pnl = float(execution.pnl)
            except (ValueError, TypeError):
                pnl = None
            
            trades = execution.trades if execution.trades else None
            
            # For backtests, try to get from snapshot if execution fields are empty
            if (pnl is None or trades is None) and execution.run_source in ['ai_backtest', 'manual_backtest']:
                version = db.query(StrategyVersion).filter(
                    StrategyVersion.strategy_id == execution.strategy_id,
                    StrategyVersion.version == execution.strategy_version
                ).first()
                
                if version and version.backtest_snapshot:
                    snapshot = version.backtest_snapshot
                    if isinstance(snapshot, dict):
                        summary = snapshot.get('summary', {})
                        if pnl is None:
                            pnl = summary.get('netPNL') or summary.get('net_pnl') or summary.get('totalReturn')
                        if trades is None:
                            trades = summary.get('totalTrades') or summary.get('total_trades')
            
            # CRITICAL: Use execution's strategy_name and strategy_code (snapshot fields)
            # These are set when execution is created
            strategy_name = execution.strategy_name or "Unknown Strategy"
            strategy_code = execution.strategy_code or "UNKNOWN"
            
            run_items.append(StrategyRunItem(
                id=execution.id,
                strategy_id=execution.strategy_id,
                strategy_name=strategy_name,
                strategy_code=strategy_code,
                execution_mode=execution_mode_str,
                run_source=execution.run_source or 'live',  # Default to 'live' if not set
                pnl=pnl,
                trades=trades,
                created_at=execution.created_at,
                status=status_str
            ))
        
        return StrategyRunsResponse(
            success=True,
            runs=run_items,
            total=total
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

