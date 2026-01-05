"""
Paper Trade Service
Handles virtual trading with capital-based lot sizing.

CRITICAL RULES:
- No fractional lots (always floor)
- No rounding
- Margin check before trade
- One open position at a time
"""
import logging
import math
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_DOWN
from sqlalchemy.orm import Session
from models import StrategyExecution, PaperTrade, ExecutionStatus

logger = logging.getLogger(__name__)


def calculate_lot_size(
    total_capital: float,
    capital_percent: float,
    leverage: int,
    contract_value: float,
    mark_price: float
) -> tuple[Optional[int], Optional[float], Optional[float], Optional[str]]:
    """
    Calculate lot size using exact formula.
    
    Formula (LOCKED):
    usable_capital = total_capital * (capital_percent / 100)
    position_value = usable_capital * leverage
    raw_lot_size = position_value / (contract_value * mark_price)
    lot_size = floor(raw_lot_size)
    
    Args:
        total_capital: Total capital available
        capital_percent: Percentage of capital to use (0-100)
        leverage: Leverage multiplier
        contract_value: Contract value per lot
        mark_price: Current market price
    
    Returns:
        tuple: (lot_size, usable_capital, margin_required, error_message)
        - lot_size: Integer lot size (None if invalid)
        - usable_capital: Usable capital amount
        - margin_required: Margin required for the trade
        - error_message: Error message if calculation fails
    """
    try:
        # Validate inputs
        if total_capital <= 0:
            return None, None, None, "Total capital must be greater than 0"
        if capital_percent <= 0 or capital_percent > 100:
            return None, None, None, "Capital percent must be between 0 and 100"
        if leverage <= 0:
            return None, None, None, "Leverage must be greater than 0"
        if contract_value <= 0:
            return None, None, None, "Contract value must be greater than 0"
        if mark_price <= 0:
            return None, None, None, "Mark price must be greater than 0"
        
        # Calculate usable capital
        usable_capital = total_capital * (capital_percent / 100)
        
        # Calculate position value
        position_value = usable_capital * leverage
        
        # Calculate raw lot size
        raw_lot_size = position_value / (contract_value * mark_price)
        
        # CRITICAL: Always floor (no rounding, no fractional lots)
        lot_size = math.floor(raw_lot_size)
        
        # Check if lot size is valid
        if lot_size < 1:
            return None, usable_capital, None, "Lot size is less than 1 (insufficient capital)"
        
        # Calculate margin required
        margin_required = (lot_size * contract_value * mark_price) / leverage
        
        # Margin check
        if margin_required > usable_capital:
            return None, usable_capital, margin_required, "Margin required exceeds usable capital"
        
        return lot_size, usable_capital, margin_required, None
        
    except Exception as e:
        logger.error(f"Error calculating lot size: {e}", exc_info=True)
        return None, None, None, f"Calculation error: {str(e)}"


def create_paper_trade(
    db: Session,
    execution_id: int,
    symbol: str,
    side: str,
    lot_size: int,
    contract_value: float,
    entry_price: float,
    leverage: int,
    usable_capital: float,
    margin_used: float,
    exit_price: Optional[float] = None
) -> PaperTrade:
    """
    Create a paper trade record.
    
    Args:
        db: Database session
        execution_id: Execution ID
        symbol: Trading symbol
        side: BUY or SELL
        lot_size: Lot size (integer)
        contract_value: Contract value
        entry_price: Entry price
        leverage: Leverage used
        usable_capital: Usable capital
        margin_used: Margin used
        exit_price: Exit price (None for open positions)
    
    Returns:
        PaperTrade: Created paper trade record
    """
    # Calculate PnL if exit_price is provided
    pnl = "0.0"
    if exit_price and entry_price:
        if side.upper() == "BUY":
            # BUY: profit when exit > entry
            pnl_value = (exit_price - entry_price) * lot_size * contract_value
        else:  # SELL
            # SELL: profit when exit < entry
            pnl_value = (entry_price - exit_price) * lot_size * contract_value
        pnl = str(round(pnl_value, 2))
    
    paper_trade = PaperTrade(
        execution_id=execution_id,
        symbol=symbol,
        side=side.upper(),
        lot_size=str(lot_size),
        contract_value=str(contract_value),
        entry_price=str(entry_price),
        exit_price=str(exit_price) if exit_price else None,
        leverage=leverage,
        usable_capital=str(usable_capital),
        margin_used=str(margin_used),
        pnl=pnl
    )
    
    db.add(paper_trade)
    db.flush()
    
    logger.info(f"Created paper trade: execution_id={execution_id}, symbol={symbol}, side={side}, lot_size={lot_size}, pnl={pnl}")
    
    return paper_trade


def get_open_position(
    db: Session,
    execution_id: int,
    symbol: str
) -> Optional[PaperTrade]:
    """
    Get open position for a symbol in an execution.
    
    Open position = PaperTrade with exit_price = NULL
    
    Args:
        db: Database session
        execution_id: Execution ID
        symbol: Trading symbol
    
    Returns:
        PaperTrade: Open position or None
    """
    return db.query(PaperTrade).filter(
        PaperTrade.execution_id == execution_id,
        PaperTrade.symbol == symbol,
        PaperTrade.exit_price.is_(None)
    ).first()


def close_position(
    db: Session,
    paper_trade: PaperTrade,
    exit_price: float
) -> PaperTrade:
    """
    Close an open position.
    
    Args:
        db: Database session
        paper_trade: Open position to close
        exit_price: Exit price
    
    Returns:
        PaperTrade: Updated paper trade with exit_price and PnL
    """
    entry_price = float(paper_trade.entry_price)
    lot_size = int(paper_trade.lot_size)
    contract_value = float(paper_trade.contract_value)
    
    # Calculate PnL
    if paper_trade.side.upper() == "BUY":
        pnl_value = (exit_price - entry_price) * lot_size * contract_value
    else:  # SELL
        pnl_value = (entry_price - exit_price) * lot_size * contract_value
    
    # Update paper trade
    paper_trade.exit_price = str(exit_price)
    paper_trade.pnl = str(round(pnl_value, 2))
    
    db.flush()
    
    logger.info(f"Closed position: trade_id={paper_trade.id}, entry={entry_price}, exit={exit_price}, pnl={paper_trade.pnl}")
    
    return paper_trade


def update_execution_pnl(
    db: Session,
    execution_id: int
) -> None:
    """
    Update execution PnL from all paper trades.
    
    Args:
        db: Database session
        execution_id: Execution ID
    """
    execution = db.query(StrategyExecution).filter(StrategyExecution.id == execution_id).first()
    if not execution:
        logger.warning(f"Execution {execution_id} not found for PnL update")
        return
    
    # Sum all PnL from paper trades
    paper_trades = db.query(PaperTrade).filter(PaperTrade.execution_id == execution_id).all()
    total_pnl = sum(float(trade.pnl) for trade in paper_trades)
    
    # Update execution
    execution.pnl = str(round(total_pnl, 2))
    execution.trades = len(paper_trades)
    
    db.flush()
    
    logger.info(f"Updated execution PnL: execution_id={execution_id}, total_pnl={execution.pnl}, trades={execution.trades}")

