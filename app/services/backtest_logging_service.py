"""
Backtest Logging Service
Logs backtest executions to strategy_executions table for History tab tracking.
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.models import Strategy, StrategyVersion, StrategyExecution, ExecutionStatus

logger = logging.getLogger(__name__)


def log_backtest_execution(
    db: Session,
    strategy_id: int,
    strategy_version: int,
    run_source: str,
    backtest_results: Optional[Dict[str, Any]] = None
) -> Optional[StrategyExecution]:
    """
    Log a backtest execution to strategy_executions table.
    
    CRITICAL: This creates a record for History tab tracking.
    Backtests are logged as INACTIVE executions with run_source='ai_backtest' or 'manual_backtest'.
    
    Args:
        db: Database session
        strategy_id: Strategy ID
        strategy_version: Version number that was backtested
        run_source: 'ai_backtest' or 'manual_backtest'
        backtest_results: Optional backtest results to extract PnL/trades from
    
    Returns:
        StrategyExecution record if created, None otherwise
    
    Raises:
        ValueError: If run_source is invalid
    """
    # Validate run_source
    if run_source not in ['ai_backtest', 'manual_backtest']:
        raise ValueError(f"Invalid run_source: {run_source}. Must be 'ai_backtest' or 'manual_backtest'")
    
    try:
        # Verify strategy exists
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        if not strategy:
            logger.error(f"❌ Strategy {strategy_id} not found, cannot log backtest")
            return None
        
        # Verify version exists
        version = db.query(StrategyVersion).filter(
            StrategyVersion.strategy_id == strategy_id,
            StrategyVersion.version == strategy_version
        ).first()
        if not version:
            logger.error(f"❌ Strategy version {strategy_id}:v{strategy_version} not found, cannot log backtest")
            return None
        
        # CRITICAL: Update version's backtest_snapshot with results (for History API to extract PnL/trades)
        if backtest_results and isinstance(backtest_results, dict):
            version.backtest_snapshot = backtest_results
            logger.info(f"✅ Updated backtest_snapshot for strategy {strategy_id} version {strategy_version}")
        
        # Create execution record for backtest (INACTIVE status - not a live execution)
        # MANDATORY: Explicitly set run_source - DO NOT rely on DB defaults
        execution = StrategyExecution(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            status=ExecutionStatus.inactive,  # Backtests are not active executions
            run_source=run_source,  # MANDATORY: Explicitly set - Track source of backtest
            activated_at=None,  # Not activated (it's a backtest)
            deactivated_at=None
        )
        
        # VALIDATION: Ensure run_source is set before adding to session
        if not execution.run_source:
            raise ValueError(f"CRITICAL: execution.run_source must be explicitly set (got None). Expected: {run_source}")
        
        logger.info(f"StrategyExecution run_source={execution.run_source}")
        
        # CRITICAL: Add and commit - MUST succeed for History tab
        db.add(execution)
        db.flush()  # Get execution.id before commit
        
        # Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"✅ Backtest execution logged successfully: strategy_id={strategy_id}, "
            f"version={strategy_version}, run_source={run_source}, execution_id={execution.id}"
        )
        
        return execution
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to log backtest execution: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        # Don't fail the backtest if logging fails, but log the error
        return None

