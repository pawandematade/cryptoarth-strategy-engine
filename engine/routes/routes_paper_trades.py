"""
Paper Trades API Routes
Handles paper trade history and PDF export.
"""
from fastapi import APIRouter, HTTPException, Header, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from common.db import get_db
from models import StrategyExecution, PaperTrade, Strategy
from core.services.user_sync_service import get_or_sync_user
from core.services.pdf_service import generate_paper_trade_pdf

logger = logging.getLogger(__name__)

router = APIRouter()


class PaperTradeItem(BaseModel):
    """Paper trade item"""
    id: int
    execution_id: int
    symbol: str
    side: str
    lot_size: str
    contract_value: str
    entry_price: Optional[str] = None
    exit_price: Optional[str] = None
    leverage: int
    usable_capital: str
    margin_used: str
    pnl: str
    created_at: str


class PaperTradesResponse(BaseModel):
    """Response model for paper trades list"""
    success: bool
    trades: List[PaperTradeItem]
    total: int
    execution_id: int
    strategy_name: str
    strategy_code: str
    execution_mode: str
    total_pnl: str
    total_trades: int


@router.get("/paper-trades/{execution_id}", response_model=PaperTradesResponse)
def get_paper_trades(
    execution_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get paper trades for an execution.
    
    Args:
        execution_id: Execution ID
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        PaperTradesResponse with trades list
    """
    try:
        # Authenticate user
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Failed to authenticate user")
        
        # CRITICAL: Business tables store external_user_id in user_id column
        # ALWAYS scope StrategyExecution queries by user.external_user_id
        # Get execution - scoped by user to prevent data leakage
        execution = db.query(StrategyExecution).filter(
            StrategyExecution.id == execution_id,
            StrategyExecution.user_id == user.external_user_id  # CRITICAL: User scoping
        ).first()
        
        if not execution:
            raise HTTPException(
                status_code=404,
                detail=f"Execution with ID {execution_id} not found"
            )
        
        # Verify ownership - Business tables store external_user_id in user_id column
        strategy = db.query(Strategy).filter(
            Strategy.id == execution.strategy_id,
            Strategy.user_id == user.external_user_id
        ).first()
        
        if not strategy:
            raise HTTPException(
                status_code=403,
                detail="Access denied to this execution"
            )
        
        # Get paper trades
        paper_trades = db.query(PaperTrade).filter(
            PaperTrade.execution_id == execution_id
        ).order_by(PaperTrade.created_at.asc()).all()
        
        # Build response
        trade_items = []
        for trade in paper_trades:
            trade_items.append(PaperTradeItem(
                id=trade.id,
                execution_id=trade.execution_id,
                symbol=trade.symbol,
                side=trade.side,
                lot_size=trade.lot_size,
                contract_value=trade.contract_value,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                leverage=trade.leverage,
                usable_capital=trade.usable_capital,
                margin_used=trade.margin_used,
                pnl=trade.pnl,
                created_at=trade.created_at.isoformat() if trade.created_at else ""
            ))
        
        execution_mode_str = execution.execution_mode.value if hasattr(execution.execution_mode, 'value') else str(execution.execution_mode)
        
        return PaperTradesResponse(
            success=True,
            trades=trade_items,
            total=len(trade_items),
            execution_id=execution.id,
            strategy_name=execution.strategy_name,
            strategy_code=execution.strategy_code,
            execution_mode=execution_mode_str,
            total_pnl=execution.pnl or "0.0",
            total_trades=execution.trades or 0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting paper trades: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/paper-trades/{execution_id}/pdf")
def get_paper_trades_pdf(
    execution_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Generate PDF export for paper trades.
    
    PDF includes:
    - Strategy name
    - Execution mode
    - Trade table
    - Total PnL
    - Date range
    
    Args:
        execution_id: Execution ID
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        PDF file response
    """
    try:
        # Authenticate user
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Failed to authenticate user")
        
        # CRITICAL: Business tables store external_user_id in user_id column
        # ALWAYS scope StrategyExecution queries by user.external_user_id
        # Get execution - scoped by user to prevent data leakage
        execution = db.query(StrategyExecution).filter(
            StrategyExecution.id == execution_id,
            StrategyExecution.user_id == user.external_user_id  # CRITICAL: User scoping
        ).first()
        
        if not execution:
            raise HTTPException(
                status_code=404,
                detail=f"Execution with ID {execution_id} not found"
            )
        
        # Verify ownership - Business tables store external_user_id in user_id column
        strategy = db.query(Strategy).filter(
            Strategy.id == execution.strategy_id,
            Strategy.user_id == user.external_user_id
        ).first()
        
        if not strategy:
            raise HTTPException(
                status_code=403,
                detail="Access denied to this execution"
            )
        
        # Get paper trades
        paper_trades = db.query(PaperTrade).filter(
            PaperTrade.execution_id == execution_id
        ).order_by(PaperTrade.created_at.asc()).all()
        
        # Generate PDF
        pdf_bytes = generate_paper_trade_pdf(execution, paper_trades)
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=paper_trades_{execution_id}.pdf"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

