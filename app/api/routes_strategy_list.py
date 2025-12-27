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
from sqlalchemy import desc, func
from datetime import datetime
from collections import defaultdict
import logging

from app.database import get_db
from app.models import Strategy, StrategyVersion, StrategyExecution, User
from app.api.user_dependencies import get_current_user_strict

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


class ModeStatus(BaseModel):
    """Status for a single execution mode (paper or live)"""
    exists: bool
    status: Optional[str] = None  # 'running', 'stopped', 'paused', 'completed'
    pnl: Optional[float] = None
    started_at: Optional[datetime] = None


class StrategyRunItem(BaseModel):
    """Strategy run item for History tab - GROUPED by strategy_code"""
    strategy_code: str
    strategy_name: str
    is_premium: bool = False  # Premium indicator
    paper: ModeStatus
    live: ModeStatus


class StrategyRunsResponse(BaseModel):
    """Response model for GET /strategy-runs - Returns ONE card per strategy"""
    success: bool
    runs: List[StrategyRunItem]
    total: int


@router.get("/strategies", response_model=StrategyListResponse)
def get_strategies(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_strict),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Get all strategies for Template tab.
    
    Returns strategy blueprints (no PnL, no run logs).
    Used by Template tab to show strategy cards.
    
    Args:
        db: Database session
        user: Authenticated user (from JWT)
        limit: Maximum number of strategies to return
        offset: Number of strategies to skip
    
    Returns:
        StrategyListResponse with strategies list
    """
    try:
        # CRITICAL: JWT user.id is the ONLY source of truth
        # Show ACTIVE and DRAFT strategies only (no admin logic, no created_by filter)
        logger.error(f"JWT USER ID = {user.id}")
        
        # Import StrategyStatus enum for proper filtering
        from app.models import StrategyStatus
        
        query = db.query(Strategy).filter(
            Strategy.user_id == user.id,
            Strategy.status.in_([StrategyStatus.ACTIVE, StrategyStatus.DRAFT])
        )
        
        # Debug: Log row count before pagination
        row_count = query.count()
        logger.error(f"ROW COUNT = {row_count}")
        
        strategies = query.order_by(desc(Strategy.updated_at)).offset(offset).limit(limit).all()
        total = row_count
        logger.info(f"[Templates] Found {len(strategies)} strategies (total={total}) for user_id={user.id}")
        
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_strict)
):
    """
    Get a specific strategy by ID with full details.
    
    Returns strategy with latest version payload for editing/loading.
    Used when clicking a strategy from Template tab.
    
    Args:
        strategy_id: Strategy ID
        db: Database session
        user: Authenticated user (from JWT)
    
    Returns:
        StrategyDetailResponse with full strategy details
    """
    try:
        
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_strict),
    strategy_id: Optional[int] = Query(None, description="Filter by strategy ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Get strategy execution/backtest history for History tab.
    
    Returns execution logs (run_source, pnl, trades, created_at).
    Used by History tab to show execution history.
    
    Args:
        db: Database session
        user: Authenticated user (from JWT)
        strategy_id: Optional filter by strategy ID
        limit: Maximum number of runs to return
        offset: Number of runs to skip
    
    Returns:
        StrategyRunsResponse with runs list
    """
    try:
        # CRITICAL: JWT user.id is the ONLY source of truth
        # NO joins - direct filter by user_id
        # NO status filters, NO admin logic
        logger.error(f"JWT USER ID = {user.id}")
        
        # Get all executions for user - direct query (no join)
        query = db.query(StrategyExecution).filter(
            StrategyExecution.user_id == user.id
        )
        
        if strategy_id:
            query = query.filter(StrategyExecution.strategy_id == strategy_id)
        
        # Debug: Log row count
        row_count = query.count()
        logger.error(f"ROW COUNT = {row_count}")
        
        executions = query.order_by(desc(StrategyExecution.created_at)).all()
        logger.info(f"[History] Found {len(executions)} executions for user_id={user.id}")
        
        # Group by strategy_code
        strategy_groups = defaultdict(lambda: {
            'strategy_code': None,
            'strategy_name': None,
            'is_premium': False,  # TODO: Get from strategy metadata
            'paper': {
                'exists': False,
                'status': None,
                'pnl': None,
                'started_at': None
            },
            'live': {
                'exists': False,
                'status': None,
                'pnl': None,
                'started_at': None
            }
        })
        
        for execution in executions:
            strategy_code = execution.strategy_code or "UNKNOWN"
            group = strategy_groups[strategy_code]
            
            # Set strategy metadata (from first execution)
            if not group['strategy_code']:
                group['strategy_code'] = strategy_code
                group['strategy_name'] = execution.strategy_name or "Unknown Strategy"
            
            # Get status and mode
            status_str = execution.status.value if hasattr(execution.status, 'value') else str(execution.status)
            mode_str = execution.execution_mode.value if hasattr(execution.execution_mode, 'value') else str(execution.execution_mode)
            
            # Update mode-specific data
            if mode_str in ['paper', 'live']:
                mode_data = group[mode_str]
                mode_data['exists'] = True
                mode_data['status'] = status_str
                
                # Get P&L
                try:
                    pnl_value = float(execution.pnl) if execution.pnl else 0.0
                    # Keep latest P&L if multiple executions exist
                    if mode_data['pnl'] is None or execution.updated_at > mode_data.get('_last_update', datetime.min):
                        mode_data['pnl'] = pnl_value
                        mode_data['_last_update'] = execution.updated_at
                except (ValueError, TypeError):
                    mode_data['pnl'] = 0.0
                
                # Get started_at (use activated_at if available, else created_at)
                if execution.activated_at:
                    if mode_data['started_at'] is None or execution.activated_at > mode_data['started_at']:
                        mode_data['started_at'] = execution.activated_at
                elif execution.created_at:
                    if mode_data['started_at'] is None or execution.created_at > mode_data['started_at']:
                        mode_data['started_at'] = execution.created_at
        
        # Build response - ONE item per strategy_code
        run_items = []
        for strategy_code, group in strategy_groups.items():
            # Clean up internal tracking fields
            group['paper'].pop('_last_update', None)
            group['live'].pop('_last_update', None)
            
            run_items.append(StrategyRunItem(
                strategy_code=group['strategy_code'],
                strategy_name=group['strategy_name'],
                is_premium=group['is_premium'],
                paper=ModeStatus(**group['paper']),
                live=ModeStatus(**group['live'])
            ))
        
        # Sort by most recent started_at (any mode)
        run_items.sort(key=lambda x: max(
            x.paper.started_at or datetime.min,
            x.live.started_at or datetime.min
        ), reverse=True)
        
        # Apply pagination
        total = len(run_items)
        run_items = run_items[offset:offset + limit]
        
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

