"""
Daily Audit Cron Job
Read-only validation job that runs daily to check data integrity
Does NOT execute backtests or modify data
"""
from core.services.backtest_integrity_monitor import run_integrity_audit
from core.services.cron_alerting import generate_all_alerts, send_alert
from common.db import SessionLocal
from models import CronMaster, CronExecutionLog, CronStatus, CronTriggeredBy
from datetime import datetime
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


def get_db() -> Session:
    """Get database session"""
    return SessionLocal()


def run_daily_audit():
    """
    Run daily audit cron job
    This is a READ-ONLY job that:
    1. Runs backtest integrity audit
    2. Generates cron alerts
    3. Logs findings
    4. Does NOT execute backtests or modify data
    """
    cron_name = "DAILY_AUDIT"
    db = get_db()
    
    try:
        # Create or update cron master entry
        cron_master = db.query(CronMaster).filter(
            CronMaster.cron_name == cron_name
        ).first()
        
        if not cron_master:
            cron_master = CronMaster(
                cron_name=cron_name,
                cron_type="DAILY",
                status=CronStatus.RUNNING,
                last_run_at=datetime.utcnow(),
                triggered_by=CronTriggeredBy.SYSTEM
            )
            db.add(cron_master)
        else:
            cron_master.status = CronStatus.RUNNING
            cron_master.last_run_at = datetime.utcnow()
            cron_master.error_message = None
        
        db.commit()
        
        # Create execution log entry
        execution_log = CronExecutionLog(
            cron_name=cron_name,
            triggered_by=CronTriggeredBy.SYSTEM,
            started_at=datetime.utcnow(),
            status=CronStatus.RUNNING
        )
        db.add(execution_log)
        db.commit()
        execution_log_id = execution_log.id
        
        logger.info(f"Starting daily audit cron: {cron_name}")
        
        audit_results = {}
        error_occurred = False
        error_message = None
        
        try:
            # 1. Run backtest integrity audit
            logger.info("Running backtest integrity audit...")
            integrity_report = run_integrity_audit()
            audit_results["integrity"] = integrity_report
            
            # 2. Generate cron alerts
            logger.info("Generating cron alerts...")
            alerts = generate_all_alerts()
            audit_results["alerts"] = alerts
            
            # 3. Send critical alerts
            critical_alerts = [a for a in alerts["alerts"] if a["severity"] == "CRITICAL"]
            for alert in critical_alerts:
                send_alert(alert, channel="log")
            
            logger.info(f"Daily audit complete. Issues: {integrity_report.get('summary', {}).get('total_issues', 0)}, Alerts: {alerts.get('summary', {}).get('total', 0)}")
            
        except Exception as e:
            error_occurred = True
            error_message = str(e)
            logger.error(f"Error during daily audit: {e}", exc_info=True)
        
        # Update execution log
        execution_log.finished_at = datetime.utcnow()
        execution_log.status = CronStatus.FAILED if error_occurred else CronStatus.SUCCESS
        execution_log.error_message = error_message
        db.commit()
        
        # Update cron master
        cron_master.status = CronStatus.FAILED if error_occurred else CronStatus.SUCCESS
        cron_master.last_success_at = datetime.utcnow() if not error_occurred else cron_master.last_success_at
        cron_master.error_message = error_message
        db.commit()
        
        logger.info(f"Daily audit cron completed: {cron_name} - Status: {cron_master.status}")
        
        return {
            "success": not error_occurred,
            "results": audit_results,
            "error": error_message
        }
        
    except Exception as e:
        logger.error(f"Fatal error in daily audit cron: {e}", exc_info=True)
        
        # Mark as failed
        try:
            cron_master = db.query(CronMaster).filter(
                CronMaster.cron_name == cron_name
            ).first()
            if cron_master:
                cron_master.status = CronStatus.FAILED
                cron_master.error_message = str(e)
                db.commit()
        except:
            pass
        
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()


if __name__ == "__main__":
    # Allow running as standalone script for testing
    run_daily_audit()

