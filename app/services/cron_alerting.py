"""
Cron Alerting Service
Read-only inspection of cron status and generates alerts
Does NOT modify cron execution logic
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from common.db import SessionLocal
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def get_db() -> Session:
    """Get database session"""
    return SessionLocal()


def check_stuck_crons(threshold_minutes: int = 30) -> list:
    """
    Check for crons stuck in RUNNING state
    Returns list of stuck cron alerts
    """
    try:
        db = get_db()
        try:
            query = text("""
                SELECT cron_name, status, last_run_at, 
                       TIMESTAMPDIFF(MINUTE, last_run_at, NOW()) as minutes_running
                FROM cron_master
                WHERE status = 'RUNNING'
                AND TIMESTAMPDIFF(MINUTE, last_run_at, NOW()) > :threshold
            """)
            stuck_crons = db.execute(query, {"threshold": threshold_minutes}).fetchall()
            
            alerts = []
            for cron in stuck_crons:
                alerts.append({
                    "severity": "CRITICAL",
                    "type": "STUCK_CRON",
                    "cron_name": cron.cron_name,
                    "message": f"Cron '{cron.cron_name}' stuck in RUNNING state for {cron.minutes_running} minutes",
                    "minutes_running": cron.minutes_running,
                    "last_run_at": cron.last_run_at.isoformat() if cron.last_run_at else None
                })
            
            return alerts
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking stuck crons: {e}")
        return []


def check_consecutive_failures(consecutive_count: int = 2) -> list:
    """
    Check for consecutive cron failures
    Returns list of failure alerts
    """
    try:
        db = get_db()
        try:
            query = text("""
                SELECT cron_name, COUNT(*) as failure_count,
                       MAX(started_at) as last_failure_at
                FROM cron_execution_log
                WHERE status = 'FAILED'
                AND started_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                GROUP BY cron_name
                HAVING failure_count >= :consecutive_count
            """)
            failures = db.execute(query, {"consecutive_count": consecutive_count}).fetchall()
            
            alerts = []
            for failure in failures:
                alerts.append({
                    "severity": "WARNING",
                    "type": "CONSECUTIVE_FAILURES",
                    "cron_name": failure.cron_name,
                    "message": f"Cron '{failure.cron_name}' failed {failure.failure_count} times in last 24 hours",
                    "failure_count": failure.failure_count,
                    "last_failure_at": failure.last_failure_at.isoformat() if failure.last_failure_at else None
                })
            
            return alerts
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking consecutive failures: {e}")
        return []


def check_missed_daily_crons() -> list:
    """
    Check for missed daily cron executions
    Returns list of missed cron alerts
    """
    try:
        db = get_db()
        try:
            query = text("""
                SELECT cron_name, last_success_at, 
                       TIMESTAMPDIFF(HOUR, last_success_at, NOW()) as hours_since_success
                FROM cron_master
                WHERE cron_type = 'DAILY'
                AND (last_success_at IS NULL OR TIMESTAMPDIFF(HOUR, last_success_at, NOW()) > 25)
            """)
            missed_crons = db.execute(query).fetchall()
            
            alerts = []
            for cron in missed_crons:
                hours_since = cron.hours_since_success if cron.hours_since_success else 999
                alerts.append({
                    "severity": "WARNING",
                    "type": "MISSED_DAILY_CRON",
                    "cron_name": cron.cron_name,
                    "message": f"Daily cron '{cron.cron_name}' missed - last success {hours_since} hours ago",
                    "hours_since_success": hours_since,
                    "last_success_at": cron.last_success_at.isoformat() if cron.last_success_at else None
                })
            
            return alerts
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking missed daily crons: {e}")
        return []


def check_duration_anomalies() -> list:
    """
    Check for cron execution duration anomalies
    Detects crons taking unusually long or short time
    """
    try:
        db = get_db()
        try:
            # Get average duration per cron from last 7 days
            avg_duration_query = text("""
                SELECT cron_name, 
                       AVG(TIMESTAMPDIFF(SECOND, started_at, finished_at)) as avg_duration_seconds,
                       COUNT(*) as execution_count
                FROM cron_execution_log
                WHERE status = 'SUCCESS'
                AND started_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                GROUP BY cron_name
                HAVING execution_count >= 3
            """)
            avg_durations = db.execute(avg_duration_query).fetchall()
            
            alerts = []
            for avg_row in avg_durations:
                cron_name = avg_row.cron_name
                avg_duration = avg_row.avg_duration_seconds or 0
                
                # Get recent execution duration
                recent_query = text("""
                    SELECT TIMESTAMPDIFF(SECOND, started_at, finished_at) as duration_seconds
                    FROM cron_execution_log
                    WHERE cron_name = :cron_name
                    AND status = 'SUCCESS'
                    ORDER BY started_at DESC
                    LIMIT 1
                """)
                recent = db.execute(recent_query, {"cron_name": cron_name}).fetchone()
                
                if recent and recent.duration_seconds:
                    # Alert if duration is 3x longer or 3x shorter than average
                    if recent.duration_seconds > avg_duration * 3 and avg_duration > 0:
                        alerts.append({
                            "severity": "WARNING",
                            "type": "DURATION_ANOMALY",
                            "cron_name": cron_name,
                            "message": f"Cron '{cron_name}' took {recent.duration_seconds}s (avg: {avg_duration:.1f}s) - 3x longer than average",
                            "duration_seconds": recent.duration_seconds,
                            "avg_duration_seconds": round(avg_duration, 1)
                        })
                    elif recent.duration_seconds < avg_duration / 3 and avg_duration > 0:
                        alerts.append({
                            "severity": "INFO",
                            "type": "DURATION_ANOMALY",
                            "cron_name": cron_name,
                            "message": f"Cron '{cron_name}' took {recent.duration_seconds}s (avg: {avg_duration:.1f}s) - 3x shorter than average",
                            "duration_seconds": recent.duration_seconds,
                            "avg_duration_seconds": round(avg_duration, 1)
                        })
            
            return alerts
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking duration anomalies: {e}")
        return []


def generate_all_alerts() -> dict:
    """
    Generate all cron alerts
    Returns comprehensive alert report
    """
    logger.info("Generating cron alerts...")
    
    alerts = {
        "timestamp": datetime.utcnow().isoformat(),
        "alerts": []
    }
    
    # Run all checks
    alerts["alerts"].extend(check_stuck_crons(threshold_minutes=30))
    alerts["alerts"].extend(check_consecutive_failures(consecutive_count=2))
    alerts["alerts"].extend(check_missed_daily_crons())
    alerts["alerts"].extend(check_duration_anomalies())
    
    # Categorize by severity
    critical = [a for a in alerts["alerts"] if a["severity"] == "CRITICAL"]
    warnings = [a for a in alerts["alerts"] if a["severity"] == "WARNING"]
    info = [a for a in alerts["alerts"] if a["severity"] == "INFO"]
    
    alerts["summary"] = {
        "total": len(alerts["alerts"]),
        "critical": len(critical),
        "warnings": len(warnings),
        "info": len(info)
    }
    
    logger.info(f"Generated {len(alerts['alerts'])} alerts: {len(critical)} critical, {len(warnings)} warnings, {len(info)} info")
    
    return alerts


def send_alert(alert: dict, channel: str = "log") -> bool:
    """
    Send alert via specified channel
    Currently supports: log, email (future), slack (future)
    
    This is a placeholder - actual implementation would integrate with:
    - Email service (SMTP/SendGrid)
    - Slack webhook
    - Telegram bot
    """
    try:
        if channel == "log":
            # Log alert
            if alert["severity"] == "CRITICAL":
                logger.critical(f"ðŸš¨ CRITICAL ALERT: {alert['message']}")
            elif alert["severity"] == "WARNING":
                logger.warning(f"âš ï¸ WARNING: {alert['message']}")
            else:
                logger.info(f"â„¹ï¸ INFO: {alert['message']}")
            return True
        
        # Future: Email alert
        # elif channel == "email":
        #     send_email_alert(alert)
        #     return True
        
        # Future: Slack alert
        # elif channel == "slack":
        #     send_slack_alert(alert)
        #     return True
        
        return False
    except Exception as e:
        logger.error(f"Error sending alert: {e}")
        return False

