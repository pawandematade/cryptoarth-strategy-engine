"""
Execution Logger
Centralized logging for execution events.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("execution_engine")


def log_execution_start(strategy_code: str, version: int, execution_id: int):
    """Log execution start"""
    logger.info(
        f"[Execution Start] strategy_code={strategy_code}, "
        f"version={version}, execution_id={execution_id}"
    )


def log_execution_stop(strategy_code: str, version: int, execution_id: int, reason: str):
    """Log execution stop"""
    logger.info(
        f"[Execution Stop] strategy_code={strategy_code}, "
        f"version={version}, execution_id={execution_id}, reason={reason}"
    )


def log_execution_pause(strategy_code: str, version: int, execution_id: int):
    """Log execution pause"""
    logger.info(
        f"[Execution Pause] strategy_code={strategy_code}, "
        f"version={version}, execution_id={execution_id}"
    )


def log_execution_resume(strategy_code: str, version: int, execution_id: int):
    """Log execution resume"""
    logger.info(
        f"[Execution Resume] strategy_code={strategy_code}, "
        f"version={version}, execution_id={execution_id}"
    )


def log_decision(
    strategy_code: str,
    version: int,
    symbol: str,
    decision: str,
    price: float,
    reason: Optional[str] = None
):
    """Log trading decision (BUY/SELL/HOLD)"""
    log_msg = (
        f"[Decision] strategy_code={strategy_code}, version={version}, "
        f"symbol={symbol}, decision={decision}, price={price}"
    )
    if reason:
        log_msg += f", reason={reason}"
    logger.info(log_msg)


def log_tick_processed(
    strategy_code: str,
    version: int,
    symbol: str,
    timestamp: str,
    price: float
):
    """Log processed market tick"""
    logger.debug(
        f"[Tick] strategy_code={strategy_code}, version={version}, "
        f"symbol={symbol}, timestamp={timestamp}, price={price}"
    )


def log_error(strategy_code: str, version: int, error: Exception, context: Optional[str] = None):
    """Log execution error"""
    error_msg = (
        f"[Execution Error] strategy_code={strategy_code}, "
        f"version={version}, error={type(error).__name__}: {str(error)}"
    )
    if context:
        error_msg += f", context={context}"
    logger.error(error_msg, exc_info=True)


def log_state_change(
    strategy_code: str,
    version: int,
    old_status: str,
    new_status: str
):
    """Log execution state change"""
    logger.info(
        f"[State Change] strategy_code={strategy_code}, version={version}, "
        f"status: {old_status} → {new_status}"
    )
