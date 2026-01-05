"""
Strategy Loader
Loads strategy payload from database for execution.
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models import Strategy, StrategyVersion, StrategyExecution
from core.execution.execution_logger import log_error

logger = logging.getLogger("execution_engine.strategy_loader")


def load_strategy_for_execution(
    db: Session,
    execution: StrategyExecution
) -> Optional[Dict[str, Any]]:
    """
    Load strategy payload for execution.
    
    Args:
        db: Database session
        execution: StrategyExecution model instance
    
    Returns:
        Strategy payload dictionary, or None if not found/error
    """
    try:
        # Load strategy to get strategy_code
        strategy = db.query(Strategy).filter(
            Strategy.id == execution.strategy_id
        ).first()
        
        if not strategy:
            logger.error(
                f"Strategy not found: strategy_id={execution.strategy_id}, "
                f"execution_id={execution.id}"
            )
            return None
        
        # Load strategy version
        strategy_version = db.query(StrategyVersion).filter(
            StrategyVersion.strategy_id == execution.strategy_id,
            StrategyVersion.version == execution.strategy_version
        ).first()
        
        if not strategy_version:
            logger.error(
                f"Strategy version not found: strategy_id={execution.strategy_id}, "
                f"version={execution.strategy_version}, execution_id={execution.id}"
            )
            return None
        
        # Extract strategy payload
        strategy_payload = strategy_version.strategy_payload
        
        if not strategy_payload or not isinstance(strategy_payload, dict):
            logger.error(
                f"Invalid strategy payload: strategy_code={strategy.strategy_code}, "
                f"version={execution.strategy_version}, execution_id={execution.id}"
            )
            return None
        
        # Add metadata for execution context
        execution_context = {
            "strategy_code": strategy.strategy_code,
            "strategy_id": execution.strategy_id,
            "version": execution.strategy_version,
            "execution_id": execution.id,
            "payload": strategy_payload
        }
        
        logger.info(
            f"Strategy loaded: strategy_code={strategy.strategy_code}, "
            f"version={execution.strategy_version}, execution_id={execution.id}"
        )
        
        return execution_context
        
    except Exception as e:
        log_error(
            strategy_code="unknown",
            version=execution.strategy_version if execution else 0,
            error=e,
            context="load_strategy_for_execution"
        )
        return None
