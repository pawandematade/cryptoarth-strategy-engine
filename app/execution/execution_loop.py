"""
Execution Loop
Runs execution loop for a single strategy (mock data only).
"""
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
from app.models import StrategyExecution, ExecutionStatus
from app.execution.strategy_loader import load_strategy_for_execution
from app.execution.decision_engine import evaluate_strategy
from app.execution.execution_logger import (
    log_execution_start,
    log_execution_stop,
    log_execution_pause,
    log_execution_resume,
    log_tick_processed,
    log_state_change,
    log_error
)

logger = logging.getLogger("execution_engine.execution_loop")


class ExecutionLoop:
    """
    Execution loop for a single strategy.
    
    Runs continuously while execution status is ACTIVE,
    generating mock ticks and evaluating strategy decisions.
    """
    
    def __init__(
        self,
        db_session_factory: sessionmaker,
        execution: StrategyExecution,
        tick_interval_seconds: float = 5.0
    ):
        """
        Initialize execution loop.
        
        Args:
            db_session_factory: Database session factory (for creating fresh sessions)
            execution: StrategyExecution model instance
            tick_interval_seconds: Interval between ticks (default 5 seconds)
        """
        self.db_session_factory = db_session_factory
        self.execution_id = execution.id
        self.execution_strategy_id = execution.strategy_id
        self.execution_version = execution.strategy_version
        self.tick_interval_seconds = tick_interval_seconds
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.should_stop = False
        self.strategy_context: Optional[Dict[str, Any]] = None
        
        # Load strategy once (using temporary session)
        db = db_session_factory()
        try:
            # Reload execution to get fresh copy
            execution_copy = db.query(StrategyExecution).filter(
                StrategyExecution.id == execution.id
            ).first()
            if execution_copy:
                self.strategy_context = load_strategy_for_execution(db, execution_copy)
        finally:
            db.close()
        
        if not self.strategy_context:
            raise ValueError(f"Failed to load strategy for execution_id={execution.id}")
    
    def start(self):
        """Start execution loop in a separate thread"""
        if self.is_running:
            logger.warning(f"Execution loop already running: execution_id={self.execution_id}")
            return
        
        self.should_stop = False
        self.is_running = True
        
        strategy_code = self.strategy_context["strategy_code"]
        version = self.strategy_context["version"]
        
        log_execution_start(
            strategy_code=strategy_code,
            version=version,
            execution_id=self.execution_id
        )
        
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
    
    def stop(self, reason: str = "Requested"):
        """Stop execution loop"""
        if not self.is_running:
            return
        
        self.should_stop = True
        
        strategy_code = self.strategy_context["strategy_code"] if self.strategy_context else "UNKNOWN"
        version = self.strategy_context["version"] if self.strategy_context else 0
        
        log_execution_stop(
            strategy_code=strategy_code,
            version=version,
            execution_id=self.execution_id,
            reason=reason
        )
    
    def _run_loop(self):
        """Main execution loop (runs in thread)"""
        try:
            strategy_code = self.strategy_context["strategy_code"]
            version = self.strategy_context["version"]
            strategy_payload = self.strategy_context["payload"]
            symbol = strategy_payload.get("symbol", "BTCUSD")
            
            # Mock price generator (simple sine wave for demo)
            base_price = 50000.0  # Starting price
            price_amplitude = 1000.0  # Price variation
            tick_count = 0
            
            while not self.should_stop:
                # Create fresh DB session for this iteration (read-only)
                db = self.db_session_factory()
                try:
                    # Check execution status in DB (read-only)
                    current_execution = db.query(StrategyExecution).filter(
                        StrategyExecution.id == self.execution_id
                    ).first()
                    
                    if not current_execution:
                        logger.warning(f"Execution not found in DB: execution_id={self.execution_id}")
                        break
                    
                    # Handle status changes
                    if current_execution.status == ExecutionStatus.STOPPED:
                        log_state_change(strategy_code, version, "active", "stopped")
                        break
                
                    elif current_execution.status == ExecutionStatus.PAUSED:
                        if last_status != ExecutionStatus.PAUSED:
                            log_execution_pause(strategy_code, version, self.execution_id)
                        last_status = ExecutionStatus.PAUSED
                        # Sleep longer when paused
                        time.sleep(self.tick_interval_seconds * 2)
                        continue
                    
                    elif current_execution.status == ExecutionStatus.ACTIVE:
                        if last_status == ExecutionStatus.PAUSED:
                            log_execution_resume(strategy_code, version, self.execution_id)
                            log_state_change(strategy_code, version, "paused", "active")
                        last_status = ExecutionStatus.ACTIVE
                        
                        # Generate mock market data
                        tick_count += 1
                        mock_price = base_price + price_amplitude * (tick_count % 100) / 100
                        timestamp = datetime.now(timezone.utc).isoformat()
                        
                        market_data = {
                            "symbol": symbol,
                            "price": mock_price,
                            "timestamp": timestamp,
                            "tick_count": tick_count
                        }
                        
                        # Add execution context to strategy payload for logging
                        strategy_with_context = strategy_payload.copy()
                        strategy_with_context["execution_context"] = {
                            "strategy_code": strategy_code,
                            "version": version,
                            "execution_id": self.execution_id
                        }
                        
                        # Log tick
                        log_tick_processed(strategy_code, version, symbol, timestamp, mock_price)
                        
                        # Evaluate strategy and get decision
                        decision, reason = evaluate_strategy(strategy_with_context, market_data)
                        
                        # DRY-RUN: Decision is logged, no action taken
                        # In real implementation, decision would trigger order placement
                    
                    else:
                        # INACTIVE or unknown status
                        logger.warning(
                            f"Execution status is {current_execution.status.value}: "
                            f"execution_id={self.execution_id}"
                        )
                        break
                finally:
                    # Close DB session
                    db.close()
                
                # Wait before next tick
                time.sleep(self.tick_interval_seconds)
            
        except Exception as e:
            strategy_code = self.strategy_context["strategy_code"] if self.strategy_context else "UNKNOWN"
            version = self.strategy_context["version"] if self.strategy_context else 0
            log_error(strategy_code, version, e, "execution_loop._run_loop")
        finally:
            self.is_running = False
    
    def join(self, timeout: Optional[float] = None):
        """Wait for execution loop thread to finish"""
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
