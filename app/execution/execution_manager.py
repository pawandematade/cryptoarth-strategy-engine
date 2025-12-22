"""
Execution Manager
Manages all strategy execution loops.
Polls database for ACTIVE executions and starts/stops loops accordingly.
"""
import logging
import time
import threading
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
from app.database import get_db
from app.models import StrategyExecution, ExecutionStatus
from app.execution.execution_loop import ExecutionLoop
from app.execution.execution_logger import (
    log_execution_start,
    log_execution_stop,
    log_error
)

logger = logging.getLogger("execution_engine.execution_manager")


class ExecutionManager:
    """
    Execution Manager
    
    Polls database for ACTIVE strategy executions and manages execution loops.
    Runs in background thread, checking DB periodically.
    """
    
    def __init__(
        self,
        poll_interval_seconds: float = 10.0,
        tick_interval_seconds: float = 5.0
    ):
        """
        Initialize execution manager.
        
        Args:
            poll_interval_seconds: How often to poll DB for execution changes (default 10s)
            tick_interval_seconds: How often each execution loop generates ticks (default 5s)
        """
        self.poll_interval_seconds = poll_interval_seconds
        self.tick_interval_seconds = tick_interval_seconds
        self.is_running = False
        self.should_stop = False
        self.manager_thread: Optional[threading.Thread] = None
        self.active_loops: Dict[int, ExecutionLoop] = {}
        self.lock = threading.Lock()
        
        # Create database engine and session factory
        # Handle empty password for XAMPP (local development)
        if DB_PASSWORD:
            db_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        else:
            # Empty password - XAMPP default
            db_url = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        self.db_engine = create_engine(db_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.db_engine)
    
    def start(self):
        """Start execution manager"""
        if self.is_running:
            logger.warning("Execution manager already running")
            return
        
        self.should_stop = False
        self.is_running = True
        
        logger.info("Execution Manager starting...")
        logger.info(f"Poll interval: {self.poll_interval_seconds}s")
        logger.info(f"Tick interval: {self.tick_interval_seconds}s")
        
        self.manager_thread = threading.Thread(target=self._run_manager, daemon=True)
        self.manager_thread.start()
    
    def stop(self):
        """Stop execution manager and all execution loops"""
        if not self.is_running:
            return
        
        logger.info("Execution Manager stopping...")
        self.should_stop = True
        
        # Stop all active loops
        with self.lock:
            for execution_id, loop in list(self.active_loops.items()):
                try:
                    loop.stop(reason="Manager stopping")
                    loop.join(timeout=5.0)
                except Exception as e:
                    logger.error(f"Error stopping loop for execution_id={execution_id}: {e}")
            
            self.active_loops.clear()
        
        if self.manager_thread and self.manager_thread.is_alive():
            self.manager_thread.join(timeout=10.0)
        
        self.is_running = False
        logger.info("Execution Manager stopped")
    
    def _run_manager(self):
        """Main manager loop (runs in thread)"""
        logger.info("Execution Manager started")
        
        try:
            while not self.should_stop:
                try:
                    # Create new DB session for polling
                    db = self.SessionLocal()
                    try:
                        self._sync_executions(db)
                    finally:
                        db.close()
                except Exception as e:
                    logger.error(f"Error in execution manager sync: {e}", exc_info=True)
                
                # Wait before next poll
                time.sleep(self.poll_interval_seconds)
        except Exception as e:
            logger.error(f"Fatal error in execution manager: {e}", exc_info=True)
        finally:
            self.is_running = False
            logger.info("Execution Manager thread exited")
    
    def _sync_executions(self, db: Session):
        """
        Sync execution loops with database state.
        
        - Starts loops for newly ACTIVE executions
        - Stops loops for executions that are no longer ACTIVE
        - Updates loops for status changes (paused/resumed)
        """
        try:
            # Query all ACTIVE executions
            active_executions = db.query(StrategyExecution).filter(
                StrategyExecution.status == ExecutionStatus.active
            ).all()
            
            active_execution_ids = {ex.id for ex in active_executions}
            
            with self.lock:
                # Start loops for new ACTIVE executions
                for execution in active_executions:
                    if execution.id not in self.active_loops:
                        try:
                            logger.info(
                                f"Starting execution loop: execution_id={execution.id}, "
                                f"strategy_id={execution.strategy_id}, "
                                f"version={execution.strategy_version}"
                            )
                            
                            loop = ExecutionLoop(
                                db_session_factory=self.SessionLocal,
                                execution=execution,
                                tick_interval_seconds=self.tick_interval_seconds
                            )
                            loop.start()
                            self.active_loops[execution.id] = loop
                            
                        except Exception as e:
                            logger.error(
                                f"Failed to start execution loop for "
                                f"execution_id={execution.id}: {e}",
                                exc_info=True
                            )
                
                # Stop loops for executions that are no longer ACTIVE
                loops_to_remove = []
                for execution_id, loop in self.active_loops.items():
                    if execution_id not in active_execution_ids:
                        try:
                            logger.info(
                                f"Stopping execution loop: execution_id={execution_id} "
                                f"(no longer ACTIVE)"
                            )
                            loop.stop(reason="Execution status changed")
                            loop.join(timeout=5.0)
                            loops_to_remove.append(execution_id)
                        except Exception as e:
                            logger.error(
                                f"Error stopping loop for execution_id={execution_id}: {e}",
                                exc_info=True
                            )
                            loops_to_remove.append(execution_id)
                
                # Remove stopped loops
                for execution_id in loops_to_remove:
                    self.active_loops.pop(execution_id, None)
                
                logger.debug(
                    f"Execution sync complete: "
                    f"{len(self.active_loops)} active loops, "
                    f"{len(active_execution_ids)} ACTIVE executions in DB"
                )
        
        except Exception as e:
            logger.error(f"Error syncing executions: {e}", exc_info=True)
    
    def get_active_loop_count(self) -> int:
        """Get count of active execution loops"""
        with self.lock:
            return len(self.active_loops)
    
    def get_active_execution_ids(self) -> list[int]:
        """Get list of active execution IDs"""
        with self.lock:
            return list(self.active_loops.keys())
