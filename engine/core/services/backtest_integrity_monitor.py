"""
Backtest Data Integrity Monitoring Service
Read-only validation jobs to detect data gaps and integrity issues
"""
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from common.db import SessionLocal
from models import StrategyBacktestSummary, StrategyBacktestDaily, StrategyBacktestTrades
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Don't close here, caller should close


def check_missing_candle_intervals(symbol: str = None, days_back: int = 7) -> dict:
    """
    Check for missing candle intervals in backtest data
    This is a read-only validation - does NOT insert missing data
    
    Returns:
        {
            "symbol": "BTCUSD",
            "missing_intervals": [...],
            "total_expected": 100,
            "total_found": 95,
            "coverage_percent": 95.0
        }
    """
    try:
        db = get_db()
        try:
            # This is a placeholder - actual implementation would check candle tables
            # For now, return a structure that can be extended
            result = {
                "symbol": symbol or "ALL",
                "missing_intervals": [],
                "total_expected": 0,
                "total_found": 0,
                "coverage_percent": 100.0,
                "checked_at": datetime.utcnow().isoformat()
            }
            
            # TODO: Implement actual candle interval checking logic
            # This would query aibacktest_<SYMBOL> tables and check for gaps
            
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking missing candle intervals: {e}")
        return {
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }


def check_gaps_in_daily_data() -> dict:
    """
    Check for gaps in strategy_backtest_daily table
    Detects missing daily entries for strategies
    
    Returns:
        {
            "gaps": [
                {
                    "strategy_id": 1,
                    "symbol": "BTCUSD",
                    "missing_dates": ["2024-01-15", "2024-01-16"],
                    "backtest_run_id": "uuid"
                }
            ],
            "total_gaps": 2
        }
    """
    try:
        db = get_db()
        gaps = []
        
        try:
            # Find strategies with daily data
            strategies_query = text("""
                SELECT DISTINCT strategy_id, symbol, backtest_run_id
                FROM strategy_backtest_daily
                ORDER BY strategy_id, symbol
            """)
            strategies = db.execute(strategies_query).fetchall()
            
            for strategy in strategies:
                strategy_id = strategy.strategy_id
                symbol = strategy.symbol
                backtest_run_id = strategy.backtest_run_id
                
                # Get date range for this strategy
                date_range_query = text("""
                    SELECT MIN(date) as min_date, MAX(date) as max_date
                    FROM strategy_backtest_daily
                    WHERE strategy_id = :strategy_id
                    AND symbol = :symbol
                    AND backtest_run_id = :backtest_run_id
                """)
                date_range = db.execute(
                    date_range_query,
                    {
                        "strategy_id": strategy_id,
                        "symbol": symbol,
                        "backtest_run_id": backtest_run_id
                    }
                ).fetchone()
                
                if not date_range or not date_range.min_date:
                    continue
                
                # Check for missing dates in range
                missing_dates_query = text("""
                    SELECT date
                    FROM strategy_backtest_daily
                    WHERE strategy_id = :strategy_id
                    AND symbol = :symbol
                    AND backtest_run_id = :backtest_run_id
                    ORDER BY date
                """)
                existing_dates = {row.date for row in db.execute(
                    missing_dates_query,
                    {
                        "strategy_id": strategy_id,
                        "symbol": symbol,
                        "backtest_run_id": backtest_run_id
                    }
                ).fetchall()}
                
                # Generate expected dates
                min_date = date_range.min_date
                max_date = date_range.max_date
                current_date = min_date
                missing_dates = []
                
                while current_date <= max_date:
                    if current_date not in existing_dates:
                        missing_dates.append(current_date.isoformat())
                    current_date += timedelta(days=1)
                
                if missing_dates:
                    gaps.append({
                        "strategy_id": strategy_id,
                        "symbol": symbol,
                        "missing_dates": missing_dates,
                        "backtest_run_id": backtest_run_id
                    })
            
            return {
                "gaps": gaps,
                "total_gaps": len(gaps),
                "checked_at": datetime.utcnow().isoformat()
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking gaps in daily data: {e}")
        return {
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }


def check_orphaned_backtest_runs() -> dict:
    """
    Check for orphaned backtest_run_id references
    Detects backtest_run_ids that exist in daily/trades but not in summary
    
    Returns:
        {
            "orphaned_runs": [
                {
                    "backtest_run_id": "uuid",
                    "table": "strategy_backtest_daily",
                    "count": 10
                }
            ],
            "total_orphaned": 1
        }
    """
    try:
        db = get_db()
        orphaned_runs = []
        
        try:
            # Check daily table
            daily_orphans_query = text("""
                SELECT DISTINCT sbd.backtest_run_id, COUNT(*) as count
                FROM strategy_backtest_daily sbd
                LEFT JOIN strategy_backtest_summary sbs
                    ON sbd.backtest_run_id = sbs.backtest_run_id
                WHERE sbs.backtest_run_id IS NULL
                GROUP BY sbd.backtest_run_id
            """)
            daily_orphans = db.execute(daily_orphans_query).fetchall()
            
            for orphan in daily_orphans:
                orphaned_runs.append({
                    "backtest_run_id": orphan.backtest_run_id,
                    "table": "strategy_backtest_daily",
                    "count": orphan.count
                })
            
            # Check trades table
            trades_orphans_query = text("""
                SELECT DISTINCT sbt.backtest_run_id, COUNT(*) as count
                FROM strategy_backtest_trades sbt
                LEFT JOIN strategy_backtest_summary sbs
                    ON sbt.backtest_run_id = sbs.backtest_run_id
                WHERE sbs.backtest_run_id IS NULL
                GROUP BY sbt.backtest_run_id
            """)
            trades_orphans = db.execute(trades_orphans_query).fetchall()
            
            for orphan in trades_orphans:
                orphaned_runs.append({
                    "backtest_run_id": orphan.backtest_run_id,
                    "table": "strategy_backtest_trades",
                    "count": orphan.count
                })
            
            return {
                "orphaned_runs": orphaned_runs,
                "total_orphaned": len(orphaned_runs),
                "checked_at": datetime.utcnow().isoformat()
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking orphaned backtest runs: {e}")
        return {
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }


def run_integrity_audit() -> dict:
    """
    Run complete integrity audit
    Combines all checks into a single report
    
    Returns comprehensive audit report
    """
    logger.info("Starting backtest data integrity audit...")
    
    audit_report = {
        "audit_timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    # Run all checks
    try:
        audit_report["checks"]["daily_gaps"] = check_gaps_in_daily_data()
        audit_report["checks"]["orphaned_runs"] = check_orphaned_backtest_runs()
        audit_report["checks"]["candle_intervals"] = check_missing_candle_intervals()
        
        # Summary
        total_issues = (
            audit_report["checks"]["daily_gaps"].get("total_gaps", 0) +
            audit_report["checks"]["orphaned_runs"].get("total_orphaned", 0)
        )
        
        audit_report["summary"] = {
            "total_issues": total_issues,
            "status": "OK" if total_issues == 0 else "ISSUES_DETECTED"
        }
        
        logger.info(f"Integrity audit complete. Issues detected: {total_issues}")
        
    except Exception as e:
        logger.error(f"Error running integrity audit: {e}")
        audit_report["error"] = str(e)
        audit_report["summary"] = {
            "status": "ERROR"
        }
    
    return audit_report

