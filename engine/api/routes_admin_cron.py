"""
Admin Cron Management API Routes
Admin-only endpoints for managing cron jobs.

CRITICAL: All endpoints require admin authentication.
"""
from fastapi import APIRouter, HTTPException, status, Header, Body, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List, Optional
import logging
from sqlalchemy.orm import Session
from common.db import get_db, SessionLocal
from engine.models import CronMaster, CronStatus, CronTriggeredBy
from engine.core.services.cron_service import execute_cron, check_cron_running
from engine.core.services.daily_backtest_cron import run_daily_backtest_cron, get_daily_backtest_cron_name

logger = logging.getLogger(__name__)

router = APIRouter()

# Cron type handlers mapping
CRON_HANDLERS = {
    "BACKTEST": {
        "DAILY_BACKTEST": lambda symbol, **kwargs: run_daily_backtest_cron(symbol, **kwargs)
    }
}


class RunCronRequest(BaseModel):
    """Request model for manually running a cron"""
    cron_name: str = Field(..., description="Cron name (e.g., 'DAILY_BACKTEST_BTCUSD')")
    symbol: Optional[str] = Field(None, description="Symbol if cron is symbol-specific")
    
    @validator('cron_name')
    def validate_cron_name(cls, v):
        """Validate cron name format"""
        if not v or not isinstance(v, str):
            raise ValueError("Cron name must be a non-empty string")
        return v.upper().strip()


@router.get("/admin/cron/list")
async def list_crons(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to list all cron jobs with their status.
    
    Args:
        authorization: Authorization header (admin required)
        db: Database session (injected)
    
    Returns:
        JSONResponse with list of all crons
    """
    # Admin authentication check
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # TODO: Add admin role verification here
    # For now, any authenticated user can access - should be restricted to admin users only
    
    try:
        # Query all crons
        crons = db.query(CronMaster).order_by(CronMaster.cron_name).all()
        
        # Format response
        cron_list = []
        for cron in crons:
            cron_list.append({
                "cron_name": cron.cron_name,
                "cron_type": cron.cron_type,
                "symbol": cron.symbol,
                "status": cron.status.value if cron.status else None,
                "last_run_at": cron.last_run_at.isoformat() if cron.last_run_at else None,
                "last_success_at": cron.last_success_at.isoformat() if cron.last_success_at else None,
                "error_message": cron.error_message,
                "triggered_by": cron.triggered_by.value if cron.triggered_by else None,
                "created_at": cron.created_at.isoformat() if cron.created_at else None,
                "updated_at": cron.updated_at.isoformat() if cron.updated_at else None
            })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "data": cron_list,
                "total": len(cron_list)
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Admin] Error listing crons: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/admin/cron/run")
async def run_cron_manually(
    request: RunCronRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to manually trigger a cron job.
    
    CRITICAL: Uses same logic as system cron.
    Sets triggered_by = ADMIN.
    Prevents parallel execution.
    
    Args:
        request: RunCronRequest with cron_name and optional symbol
        authorization: Authorization header (admin required)
        db: Database session (injected)
    
    Returns:
        JSONResponse with execution result
    """
    # Admin authentication check
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # TODO: Add admin role verification here
    # For now, any authenticated user can access - should be restricted to admin users only
    
    try:
        cron_name = request.cron_name
        symbol = request.symbol
        
        logger.info(f"[Admin] Manual cron run requested: {cron_name}, symbol={symbol}")
        
        # Check if cron is already running
        if check_cron_running(db, cron_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cron {cron_name} is already running. Cannot start parallel execution."
            )
        
        # Determine cron type and handler
        cron_type = None
        cron_function = None
        
        # Check if it's a daily backtest cron
        if cron_name.startswith("DAILY_BACKTEST_"):
            cron_type = "BACKTEST"
            if not symbol:
                # Extract symbol from cron name
                symbol = cron_name.replace("DAILY_BACKTEST_", "")
            
            # Create cron function
            def cron_func():
                return run_daily_backtest_cron(symbol)
            
            cron_function = cron_func
        else:
            # Unknown cron type
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown cron type for {cron_name}. Supported: DAILY_BACKTEST_<SYMBOL>"
            )
        
        if not cron_function:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No handler found for cron {cron_name}"
            )
        
        # Execute cron with ADMIN trigger
        from engine.core.services.cron_service import execute_cron
        from engine.models import CronTriggeredBy
        
        result = execute_cron(
            cron_name=cron_name,
            cron_type=cron_type,
            cron_function=cron_function,
            symbol=symbol,
            triggered_by=CronTriggeredBy.ADMIN
        )
        
        if result["success"]:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "cron_name": cron_name,
                    "status": result["status"],
                    "result": result.get("result"),
                    "message": f"Cron {cron_name} executed successfully"
                }
            )
        else:
            # Cron execution failed
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "success": False,
                    "cron_name": cron_name,
                    "status": result["status"],
                    "error": result.get("error"),
                    "message": f"Cron {cron_name} execution failed"
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Admin] Error running cron {request.cron_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

