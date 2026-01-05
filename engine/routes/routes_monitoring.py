"""
Monitoring & Observability Endpoints
Read-only monitoring endpoints for system observability
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from common.db import SessionLocal
from sqlalchemy import text, func
from models import CronMaster, CronExecutionLog, StrategyBacktestSummary
from core.services.backtest_integrity_monitor import run_integrity_audit
from core.services.cron_alerting import generate_all_alerts
from middleware.api_observability import get_api_metrics, get_critical_api_metrics
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Don't close here, caller should close


@router.get("/monitoring/cron/status")
async def get_cron_status():
    """
    Get overall cron status overview
    Read-only endpoint for admin dashboards
    """
    try:
        db = get_db()
        try:
            # Get cron statistics
            stats_query = text("""
                SELECT 
                    cron_name,
                    cron_type,
                    status,
                    last_run_at,
                    last_success_at,
                    error_message,
                    triggered_by
                FROM cron_master
                ORDER BY last_run_at DESC
            """)
            crons = db.execute(stats_query).fetchall()
            
            # Get execution history (last 24 hours)
            history_query = text("""
                SELECT 
                    cron_name,
                    triggered_by,
                    status,
                    started_at,
                    finished_at,
                    error_message,
                    TIMESTAMPDIFF(SECOND, started_at, finished_at) as duration_seconds
                FROM cron_execution_log
                WHERE started_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                ORDER BY started_at DESC
                LIMIT 100
            """)
            history = db.execute(history_query).fetchall()
            
            # Calculate metrics
            total_crons = len(crons)
            running_count = sum(1 for c in crons if c.status == "RUNNING")
            success_count = sum(1 for c in crons if c.status == "SUCCESS")
            failed_count = sum(1 for c in crons if c.status == "FAILED")
            
            # Recent failures
            recent_failures = [h for h in history if h.status == "FAILED"]
            
            return JSONResponse(
                status_code=200,
                content={
                    "timestamp": datetime.utcnow().isoformat(),
                    "summary": {
                        "total_crons": total_crons,
                        "running": running_count,
                        "success": success_count,
                        "failed": failed_count
                    },
                    "crons": [
                        {
                            "cron_name": c.cron_name,
                            "cron_type": c.cron_type,
                            "status": c.status,
                            "last_run_at": c.last_run_at.isoformat() if c.last_run_at else None,
                            "last_success_at": c.last_success_at.isoformat() if c.last_success_at else None,
                            "error_message": c.error_message,
                            "triggered_by": c.triggered_by
                        }
                        for c in crons
                    ],
                    "recent_history": [
                        {
                            "cron_name": h.cron_name,
                            "triggered_by": h.triggered_by,
                            "status": h.status,
                            "started_at": h.started_at.isoformat() if h.started_at else None,
                            "finished_at": h.finished_at.isoformat() if h.finished_at else None,
                            "duration_seconds": h.duration_seconds,
                            "error_message": h.error_message
                        }
                        for h in history
                    ],
                    "recent_failures_count": len(recent_failures)
                }
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting cron status: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.get("/monitoring/backtest/integrity")
async def get_backtest_integrity():
    """
    Run backtest data integrity audit
    Read-only validation - does NOT fix issues
    """
    try:
        audit_report = run_integrity_audit()
        return JSONResponse(
            status_code=200,
            content=audit_report
        )
    except Exception as e:
        logger.error(f"Error running integrity audit: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.get("/monitoring/api/metrics")
async def get_api_metrics_endpoint():
    """
    Get API observability metrics
    Returns request count, latency, and error rates per endpoint
    """
    try:
        metrics = get_api_metrics()
        return JSONResponse(
            status_code=200,
            content=metrics
        )
    except Exception as e:
        logger.error(f"Error getting API metrics: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.get("/monitoring/api/metrics/critical")
async def get_critical_api_metrics_endpoint():
    """
    Get metrics for critical performance APIs only
    Filters to performance-related endpoints
    """
    try:
        metrics = get_critical_api_metrics()
        return JSONResponse(
            status_code=200,
            content=metrics
        )
    except Exception as e:
        logger.error(f"Error getting critical API metrics: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.get("/monitoring/alerts")
async def get_alerts():
    """
    Get current cron alerts
    Returns all active alerts (stuck crons, failures, etc.)
    """
    try:
        alerts = generate_all_alerts()
        return JSONResponse(
            status_code=200,
            content=alerts
        )
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.get("/monitoring/backtest/stats")
async def get_backtest_stats():
    """
    Get backtest statistics
    Read-only metrics for dashboards
    """
    try:
        db = get_db()
        try:
            # Total backtest runs
            total_runs_query = text("""
                SELECT COUNT(DISTINCT backtest_run_id) as total_runs
                FROM strategy_backtest_summary
            """)
            total_runs = db.execute(total_runs_query).fetchone().total_runs or 0
            
            # Runs by symbol
            runs_by_symbol_query = text("""
                SELECT symbol, COUNT(DISTINCT backtest_run_id) as run_count
                FROM strategy_backtest_summary
                GROUP BY symbol
            """)
            runs_by_symbol = db.execute(runs_by_symbol_query).fetchall()
            
            # Recent runs (last 7 days)
            recent_runs_query = text("""
                SELECT COUNT(DISTINCT backtest_run_id) as recent_runs
                FROM strategy_backtest_summary
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            """)
            recent_runs = db.execute(recent_runs_query).fetchone().recent_runs or 0
            
            return JSONResponse(
                status_code=200,
                content={
                    "timestamp": datetime.utcnow().isoformat(),
                    "summary": {
                        "total_runs": total_runs,
                        "recent_runs_7d": recent_runs
                    },
                    "runs_by_symbol": [
                        {
                            "symbol": r.symbol,
                            "run_count": r.run_count
                        }
                        for r in runs_by_symbol
                    ]
                }
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting backtest stats: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

