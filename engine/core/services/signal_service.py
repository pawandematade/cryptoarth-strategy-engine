"""
Signal Generation Service
Handles strategy signal generation with safety locks.

CRITICAL SAFETY RULES:
- One signal per strategy per candle
- No duplicate signals
- No signal spam
- Lock by execution_id
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models import StrategyExecution, ExecutionStatus, ExecutionMode
from core.services.paper_trade_service import (
    calculate_lot_size,
    create_paper_trade,
    get_open_position,
    close_position,
    update_execution_pnl
)

logger = logging.getLogger(__name__)


# In-memory signal lock (for single-process deployment)
# For multi-process, use Redis or DB-based locking
_signal_locks: Dict[int, Dict[str, datetime]] = {}


def get_signal_lock_key(execution_id: int, symbol: str, timeframe: str) -> str:
    """
    Generate lock key for signal.
    
    Args:
        execution_id: Execution ID
        symbol: Trading symbol
        timeframe: Timeframe
    
    Returns:
        str: Lock key
    """
    return f"{execution_id}:{symbol}:{timeframe}"


def check_signal_lock(execution_id: int, symbol: str, timeframe: str, candle_time: datetime) -> bool:
    """
    Check if signal is locked for this candle.
    
    Args:
        execution_id: Execution ID
        symbol: Trading symbol
        timeframe: Timeframe
        candle_time: Current candle timestamp
    
    Returns:
        bool: True if locked (signal already sent for this candle), False otherwise
    """
    lock_key = get_signal_lock_key(execution_id, symbol, timeframe)
    
    if execution_id not in _signal_locks:
        _signal_locks[execution_id] = {}
    
    if lock_key in _signal_locks[execution_id]:
        last_signal_time = _signal_locks[execution_id][lock_key]
        # Same candle = same timestamp (rounded to timeframe)
        if last_signal_time == candle_time:
            return True
    
    return False


def set_signal_lock(execution_id: int, symbol: str, timeframe: str, candle_time: datetime) -> None:
    """
    Set signal lock for this candle.
    
    Args:
        execution_id: Execution ID
        symbol: Trading symbol
        timeframe: Timeframe
        candle_time: Current candle timestamp
    """
    lock_key = get_signal_lock_key(execution_id, symbol, timeframe)
    
    if execution_id not in _signal_locks:
        _signal_locks[execution_id] = {}
    
    _signal_locks[execution_id][lock_key] = candle_time
    
    logger.debug(f"Signal lock set: execution_id={execution_id}, lock_key={lock_key}, candle_time={candle_time}")


def process_strategy_signal(
    db: Session,
    execution: StrategyExecution,
    signal: str,
    symbol: str,
    timeframe: str,
    price: float,
    strategy_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process a strategy signal.
    
    CRITICAL: This function enforces all safety rules:
    - One signal per candle
    - One open position at a time (paper mode)
    - No duplicate signals
    
    Args:
        db: Database session
        execution: Strategy execution record
        signal: Signal type (BUY, SELL, EXIT)
        symbol: Trading symbol
        timeframe: Timeframe
        price: Current price
        strategy_config: Strategy configuration (capital, leverage, etc.)
    
    Returns:
        dict: Result with status and message
    """
    try:
        # Get current candle time (rounded to timeframe)
        now = datetime.now(timezone.utc)
        candle_time = now  # TODO: Round to timeframe (e.g., 5m, 15m)
        
        # CRITICAL: Check signal lock (one signal per candle)
        if check_signal_lock(execution.id, symbol, timeframe, candle_time):
            logger.warning(f"Signal locked for this candle: execution_id={execution.id}, symbol={symbol}, timeframe={timeframe}")
            return {
                "status": "locked",
                "message": "Signal already sent for this candle",
                "execution_id": execution.id
            }
        
        # Process based on execution mode
        # CRITICAL: Use lowercase enum members (paper, live, template)
        if execution.execution_mode == ExecutionMode.paper:
            return _process_paper_signal(db, execution, signal, symbol, timeframe, price, strategy_config, candle_time)
        elif execution.execution_mode == ExecutionMode.live:
            return _process_live_signal(db, execution, signal, symbol, timeframe, price, strategy_config, candle_time)
        else:  # template mode - no signals
            return {
                "status": "ignored",
                "message": "Template mode - signals not processed",
                "execution_id": execution.id
            }
            
    except Exception as e:
        logger.error(f"Error processing signal: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Signal processing error: {str(e)}",
            "execution_id": execution.id
        }


def _process_paper_signal(
    db: Session,
    execution: StrategyExecution,
    signal: str,
    symbol: str,
    timeframe: str,
    price: float,
    strategy_config: Dict[str, Any],
    candle_time: datetime
) -> Dict[str, Any]:
    """
    Process paper trading signal.
    
    Args:
        db: Database session
        execution: Strategy execution
        signal: Signal type
        symbol: Trading symbol
        timeframe: Timeframe
        price: Current price
        strategy_config: Strategy config
        candle_time: Current candle time
    
    Returns:
        dict: Result
    """
    signal_upper = signal.upper()
    
    # Get open position
    open_position = get_open_position(db, execution.id, symbol)
    
    if signal_upper == "BUY":
        # BUY signal
        if open_position:
            # Already have open position - ignore
            logger.info(f"BUY signal ignored - open position exists: execution_id={execution.id}, symbol={symbol}")
            return {
                "status": "ignored",
                "message": "Open position exists - BUY signal ignored",
                "execution_id": execution.id
            }
        
        # Calculate lot size
        total_capital = float(strategy_config.get("total_capital", 1000))
        capital_percent = float(strategy_config.get("capital_percent", 20))
        leverage = int(strategy_config.get("leverage", 25))
        contract_value = float(strategy_config.get("contract_value", 0.0001))
        
        lot_size, usable_capital, margin_required, error_msg = calculate_lot_size(
            total_capital=total_capital,
            capital_percent=capital_percent,
            leverage=leverage,
            contract_value=contract_value,
            mark_price=price
        )
        
        if lot_size is None:
            logger.warning(f"Lot size calculation failed: {error_msg}")
            return {
                "status": "error",
                "message": f"Lot size calculation failed: {error_msg}",
                "execution_id": execution.id
            }
        
        # Create paper trade
        paper_trade = create_paper_trade(
            db=db,
            execution_id=execution.id,
            symbol=symbol,
            side="BUY",
            lot_size=lot_size,
            contract_value=contract_value,
            entry_price=price,
            leverage=leverage,
            usable_capital=usable_capital,
            margin_used=margin_required
        )
        
        # Update execution trades count
        execution.trades += 1
        update_execution_pnl(db, execution.id)
        
        # Set signal lock
        set_signal_lock(execution.id, symbol, timeframe, candle_time)
        
        db.commit()
        
        logger.info(f"Paper BUY trade created: execution_id={execution.id}, symbol={symbol}, lot_size={lot_size}, price={price}")
        
        return {
            "status": "success",
            "message": "Paper BUY trade executed",
            "execution_id": execution.id,
            "trade_id": paper_trade.id,
            "lot_size": lot_size,
            "price": price
        }
    
    elif signal_upper in ["SELL", "EXIT"]:
        # SELL/EXIT signal
        if not open_position:
            # No open position - ignore
            logger.info(f"SELL signal ignored - no open position: execution_id={execution.id}, symbol={symbol}")
            return {
                "status": "ignored",
                "message": "No open position - SELL signal ignored",
                "execution_id": execution.id
            }
        
        # Close position
        close_position(db, open_position, exit_price=price)
        
        # Update execution
        update_execution_pnl(db, execution.id)
        
        # Set signal lock
        set_signal_lock(execution.id, symbol, timeframe, candle_time)
        
        db.commit()
        
        logger.info(f"Paper SELL trade executed: execution_id={execution.id}, symbol={symbol}, price={price}")
        
        return {
            "status": "success",
            "message": "Paper SELL trade executed",
            "execution_id": execution.id,
            "trade_id": open_position.id,
            "price": price
        }
    
    else:
        logger.warning(f"Unknown signal type: {signal}")
        return {
            "status": "error",
            "message": f"Unknown signal type: {signal}",
            "execution_id": execution.id
        }


def _process_live_signal(
    db: Session,
    execution: StrategyExecution,
    signal: str,
    symbol: str,
    timeframe: str,
    price: float,
    strategy_config: Dict[str, Any],
    candle_time: datetime
) -> Dict[str, Any]:
    """
    Process live trading signal (webhook only).
    
    Args:
        db: Database session
        execution: Strategy execution
        signal: Signal type
        symbol: Trading symbol
        timeframe: Timeframe
        price: Current price
        strategy_config: Strategy config
        candle_time: Current candle time
    
    Returns:
        dict: Result
    """
    from core.services.webhook_service import send_strategy_signal
    
    # Prepare webhook payload
    payload = {
        "event": "STRATEGY_SIGNAL",
        "strategy_code": execution.strategy_code,
        "strategy_name": execution.strategy_name,
        "symbol": symbol,
        "signal": signal.upper(),
        "timeframe": timeframe,
        "price": price,
        "timestamp": candle_time.isoformat(),
        "execution_id": execution.id
    }
    
    # Send webhook signal
    send_result = send_strategy_signal(payload)
    
    # Set signal lock
    set_signal_lock(execution.id, symbol, timeframe, candle_time)
    
    db.commit()
    
    logger.info(f"Live signal sent: execution_id={execution.id}, symbol={symbol}, signal={signal}, price={price}")
    
    return {
        "status": "success",
        "message": "Live signal sent via webhook",
        "execution_id": execution.id,
        "webhook_result": send_result
    }

