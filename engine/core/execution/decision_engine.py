"""
Decision Engine
Evaluates strategy logic and returns trading decisions (dry-run only).
"""
import logging
from typing import Dict, Any, Optional, Literal
from core.execution.execution_logger import log_decision, log_error

logger = logging.getLogger("execution_engine.decision_engine")

DecisionType = Literal["BUY", "SELL", "HOLD"]


def evaluate_strategy(
    strategy_payload: Dict[str, Any],
    market_data: Dict[str, Any]
) -> tuple[DecisionType, Optional[str]]:
    """
    Evaluate strategy logic and return trading decision.
    
    This is a DRY-RUN implementation - no actual trading logic.
    Returns decisions based on strategy payload structure.
    
    Args:
        strategy_payload: Strategy JSON payload
        market_data: Mock market data (price, timestamp, etc.)
    
    Returns:
        Tuple of (decision, reason)
        - decision: "BUY", "SELL", or "HOLD"
        - reason: Optional explanation string
    """
    try:
        symbol = strategy_payload.get("symbol", "UNKNOWN")
        strategy_type = strategy_payload.get("strategy_type", "unknown")
        price = market_data.get("price", 0.0)
        
        # DRY-RUN: Simple decision logic based on strategy type
        # In real implementation, this would use StrategyRunner to evaluate conditions
        
        # For now, return HOLD as default (safe default for dry-run)
        decision: DecisionType = "HOLD"
        reason = f"Dry-run mode: {strategy_type} strategy"
        
        # Example: If strategy has logic indicators, we could evaluate them
        # But for skeleton, we just log the structure exists
        if "logic" in strategy_payload:
            reason += " - Strategy logic present"
        
        if "risk" in strategy_payload:
            reason += " - Risk parameters configured"
        
        # Log the decision
        log_decision(
            strategy_code=strategy_payload.get("execution_context", {}).get("strategy_code", "UNKNOWN"),
            version=strategy_payload.get("execution_context", {}).get("version", 0),
            symbol=symbol,
            decision=decision,
            price=price,
            reason=reason
        )
        
        return decision, reason
        
    except Exception as e:
        strategy_code = strategy_payload.get("execution_context", {}).get("strategy_code", "UNKNOWN")
        version = strategy_payload.get("execution_context", {}).get("version", 0)
        log_error(strategy_code, version, e, "evaluate_strategy")
        return "HOLD", f"Error evaluating strategy: {str(e)}"
