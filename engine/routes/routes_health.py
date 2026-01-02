"""
Health Check Endpoints
Read-only health monitoring for Strategy Engine
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
from common.db import test_db_connection, SessionLocal
from common.redis import redis_client
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from app.models import CronMaster, CronExecutionLog
from sqlalchemy.orm import Session
import logging
import shutil
import os

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Don't close here, caller should close


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint
    Returns OK if service is running
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "OK",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "CryptoArth Strategy Engine",
            "details": {
                "uptime": "operational"
            }
        }
    )


@router.get("/health/db")
async def health_db():
    """
    Database health check
    Tests DB connectivity and returns status
    """
    try:
        db_connected = test_db_connection()
        
        if not db_connected:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "UNHEALTHY",
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "Database",
                    "details": {
                        "connected": False,
                        "error": "Database connection failed"
                    }
                }
            )
        
        # Test query
        db = SessionLocal()
        try:
            result = db.execute(text("SELECT 1 as test"))
            result.fetchone()
            query_ok = True
        except Exception as e:
            logger.error(f"Database query test failed: {e}")
            query_ok = False
        finally:
            db.close()
        
        return JSONResponse(
            status_code=200 if query_ok else 503,
            content={
                "status": "OK" if query_ok else "UNHEALTHY",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Database",
                "details": {
                    "connected": True,
                    "query_test": query_ok
                }
            }
        )
    except Exception as e:
        logger.error(f"Database health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "UNHEALTHY",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Database",
                "details": {
                    "connected": False,
                    "error": str(e)
                }
            }
        )


@router.get("/health/cron")
async def health_cron():
    """
    Cron monitoring health check
    Checks cron execution status and detects issues
    """
    try:
        db = SessionLocal()
        issues = []
        warnings = []
        
        try:
            # Check for stuck crons (RUNNING > 30 minutes)
            stuck_threshold_minutes = 30
            stuck_query = text("""
                SELECT cron_name, status, last_run_at, TIMESTAMPDIFF(MINUTE, last_run_at, NOW()) as minutes_running
                FROM cron_master
                WHERE status = 'RUNNING'
                AND TIMESTAMPDIFF(MINUTE, last_run_at, NOW()) > :threshold
            """)
            stuck_crons = db.execute(stuck_query, {"threshold": stuck_threshold_minutes}).fetchall()
            
            for cron in stuck_crons:
                issues.append({
                    "type": "CRITICAL",
                    "message": f"Cron '{cron.cron_name}' stuck in RUNNING state for {cron.minutes_running} minutes",
                    "cron_name": cron.cron_name,
                    "minutes_running": cron.minutes_running
                })
            
            # Check for consecutive failures
            failure_query = text("""
                SELECT cron_name, COUNT(*) as failure_count
                FROM cron_execution_log
                WHERE status = 'FAILED'
                AND started_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                GROUP BY cron_name
                HAVING failure_count >= 2
            """)
            consecutive_failures = db.execute(failure_query).fetchall()
            
            for failure in consecutive_failures:
                warnings.append({
                    "type": "WARNING",
                    "message": f"Cron '{failure.cron_name}' failed {failure.failure_count} times in last 24 hours",
                    "cron_name": failure.cron_name,
                    "failure_count": failure.failure_count
                })
            
            # Check for missed daily crons (should run daily but last_success_at > 25 hours ago)
            missed_query = text("""
                SELECT cron_name, last_success_at, TIMESTAMPDIFF(HOUR, last_success_at, NOW()) as hours_since_success
                FROM cron_master
                WHERE cron_type = 'DAILY'
                AND (last_success_at IS NULL OR TIMESTAMPDIFF(HOUR, last_success_at, NOW()) > 25)
            """)
            missed_crons = db.execute(missed_query).fetchall()
            
            for cron in missed_crons:
                hours_since = cron.hours_since_success if cron.hours_since_success else 999
                warnings.append({
                    "type": "WARNING",
                    "message": f"Daily cron '{cron.cron_name}' missed - last success {hours_since} hours ago",
                    "cron_name": cron.cron_name,
                    "hours_since_success": hours_since
                })
            
            # Get overall cron stats
            stats_query = text("""
                SELECT 
                    COUNT(*) as total_crons,
                    SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) as running_count,
                    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count
                FROM cron_master
            """)
            stats = db.execute(stats_query).fetchone()
            
            overall_status = "OK"
            if issues:
                overall_status = "CRITICAL"
            elif warnings:
                overall_status = "WARNING"
            
            return JSONResponse(
                status_code=200 if overall_status == "OK" else 503,
                content={
                    "status": overall_status,
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "Cron Monitoring",
                    "details": {
                        "total_crons": stats.total_crons or 0,
                        "running": stats.running_count or 0,
                        "success": stats.success_count or 0,
                        "failed": stats.failed_count or 0,
                        "issues": issues,
                        "warnings": warnings
                    }
                }
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Cron health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "UNHEALTHY",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Cron Monitoring",
                "details": {
                    "error": str(e)
                }
            }
        )


@router.get("/health/redis")
async def health_redis():
    """
    Redis health check
    Tests Redis connectivity
    """
    if redis_client is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "UNHEALTHY",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Redis",
                "details": {
                    "connected": False,
                    "error": "Redis not configured (REDIS_HOST missing)"
                }
            }
        )
    try:
        result = redis_client.ping()
        return JSONResponse(
            status_code=200,
            content={
                "status": "OK",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Redis",
                "details": {
                    "connected": result
                }
            }
        )
    except RedisConnectionError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "UNHEALTHY",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Redis",
                "details": {
                    "connected": False,
                    "error": "Could not connect to Redis"
                }
            }
        )
    except Exception as e:
        logger.error(f"Redis health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "UNHEALTHY",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Redis",
                "details": {
                    "connected": False,
                    "error": str(e)
                }
            }
        )


@router.get("/health/disk")
async def health_disk():
    """
    Disk space health check (optional)
    Checks available disk space
    """
    try:
        total, used, free = shutil.disk_usage("/")
        free_percent = (free / total) * 100
        
        status = "OK"
        if free_percent < 10:
            status = "CRITICAL"
        elif free_percent < 20:
            status = "WARNING"
        
        return JSONResponse(
            status_code=200 if status == "OK" else 503,
            content={
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Disk Space",
                "details": {
                    "total_gb": round(total / (1024**3), 2),
                    "used_gb": round(used / (1024**3), 2),
                    "free_gb": round(free / (1024**3), 2),
                    "free_percent": round(free_percent, 2)
                }
            }
        )
    except Exception as e:
        logger.error(f"Disk health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "UNHEALTHY",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "Disk Space",
                "details": {
                    "error": str(e)
                }
            }
        )

