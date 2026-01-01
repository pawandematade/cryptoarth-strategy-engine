"""
Strategy Management APIs migrated from cryptoarth_backend
Handles user strategies, deploy/undeploy, and strategy CRUD operations

Categories:
- User strategy portfolio
- Strategy deploy / undeploy
- userStratergyPortfolio mapping
- highLowstratergy read/write APIs

Request/Response formats match cryptoarth_backend exactly.
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import logging
from datetime import datetime, date
import random

from app.database import get_db
from app.api.user_dependencies import get_current_user_strict
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

# Django table name constants
USER_STRATEGY_PORTFOLIO_TABLE = "authenticate_userstratergyportfolio"
HIGH_LOW_STRATEGY_TABLE = "authenticate_highlowstratergy"
USER_TABLE = "authenticate_user"
BROKER_MODELS_TABLE = "authenticate_brokermodels"
STRATEGY_ALLOWED_USERS_TABLE = "authenticate_highlowstratergy_allowed_users"  # M2M table (Django naming: app_model_field)


# ============================================================================
# REQUEST MODELS
# ============================================================================

class DeployStrategyRequest(BaseModel):
    """Request model for deploy strategy"""
    strategyid: int
    broker_id: Optional[int] = None


class UndeployStrategyRequest(BaseModel):
    """Request model for undeploy strategy"""
    strategyid: int  # This is actually the portfolio ID, not strategy ID


class AddStrategyRequest(BaseModel):
    """Request model for add_strategy endpoint"""
    strategy_name: Optional[str] = None
    name: Optional[str] = None
    owner: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    strategy_type: Optional[str] = "ai_generated"
    timeframe: Optional[str] = "15MIN"
    symbol: Optional[str] = "BTCUSD"
    trades_per_day: Optional[int] = 0
    indicator_name: Optional[str] = None
    target: Optional[str] = None
    sl: Optional[str] = None
    logic: Optional[Any] = None
    risk: Optional[Any] = None
    tag: Optional[List] = None
    entry_condition: Optional[str] = None
    exit_condition: Optional[str] = None
    stratergy_code: Optional[str] = None
    strategy_code: Optional[str] = None
    full_name: Optional[str] = None
    stratergy_description: Optional[str] = None
    strategy_description: Optional[str] = None
    strategy_allow: Optional[str] = "limited"
    trading_type: Optional[str] = "Automatic"
    capital_requirement: Optional[str] = None
    captial_requirement: Optional[str] = None
    entry_time: Optional[str] = "NA"
    exit_time: Optional[str] = "NA"


class AdminStrategySetRequest(BaseModel):
    """Request model for admin strategy set"""
    strategy: Optional[str] = None
    status: Optional[str] = None  # "Active" or "Inactive"


class UserStrategySetRequest(BaseModel):
    """Request model for user strategy set"""
    strategy: Optional[str] = None
    status: Optional[str] = None  # "Active" or "Inactive"


class AddUserToStrategyRequest(BaseModel):
    """Request model for add user to strategy"""
    strategy_id: int
    phone_numbers: str  # Comma-separated phone numbers


class RemoveUserToStrategyRequest(BaseModel):
    """Request model for remove user from strategy"""
    strategy_id: int
    phone_numbers: str  # Comma-separated phone numbers


class ActivateStrategyRequest(BaseModel):
    """Request model for activate/deactivate strategy"""
    id: int


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_strategy_code() -> str:
    """Generate a unique strategy code"""
    return f'STRG-{random.randint(100000, 999999)}'


def format_local_date(utc_datetime: Optional[datetime]) -> Optional[str]:
    """Convert UTC datetime to Asia/Kolkata local date string"""
    if not utc_datetime:
        return None
    try:
        import pytz
        ist_timezone = pytz.timezone("Asia/Kolkata")
        local_time = utc_datetime.astimezone(ist_timezone)
        return local_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ============================================================================
# USER STRATEGY PORTFOLIO APIs
# ============================================================================

@router.get("/user/strategies/")
def user_strategy_portfolio(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/user/strategies/
    Get user strategy portfolio
    Matches: cryptoarth_backend/authenticate/views.py user_strategy_portfolio
    """
    try:
        query = text(f"""
            SELECT 
                usp.id, usp.owner_id, usp.stratergy_id, usp.is_active, usp.date, usp.broker_id,
                s.id as strategy_id, s.owner as strategy_owner, s.stratergy_code, s.name, s.full_name,
                s.is_active as strategy_is_active, s.stratergy_description, s.tag, s.captial_requirement,
                s.entry_time, s.exit_time, s.created_date, s.target, s.sl, s.risk, s.overallReturn,
                s.strategy_allow, s.symbol, s.trading_type,
                u.id as user_id, u.phone, u.email, u.first_name, u.last_name, u.username,
                b.id as broker_id_full, b.broker, b.name as broker_name, b.status as broker_status
            FROM {USER_STRATEGY_PORTFOLIO_TABLE} usp
            INNER JOIN {HIGH_LOW_STRATEGY_TABLE} s ON usp.stratergy_id = s.id
            INNER JOIN {USER_TABLE} u ON usp.owner_id = u.id
            LEFT JOIN {BROKER_MODELS_TABLE} b ON usp.broker_id = b.id
            WHERE usp.owner_id = :user_id
            ORDER BY usp.date DESC
        """)
        
        result = db.execute(query, {"user_id": user.external_user_id})
        
        portfolios = []
        for row in result:
            portfolios.append({
                "id": row[0],
                "owner": {
                    "id": row[20],
                    "phone": row[21] if row[21] else None,
                    "email": row[22] if row[22] else None,
                    "first_name": row[23] if row[23] else "",
                    "last_name": row[24] if row[24] else "",
                    "username": row[25] if row[25] else None
                },
                "stratergy": {
                    "id": row[6],
                    "owner": row[7] if row[7] else "NA",
                    "stratergy_code": row[8] if row[8] else "NA",
                    "name": row[9] if row[9] else "NA",
                    "full_name": row[10] if row[10] else "NA",
                    "is_active": bool(row[11]) if row[11] is not None else False,
                    "stratergy_description": row[12] if row[12] else "NA",
                    "tag": row[13] if row[13] else None,
                    "captial_requirement": row[14] if row[14] else "NA",
                    "entry_time": row[15] if row[15] else "NA",
                    "exit_time": row[16] if row[16] else "NA",
                    "created_date": row[17].isoformat() if row[17] else None,
                    "target": row[18] if row[18] else "NA",
                    "sl": row[19] if row[19] else "NA",
                    "risk": row[20] if row[20] else "Low",
                    "overallReturn": float(row[21]) if row[21] else 0.0,
                    "strategy_allow": row[22] if row[22] else "All",
                    "symbol": row[23] if row[23] else None,
                    "trading_type": row[24] if row[24] else "Automatic"
                },
                "is_active": bool(row[3]) if row[3] is not None else False,
                "broker": {
                    "id": row[29],
                    "broker": row[30] if row[30] else None,
                    "name": row[31] if row[31] else None,
                    "status": bool(row[32]) if row[32] is not None else True
                } if row[29] else None
            })
        
        return portfolios
        
    except Exception as e:
        logger.error(f"Error in user_strategy_portfolio: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching strategy portfolio: {str(e)}"
        )


@router.get("/user/user_strategy/")
def user_strategy(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/user/user_strategy/
    Get user strategies (mini format)
    Matches: cryptoarth_backend/authenticate/views.py user_strategy
    """
    try:
        query = text(f"""
            SELECT 
                usp.id, usp.owner_id, usp.stratergy_id, usp.is_active, usp.broker_id,
                s.id as strategy_id, s.owner, s.stratergy_code, s.name, s.full_name,
                s.is_active as strategy_is_active, s.stratergy_description, s.tag,
                s.captial_requirement, s.entry_time, s.exit_time, s.created_date,
                s.target, s.sl, s.risk, s.overallReturn, s.strategy_allow, s.symbol, s.trading_type,
                u.id as user_id, u.phone, u.first_name, u.last_name, u.is_login,
                b.id as broker_id_full, b.broker, b.name as broker_name, b.status as broker_status
            FROM {USER_STRATEGY_PORTFOLIO_TABLE} usp
            INNER JOIN {HIGH_LOW_STRATEGY_TABLE} s ON usp.stratergy_id = s.id
            INNER JOIN {USER_TABLE} u ON usp.owner_id = u.id
            LEFT JOIN {BROKER_MODELS_TABLE} b ON usp.broker_id = b.id
            WHERE usp.owner_id = :user_id
            ORDER BY usp.date DESC
        """)
        
        result = db.execute(query, {"user_id": user.external_user_id})
        
        strategies = []
        for row in result:
            strategies.append({
                "id": row[0],
                "owner": {
                    "id": row[23],
                    "phone": row[24] if row[24] else None,
                    "first_name": row[25] if row[25] else "",
                    "last_name": row[26] if row[26] else "",
                    "is_login": bool(row[27]) if row[27] is not None else False
                },
                "stratergy": {
                    "id": row[5],
                    "owner": row[6] if row[6] else "NA",
                    "stratergy_code": row[7] if row[7] else "NA",
                    "name": row[8] if row[8] else "NA",
                    "full_name": row[9] if row[9] else "NA",
                    "is_active": bool(row[10]) if row[10] is not None else False,
                    "stratergy_description": row[11] if row[11] else "NA",
                    "tag": row[12] if row[12] else None,
                    "captial_requirement": row[13] if row[13] else "NA",
                    "entry_time": row[14] if row[14] else "NA",
                    "exit_time": row[15] if row[15] else "NA",
                    "created_date": row[16].isoformat() if row[16] else None,
                    "target": row[17] if row[17] else "NA",
                    "sl": row[18] if row[18] else "NA",
                    "risk": row[19] if row[19] else "Low",
                    "overallReturn": float(row[20]) if row[20] else 0.0,
                    "strategy_allow": row[21] if row[21] else "All",
                    "symbol": row[22] if row[22] else None,
                    "trading_type": row[23] if row[23] else "Automatic"
                },
                "is_active": bool(row[3]) if row[3] is not None else False,
                "broker": {
                    "id": row[28],
                    "broker": row[29] if row[29] else None,
                    "name": row[30] if row[30] else None,
                    "status": bool(row[31]) if row[31] is not None else True
                } if row[28] else None
            })
        
        return strategies
        
    except Exception as e:
        logger.error(f"Error in user_strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user strategies: {str(e)}"
        )


# ============================================================================
# DEPLOY / UNDEPLOY APIs
# ============================================================================

@router.post("/user/strategies/deploy/")
def deploy_strategy_portfolio(
    request: DeployStrategyRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/user/strategies/deploy/
    Deploy a strategy to user's portfolio
    Matches: cryptoarth_backend/authenticate/views.py deploy_strategy_portfolio
    """
    try:
        strategy_id = request.strategyid
        broker_id = request.broker_id
        
        # Check if strategy exists
        strategy_query = text(f"""
            SELECT id, symbol, is_active
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        strategy_result = db.execute(strategy_query, {"strategy_id": strategy_id})
        strategy_row = strategy_result.first()
        
        if not strategy_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Strategy not found", "status": False}
            )
        
        strategy_symbol = strategy_row[1]
        
        # Check for existing active deployments for same symbol
        existing_deployment_query = text(f"""
            SELECT usp.id
            FROM {USER_STRATEGY_PORTFOLIO_TABLE} usp
            INNER JOIN {HIGH_LOW_STRATEGY_TABLE} s ON usp.stratergy_id = s.id
            WHERE usp.owner_id = :user_id
            AND s.symbol = :symbol
            AND usp.is_active = 1
            AND usp.stratergy_id != :strategy_id
        """)
        existing_result = db.execute(
            existing_deployment_query,
            {
                "user_id": user.external_user_id,
                "symbol": strategy_symbol,
                "strategy_id": strategy_id
            }
        )
        
        if existing_result.first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": f"You already have an active deployment for symbol '{strategy_symbol}'",
                    "status": False
                }
            )
        
        # Check if portfolio entry already exists
        existing_portfolio_query = text(f"""
            SELECT id, is_active
            FROM {USER_STRATEGY_PORTFOLIO_TABLE}
            WHERE owner_id = :user_id
            AND stratergy_id = :strategy_id
        """)
        existing_portfolio_result = db.execute(
            existing_portfolio_query,
            {
                "user_id": user.external_user_id,
                "strategy_id": strategy_id
            }
        )
        existing_portfolio = existing_portfolio_result.first()
        
        if existing_portfolio:
            # Update existing portfolio
            portfolio_id = existing_portfolio[0]
            if broker_id:
                update_query = text(f"""
                    UPDATE {USER_STRATEGY_PORTFOLIO_TABLE}
                    SET is_active = 1, date = CURDATE(), broker_id = :broker_id
                    WHERE id = :portfolio_id
                """)
                params = {"portfolio_id": portfolio_id, "broker_id": broker_id}
            else:
                update_query = text(f"""
                    UPDATE {USER_STRATEGY_PORTFOLIO_TABLE}
                    SET is_active = 1, date = CURDATE()
                    WHERE id = :portfolio_id
                """)
                params = {"portfolio_id": portfolio_id}
            db.execute(update_query, params)
            db.commit()
            
            message = "Strategy is already activated."
        else:
            # Create new portfolio entry
            insert_query = text(f"""
                INSERT INTO {USER_STRATEGY_PORTFOLIO_TABLE}
                (owner_id, stratergy_id, is_active, date, broker_id)
                VALUES
                (:owner_id, :strategy_id, 1, CURDATE(), :broker_id)
            """)
            db.execute(
                insert_query,
                {
                    "owner_id": user.external_user_id,
                    "strategy_id": strategy_id,
                    "broker_id": broker_id if broker_id else None
                }
            )
            db.commit()
            
            # Get the newly created portfolio ID
            portfolio_id_query = text(f"""
                SELECT id FROM {USER_STRATEGY_PORTFOLIO_TABLE}
                WHERE owner_id = :user_id AND stratergy_id = :strategy_id
                ORDER BY id DESC LIMIT 1
            """)
            portfolio_id_result = db.execute(
                portfolio_id_query,
                {
                    "user_id": user.external_user_id,
                    "strategy_id": strategy_id
                }
            )
            portfolio_id = portfolio_id_result.scalar()
            message = "Strategy deployed successfully"
        
        # Fetch the portfolio data for response (with nested objects)
        portfolio_query = text(f"""
            SELECT 
                usp.id, usp.owner_id, usp.stratergy_id, usp.is_active, usp.date, usp.broker_id,
                u.id as user_id, u.phone, u.email, u.first_name, u.last_name, u.username,
                s.id as strategy_id, s.owner as strategy_owner, s.stratergy_code, s.name, s.full_name,
                s.is_active as strategy_is_active, s.stratergy_description, s.tag,
                s.captial_requirement, s.entry_time, s.exit_time, s.created_date,
                s.target, s.sl, s.risk, s.overallReturn, s.strategy_allow, s.symbol, s.trading_type,
                b.id as broker_id_full, b.broker, b.name as broker_name, b.status as broker_status
            FROM {USER_STRATEGY_PORTFOLIO_TABLE} usp
            INNER JOIN {USER_TABLE} u ON usp.owner_id = u.id
            INNER JOIN {HIGH_LOW_STRATEGY_TABLE} s ON usp.stratergy_id = s.id
            LEFT JOIN {BROKER_MODELS_TABLE} b ON usp.broker_id = b.id
            WHERE usp.id = :portfolio_id
        """)
        portfolio_result = db.execute(portfolio_query, {"portfolio_id": portfolio_id})
        portfolio_row = portfolio_result.first()
        
        if not portfolio_row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error fetching portfolio data"
            )
        
        # Build response matching UserStrategyPortfolioSerializer format
        return {
            "status": "success",
            "message": message,
            "data": {
                "id": portfolio_row[0],
                "owner": {
                    "id": portfolio_row[6],
                    "phone": portfolio_row[7] if portfolio_row[7] else None,
                    "email": portfolio_row[8] if portfolio_row[8] else None,
                    "first_name": portfolio_row[9] if portfolio_row[9] else "",
                    "last_name": portfolio_row[10] if portfolio_row[10] else "",
                    "username": portfolio_row[11] if portfolio_row[11] else None
                },
                "stratergy": {
                    "id": portfolio_row[12],
                    "owner": portfolio_row[13] if portfolio_row[13] else "NA",
                    "stratergy_code": portfolio_row[14] if portfolio_row[14] else "NA",
                    "name": portfolio_row[15] if portfolio_row[15] else "NA",
                    "full_name": portfolio_row[16] if portfolio_row[16] else "NA",
                    "is_active": bool(portfolio_row[17]) if portfolio_row[17] is not None else False,
                    "stratergy_description": portfolio_row[18] if portfolio_row[18] else "NA",
                    "tag": portfolio_row[19] if portfolio_row[19] else None,
                    "captial_requirement": portfolio_row[20] if portfolio_row[20] else "NA",
                    "entry_time": portfolio_row[21] if portfolio_row[21] else "NA",
                    "exit_time": portfolio_row[22] if portfolio_row[22] else "NA",
                    "created_date": portfolio_row[23].isoformat() if portfolio_row[23] else None,
                    "target": portfolio_row[24] if portfolio_row[24] else "NA",
                    "sl": portfolio_row[25] if portfolio_row[25] else "NA",
                    "risk": portfolio_row[26] if portfolio_row[26] else "Low",
                    "overallReturn": float(portfolio_row[27]) if portfolio_row[27] else 0.0,
                    "strategy_allow": portfolio_row[28] if portfolio_row[28] else "All",
                    "symbol": portfolio_row[29] if portfolio_row[29] else None,
                    "trading_type": portfolio_row[30] if portfolio_row[30] else "Automatic"
                },
                "is_active": bool(portfolio_row[3]) if portfolio_row[3] is not None else False,
                "broker": {
                    "id": portfolio_row[31],
                    "broker": portfolio_row[32] if portfolio_row[32] else None,
                    "name": portfolio_row[33] if portfolio_row[33] else None,
                    "status": bool(portfolio_row[34]) if portfolio_row[34] is not None else True
                } if portfolio_row[31] else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in deploy_strategy_portfolio: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deploying strategy: {str(e)}"
        )


@router.post("/user/strategies/undeploy/")
def undeploy_strategy(
    request: UndeployStrategyRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/user/strategies/undeploy/
    Undeploy a strategy (delete from portfolio)
    Matches: cryptoarth_backend/authenticate/views.py UndeployStrategyAPIView
    Note: strategyid is actually the portfolio ID, not strategy ID
    """
    try:
        portfolio_id = request.strategyid
        
        # Check if portfolio exists and belongs to user
        check_query = text(f"""
            SELECT id, owner_id, stratergy_id, is_active
            FROM {USER_STRATEGY_PORTFOLIO_TABLE}
            WHERE id = :portfolio_id
            AND owner_id = :user_id
        """)
        check_result = db.execute(
            check_query,
            {
                "portfolio_id": portfolio_id,
                "user_id": user.external_user_id
            }
        )
        portfolio_row = check_result.first()
        
        if not portfolio_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio entry not found"
            )
        
        # Fetch full portfolio data for response (before deletion)
        portfolio_query = text(f"""
            SELECT 
                usp.id, usp.owner_id, usp.stratergy_id, usp.is_active, usp.date, usp.broker_id,
                u.id as user_id, u.phone, u.email, u.first_name, u.last_name, u.username,
                s.id as strategy_id, s.owner as strategy_owner, s.stratergy_code, s.name, s.full_name,
                s.is_active as strategy_is_active, s.stratergy_description, s.tag,
                s.captial_requirement, s.entry_time, s.exit_time, s.created_date,
                s.target, s.sl, s.risk, s.overallReturn, s.strategy_allow, s.symbol, s.trading_type,
                b.id as broker_id_full, b.broker, b.name as broker_name, b.status as broker_status
            FROM {USER_STRATEGY_PORTFOLIO_TABLE} usp
            INNER JOIN {USER_TABLE} u ON usp.owner_id = u.id
            INNER JOIN {HIGH_LOW_STRATEGY_TABLE} s ON usp.stratergy_id = s.id
            LEFT JOIN {BROKER_MODELS_TABLE} b ON usp.broker_id = b.id
            WHERE usp.id = :portfolio_id
        """)
        portfolio_result = db.execute(portfolio_query, {"portfolio_id": portfolio_id})
        portfolio_row = portfolio_result.first()
        
        if portfolio_row:
            # Build portfolio data for response
            portfolio_data = {
                "id": portfolio_row[0],
                "owner": {
                    "id": portfolio_row[6],
                    "phone": portfolio_row[7] if portfolio_row[7] else None,
                    "email": portfolio_row[8] if portfolio_row[8] else None,
                    "first_name": portfolio_row[9] if portfolio_row[9] else "",
                    "last_name": portfolio_row[10] if portfolio_row[10] else "",
                    "username": portfolio_row[11] if portfolio_row[11] else None
                },
                "stratergy": {
                    "id": portfolio_row[12],
                    "owner": portfolio_row[13] if portfolio_row[13] else "NA",
                    "stratergy_code": portfolio_row[14] if portfolio_row[14] else "NA",
                    "name": portfolio_row[15] if portfolio_row[15] else "NA",
                    "full_name": portfolio_row[16] if portfolio_row[16] else "NA",
                    "is_active": bool(portfolio_row[17]) if portfolio_row[17] is not None else False,
                    "stratergy_description": portfolio_row[18] if portfolio_row[18] else "NA",
                    "tag": portfolio_row[19] if portfolio_row[19] else None,
                    "captial_requirement": portfolio_row[20] if portfolio_row[20] else "NA",
                    "entry_time": portfolio_row[21] if portfolio_row[21] else "NA",
                    "exit_time": portfolio_row[22] if portfolio_row[22] else "NA",
                    "created_date": portfolio_row[23].isoformat() if portfolio_row[23] else None,
                    "target": portfolio_row[24] if portfolio_row[24] else "NA",
                    "sl": portfolio_row[25] if portfolio_row[25] else "NA",
                    "risk": portfolio_row[26] if portfolio_row[26] else "Low",
                    "overallReturn": float(portfolio_row[27]) if portfolio_row[27] else 0.0,
                    "strategy_allow": portfolio_row[28] if portfolio_row[28] else "All",
                    "symbol": portfolio_row[29] if portfolio_row[29] else None,
                    "trading_type": portfolio_row[30] if portfolio_row[30] else "Automatic"
                },
                "is_active": bool(portfolio_row[3]) if portfolio_row[3] is not None else False,
                "broker": {
                    "id": portfolio_row[31],
                    "broker": portfolio_row[32] if portfolio_row[32] else None,
                    "name": portfolio_row[33] if portfolio_row[33] else None,
                    "status": bool(portfolio_row[34]) if portfolio_row[34] is not None else True
                } if portfolio_row[31] else None
            }
        else:
            portfolio_data = {
                "id": portfolio_id,
                "owner": None,
                "stratergy": None,
                "is_active": False,
                "broker": None
            }
        
        # Delete portfolio entry
        delete_query = text(f"""
            DELETE FROM {USER_STRATEGY_PORTFOLIO_TABLE}
            WHERE id = :portfolio_id
            AND owner_id = :user_id
        """)
        db.execute(
            delete_query,
            {
                "portfolio_id": portfolio_id,
                "user_id": user.external_user_id
            }
        )
        db.commit()
        
        return {
            "status": "success",
            "message": "Strategy undeployed successfully",
            "data": portfolio_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in undeploy_strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error undeploying strategy: {str(e)}"
        )


# ============================================================================
# STRATEGY CRUD APIs
# ============================================================================

@router.get("/get_strategy_data/")
def get_strategy_data(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/get_strategy_data/
    Get all strategies (id, name, stratergy_code only)
    Matches: cryptoarth_backend/authenticate/views.py get_strategy_data
    """
    try:
        query = text(f"""
            SELECT id, name, stratergy_code
            FROM {HIGH_LOW_STRATEGY_TABLE}
            ORDER BY created_date DESC
        """)
        
        result = db.execute(query)
        
        strategies = []
        for row in result:
            strategies.append({
                "id": row[0],
                "name": row[1] if row[1] else "NA",
                "stratergy_code": row[2] if row[2] else "NA"
            })
        
        return strategies
        
    except Exception as e:
        logger.error(f"Error in get_strategy_data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching strategy data: {str(e)}"
        )


@router.post("/user/add_strategy/")
def add_strategy(
    request: AddStrategyRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/user/add_strategy/
    Create a strategy in the database
    Matches: cryptoarth_backend/authenticate/views.py add_strategy
    """
    try:
        # Get user data
        user_id = user.external_user_id
        owner = request.owner or user.phone or str(user_id)
        phone = request.phone or owner
        email = request.email or (user.email if hasattr(user, 'email') else '')
        
        if not phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "message": "phone not found"}
            )
        
        strategy_name = request.strategy_name or request.name
        if not strategy_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "message": "strategy_name is required"}
            )
        
        # Generate strategy code if not provided
        strategy_code = request.stratergy_code or request.strategy_code or generate_strategy_code()
        
        # Normalize symbol
        symbol = (request.symbol or "BTCUSD").upper()[:25]
        
        # Prepare strategy data
        strategy_data = {
            "owner": str(user_id),
            "stratergy_code": strategy_code,
            "name": strategy_name[:25] if strategy_name else "Untitled Strategy",
            "full_name": (request.full_name or strategy_name)[:25] if (request.full_name or strategy_name) else "Untitled Strategy",
            "symbol": symbol,
            "stratergy_description": request.stratergy_description or request.strategy_description or f"AI Generated {request.strategy_type or 'ai_generated'} strategy",
            "risk": "medium",
            "strategy_allow": request.strategy_allow or "limited",
            "is_active": 0,  # Draft strategies are not active
            "tag": request.tag if request.tag else None,
            "trading_type": request.trading_type or "Automatic",
            "created_date": date.today(),
            "overallReturn": 0.000,
            "captial_requirement": request.captial_requirement or request.capital_requirement or "NA",
            "entry_time": request.entry_time or "NA",
            "exit_time": request.exit_time or "NA",
            "target": request.target or "NA",
            "sl": request.sl or "NA"
        }
        
        # Insert strategy
        insert_query = text(f"""
            INSERT INTO {HIGH_LOW_STRATEGY_TABLE}
            (owner, stratergy_code, name, full_name, symbol, stratergy_description, risk,
             strategy_allow, is_active, tag, trading_type, created_date, overallReturn,
             captial_requirement, entry_time, exit_time, target, sl)
            VALUES
            (:owner, :stratergy_code, :name, :full_name, :symbol, :stratergy_description, :risk,
             :strategy_allow, :is_active, :tag, :trading_type, :created_date, :overallReturn,
             :captial_requirement, :entry_time, :exit_time, :target, :sl)
        """)
        
        db.execute(insert_query, strategy_data)
        db.commit()
        
        # Get the newly created strategy ID
        strategy_id_query = text(f"""
            SELECT id FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE stratergy_code = :strategy_code
            ORDER BY id DESC LIMIT 1
        """)
        strategy_id_result = db.execute(strategy_id_query, {"strategy_code": strategy_code})
        strategy_id = strategy_id_result.scalar()
        
        return {
            "success": True,
            "message": "Strategy created",
            "strategy_id": strategy_id,
            "strategy_code": strategy_code,
            "status": "draft"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in add_strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "message": f"Failed to create strategy: {str(e)}"}
        )


# ============================================================================
# USER-STRATEGY MAPPING APIs
# ============================================================================

@router.post("/add_user_to_strategy/")
def add_user_to_strategy(
    request: AddUserToStrategyRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/add_user_to_strategy/
    Add users to strategy's allowed_users (M2M relationship)
    Matches: cryptoarth_backend/authenticate/views.py add_user_to_strategy
    """
    try:
        strategy_id = request.strategy_id
        phone_numbers = [p.strip() for p in request.phone_numbers.split(',') if p.strip()]
        
        if not phone_numbers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "No valid phone numbers provided"}
            )
        
        # Check if strategy exists and user has permission
        # (For now, we'll allow all authenticated users - adjust based on your access control)
        strategy_query = text(f"""
            SELECT id, name, owner
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        strategy_result = db.execute(strategy_query, {"strategy_id": strategy_id})
        strategy_row = strategy_result.first()
        
        if not strategy_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        strategy_name = strategy_row[1]
        
        # Find users by phone numbers
        placeholders = ','.join([f':phone{i}' for i in range(len(phone_numbers))])
        users_query = text(f"""
            SELECT id, phone
            FROM {USER_TABLE}
            WHERE phone IN ({placeholders})
        """)
        params = {}
        for i, phone in enumerate(phone_numbers):
            params[f"phone{i}"] = phone
        
        users_result = db.execute(users_query, params)
        found_users = {row[1]: row[0] for row in users_result}
        found_phones = set(found_users.keys())
        not_found_phones = set(phone_numbers) - found_phones
        
        # Add users to strategy's allowed_users (M2M table)
        added_count = 0
        for phone in found_phones:
            user_id = found_users[phone]
            # Check if relationship already exists
            check_query = text(f"""
                SELECT COUNT(*) FROM {STRATEGY_ALLOWED_USERS_TABLE}
                WHERE highlowstratergy_id = :strategy_id
                AND user_id = :user_id
            """)
            check_result = db.execute(
                check_query,
                {"strategy_id": strategy_id, "user_id": user_id}
            )
            if check_result.scalar() == 0:
                # Insert M2M relationship
                insert_query = text(f"""
                    INSERT INTO {STRATEGY_ALLOWED_USERS_TABLE}
                    (highlowstratergy_id, user_id)
                    VALUES
                    (:strategy_id, :user_id)
                """)
                db.execute(insert_query, {"strategy_id": strategy_id, "user_id": user_id})
                added_count += 1
        
        db.commit()
        
        return {
            "message": f"Successfully added {added_count} users to strategy",
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "added_users": list(found_phones),
            "users_not_found": list(not_found_phones) if not_found_phones else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in add_user_to_strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding users to strategy: {str(e)}"
        )


@router.post("/remove_user_to_strategy/")
def remove_user_from_strategy(
    request: RemoveUserToStrategyRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/remove_user_to_strategy/
    Remove users from strategy's allowed_users (M2M relationship)
    Matches: cryptoarth_backend/authenticate/views.py remove_user_to_strategy
    Note: Requires staff permission in Django, but we'll allow all authenticated users for now
    """
    try:
        strategy_id = request.strategy_id
        phone_numbers = [p.strip() for p in request.phone_numbers.split(',') if p.strip()]
        
        if not phone_numbers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "No valid phone numbers provided"}
            )
        
        # Check if strategy exists
        strategy_query = text(f"""
            SELECT id, name
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        strategy_result = db.execute(strategy_query, {"strategy_id": strategy_id})
        strategy_row = strategy_result.first()
        
        if not strategy_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        strategy_name = strategy_row[1]
        
        # Find users by phone numbers
        placeholders = ','.join([f':phone{i}' for i in range(len(phone_numbers))])
        users_query = text(f"""
            SELECT id, phone
            FROM {USER_TABLE}
            WHERE phone IN ({placeholders})
        """)
        params = {}
        for i, phone in enumerate(phone_numbers):
            params[f"phone{i}"] = phone
        
        users_result = db.execute(users_query, params)
        found_users = {row[1]: row[0] for row in users_result}
        found_phones = set(found_users.keys())
        not_found_phones = set(phone_numbers) - found_phones
        
        # Remove users from strategy's allowed_users (M2M table)
        removed_count = 0
        for phone in found_phones:
            user_id = found_users[phone]
            delete_query = text(f"""
                DELETE FROM {STRATEGY_ALLOWED_USERS_TABLE}
                WHERE highlowstratergy_id = :strategy_id
                AND user_id = :user_id
            """)
            result = db.execute(
                delete_query,
                {"strategy_id": strategy_id, "user_id": user_id}
            )
            if result.rowcount > 0:
                removed_count += 1
        
        db.commit()
        
        return {
            "message": f"Successfully removed {removed_count} users from strategy",
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "removed_users": list(found_phones),
            "users_not_found": list(not_found_phones) if not_found_phones else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in remove_user_from_strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing users from strategy: {str(e)}"
        )


# ============================================================================
# STRATEGY ACTIVATION / DEACTIVATION APIs
# ============================================================================

@router.post("/admin_activate_strategy/")
def admin_activate_strategy(
    request: ActivateStrategyRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/admin_activate_strategy/
    Activate a strategy (set is_active = True)
    Matches: cryptoarth_backend/authenticate/views.py admin_activate_strategy
    """
    try:
        strategy_id = request.id
        
        # Check if strategy exists
        strategy_query = text(f"""
            SELECT id, owner, is_active
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        strategy_result = db.execute(strategy_query, {"strategy_id": strategy_id})
        strategy_row = strategy_result.first()
        
        if not strategy_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Strategy not found"}
            )
        
        # Update strategy to active
        update_query = text(f"""
            UPDATE {HIGH_LOW_STRATEGY_TABLE}
            SET is_active = 1
            WHERE id = :strategy_id
        """)
        db.execute(update_query, {"strategy_id": strategy_id})
        db.commit()
        
        return {"message": "Strategy Activated Successfully."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in admin_activate_strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error activating strategy: {str(e)}"
        )


@router.post("/admin_deactivate_strategy/")
def admin_deactivate_strategy(
    request: ActivateStrategyRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/admin_deactivate_strategy/
    Deactivate a strategy (set is_active = False)
    Matches: cryptoarth_backend/authenticate/views.py admin_deactivate_strategy
    """
    try:
        strategy_id = request.id
        
        # Check if strategy exists
        strategy_query = text(f"""
            SELECT id, owner, is_active
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        strategy_result = db.execute(strategy_query, {"strategy_id": strategy_id})
        strategy_row = strategy_result.first()
        
        if not strategy_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Strategy not found"}
            )
        
        # Update strategy to inactive
        update_query = text(f"""
            UPDATE {HIGH_LOW_STRATEGY_TABLE}
            SET is_active = 0
            WHERE id = :strategy_id
        """)
        db.execute(update_query, {"strategy_id": strategy_id})
        db.commit()
        
        return {"message": "Strategy Deactivated Successfully."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in admin_deactivate_strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deactivating strategy: {str(e)}"
        )


# ============================================================================
# STRATEGY SET APIs (Filtered Strategy Lists)
# ============================================================================

@router.post("/admin_strategy_set/")
def admin_strategy_set(
    request: AdminStrategySetRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/admin_strategy_set/
    Get filtered strategy list (admin/vendor)
    Matches: cryptoarth_backend/authenticate/views.py admin_strategy_set
    """
    try:
        # Build query
        query = f"""
            SELECT 
                id, owner, stratergy_code, name, full_name, is_active, stratergy_description,
                tag, captial_requirement, entry_time, exit_time, created_date, target, sl,
                risk, overallReturn, strategy_allow, symbol, trading_type
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE 1=1
        """
        params = {}
        
        if request.strategy:
            query += " AND name = :strategy"
            params["strategy"] = request.strategy
        
        if request.status == "Inactive":
            query += " AND is_active = 0"
        elif request.status == "Active":
            query += " AND is_active = 1"
        
        # Note: Staff/vendor filtering would be added here based on user.is_staff/is_vendor
        # For now, we'll return all matching strategies
        
        query += " ORDER BY created_date DESC"
        
        result = db.execute(text(query), params)
        
        strategies = []
        for row in result:
            strategies.append({
                "id": row[0],
                "owner": row[1] if row[1] else "NA",
                "stratergy_code": row[2] if row[2] else "NA",
                "name": row[3] if row[3] else "NA",
                "full_name": row[4] if row[4] else "NA",
                "is_active": bool(row[5]) if row[5] is not None else False,
                "stratergy_description": row[6] if row[6] else "NA",
                "tag": row[7] if row[7] else None,
                "captial_requirement": row[8] if row[8] else "NA",
                "entry_time": row[9] if row[9] else "NA",
                "exit_time": row[10] if row[10] else "NA",
                "created_date": row[11].isoformat() if row[11] else None,
                "target": row[12] if row[12] else "NA",
                "sl": row[13] if row[13] else "NA",
                "risk": row[14] if row[14] else "Low",
                "overallReturn": float(row[15]) if row[15] else 0.0,
                "strategy_allow": row[16] if row[16] else "All",
                "symbol": row[17] if row[17] else None,
                "trading_type": row[18] if row[18] else "Automatic"
            })
        
        return strategies
        
    except Exception as e:
        logger.error(f"Error in admin_strategy_set: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching strategy set: {str(e)}"
        )


@router.post("/user_strategy_set/")
def user_strategy_set(
    request: UserStrategySetRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/user_strategy_set/
    Get filtered strategy list (user's own strategies)
    Matches: cryptoarth_backend/authenticate/views.py user_strategy_set
    """
    try:
        # Get user's phone from external_user_id
        user_query = text(f"""
            SELECT phone FROM {USER_TABLE}
            WHERE id = :user_id
        """)
        user_result = db.execute(user_query, {"user_id": user.external_user_id})
        user_phone = user_result.scalar()
        
        if not user_phone:
            return []
        
        # Build query
        query = f"""
            SELECT 
                id, owner, stratergy_code, name, full_name, is_active, stratergy_description,
                tag, captial_requirement, entry_time, exit_time, created_date, target, sl,
                risk, overallReturn, strategy_allow, symbol, trading_type
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE owner = :owner
        """
        params = {"owner": user_phone}
        
        if request.strategy:
            query += " AND name = :strategy"
            params["strategy"] = request.strategy
        
        if request.status == "Inactive":
            query += " AND is_active = 0"
        elif request.status == "Active":
            query += " AND is_active = 1"
        
        query += " ORDER BY created_date DESC"
        
        result = db.execute(text(query), params)
        
        strategies = []
        for row in result:
            strategies.append({
                "id": row[0],
                "owner": row[1] if row[1] else "NA",
                "stratergy_code": row[2] if row[2] else "NA",
                "name": row[3] if row[3] else "NA",
                "full_name": row[4] if row[4] else "NA",
                "is_active": bool(row[5]) if row[5] is not None else False,
                "stratergy_description": row[6] if row[6] else "NA",
                "tag": row[7] if row[7] else None,
                "captial_requirement": row[8] if row[8] else "NA",
                "entry_time": row[9] if row[9] else "NA",
                "exit_time": row[10] if row[10] else "NA",
                "created_date": row[11].isoformat() if row[11] else None,
                "target": row[12] if row[12] else "NA",
                "sl": row[13] if row[13] else "NA",
                "risk": row[14] if row[14] else "Low",
                "overallReturn": float(row[15]) if row[15] else 0.0,
                "strategy_allow": row[16] if row[16] else "All",
                "symbol": row[17] if row[17] else None,
                "trading_type": row[18] if row[18] else "Automatic"
            })
        
        return strategies
        
    except Exception as e:
        logger.error(f"Error in user_strategy_set: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user strategy set: {str(e)}"
        )


# ============================================================================
# ADMIN USER STRATEGY APIs
# ============================================================================

class AdminUserStrategyRequest(BaseModel):
    """Request model for admin user strategy"""
    customer_phone: Optional[str] = None
    strategy: Optional[str] = None
    status: Optional[str] = None  # "ACTIVE" or "INACTIVE"


class AdminUserStrategyUpdateRequest(BaseModel):
    """Request model for updating admin user strategy"""
    strategy_id: int  # This is the portfolio ID
    status: bool  # True for active, False for inactive


@router.post("/user/admin_user_strategy/")
def admin_user_strategy(
    request: AdminUserStrategyRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/user/admin_user_strategy/
    Get filtered user strategy portfolio (admin/vendor)
    Matches: cryptoarth_backend/authenticate/views.py admin_user_strategy
    """
    try:
        # Build query
        query = f"""
            SELECT 
                usp.id, usp.owner_id, usp.stratergy_id, usp.is_active, usp.broker_id,
                u.id as user_id, u.phone, u.first_name, u.last_name, u.is_login,
                s.id as strategy_id, s.owner, s.stratergy_code, s.name, s.full_name,
                s.is_active as strategy_is_active, s.stratergy_description, s.tag,
                s.captial_requirement, s.entry_time, s.exit_time, s.created_date,
                s.target, s.sl, s.risk, s.overallReturn, s.strategy_allow, s.symbol, s.trading_type,
                b.id as broker_id_full, b.broker, b.name as broker_name, b.status as broker_status
            FROM {USER_STRATEGY_PORTFOLIO_TABLE} usp
            INNER JOIN {USER_TABLE} u ON usp.owner_id = u.id
            INNER JOIN {HIGH_LOW_STRATEGY_TABLE} s ON usp.stratergy_id = s.id
            LEFT JOIN {BROKER_MODELS_TABLE} b ON usp.broker_id = b.id
            WHERE 1=1
        """
        params = {}
        
        if request.customer_phone:
            query += " AND u.phone = :customer_phone"
            params["customer_phone"] = request.customer_phone
        
        if request.strategy:
            query += " AND s.stratergy_code = :strategy"
            params["strategy"] = request.strategy
        
        if request.status == "ACTIVE":
            query += " AND usp.is_active = 1"
        elif request.status == "INACTIVE":
            query += " AND usp.is_active = 0"
        
        # Note: Vendor filtering would be added here based on user.is_vendor
        # For now, we'll return all matching portfolios
        
        query += " ORDER BY usp.date DESC"
        
        result = db.execute(text(query), params)
        
        portfolios = []
        for row in result:
            portfolios.append({
                "id": row[0],
                "owner": {
                    "id": row[5],
                    "phone": row[6] if row[6] else None,
                    "first_name": row[7] if row[7] else "",
                    "last_name": row[8] if row[8] else "",
                    "is_login": bool(row[9]) if row[9] is not None else False
                },
                "stratergy": {
                    "id": row[10],
                    "owner": row[11] if row[11] else "NA",
                    "stratergy_code": row[12] if row[12] else "NA",
                    "name": row[13] if row[13] else "NA",
                    "full_name": row[14] if row[14] else "NA",
                    "is_active": bool(row[15]) if row[15] is not None else False,
                    "stratergy_description": row[16] if row[16] else "NA",
                    "tag": row[17] if row[17] else None,
                    "captial_requirement": row[18] if row[18] else "NA",
                    "entry_time": row[19] if row[19] else "NA",
                    "exit_time": row[20] if row[20] else "NA",
                    "created_date": row[21].isoformat() if row[21] else None,
                    "target": row[22] if row[22] else "NA",
                    "sl": row[23] if row[23] else "NA",
                    "risk": row[24] if row[24] else "Low",
                    "overallReturn": float(row[25]) if row[25] else 0.0,
                    "strategy_allow": row[26] if row[26] else "All",
                    "symbol": row[27] if row[27] else None,
                    "trading_type": row[28] if row[28] else "Automatic"
                },
                "is_active": bool(row[3]) if row[3] is not None else False,
                "broker": {
                    "id": row[29],
                    "broker": row[30] if row[30] else None,
                    "name": row[31] if row[31] else None,
                    "status": bool(row[32]) if row[32] is not None else True
                } if row[29] else None
            })
        
        return portfolios
        
    except Exception as e:
        logger.error(f"Error in admin_user_strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching admin user strategy: {str(e)}"
        )


@router.put("/user/admin_user_strategy/")
def admin_user_strategy_update(
    request: AdminUserStrategyUpdateRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    PUT /auth/user/admin_user_strategy/
    Update user strategy portfolio status
    Matches: cryptoarth_backend/authenticate/views.py admin_user_strategy (PUT method)
    """
    try:
        portfolio_id = request.strategy_id
        is_active = 1 if request.status else 0
        
        # Check if portfolio exists
        check_query = text(f"""
            SELECT id FROM {USER_STRATEGY_PORTFOLIO_TABLE}
            WHERE id = :portfolio_id
        """)
        check_result = db.execute(check_query, {"portfolio_id": portfolio_id})
        if not check_result.first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio entry not found"
            )
        
        # Update portfolio status
        update_query = text(f"""
            UPDATE {USER_STRATEGY_PORTFOLIO_TABLE}
            SET is_active = :is_active
            WHERE id = :portfolio_id
        """)
        db.execute(update_query, {"portfolio_id": portfolio_id, "is_active": is_active})
        db.commit()
        
        return {"message": "Strategy updated successfully."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in admin_user_strategy_update: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating strategy: {str(e)}"
        )


# ============================================================================
# STRATEGY USERS DETAIL API
# ============================================================================

@router.get("/strategy/users/{strategy_id}/detailed/")
def strategy_users_detailed(
    strategy_id: int,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/strategy/users/{id}/detailed/
    Get detailed list of users allowed to access a strategy
    Matches: cryptoarth_backend/authenticate/views.py StrategyUsersDetailView
    """
    try:
        # Check if strategy exists
        strategy_query = text(f"""
            SELECT id, name
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        strategy_result = db.execute(strategy_query, {"strategy_id": strategy_id})
        strategy_row = strategy_result.first()
        
        if not strategy_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        strategy_name = strategy_row[1]
        
        # Get allowed users from M2M table
        users_query = text(f"""
            SELECT 
                u.id, u.phone, u.email, u.first_name, u.last_name, u.username,
                u.is_active, u.date_joined
            FROM {USER_TABLE} u
            INNER JOIN {STRATEGY_ALLOWED_USERS_TABLE} sau ON u.id = sau.user_id
            WHERE sau.highlowstratergy_id = :strategy_id
        """)
        users_result = db.execute(users_query, {"strategy_id": strategy_id})
        
        users = []
        for row in users_result:
            users.append({
                "id": row[0],
                "phone": row[1] if row[1] else None,
                "email": row[2] if row[2] else None,
                "first_name": row[3] if row[3] else "",
                "last_name": row[4] if row[4] else "",
                "username": row[5] if row[5] else None,
                "is_active": bool(row[6]) if row[6] is not None else False,
                "date_joined": row[7].isoformat() if row[7] else None
            })
        
        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "total_users": len(users),
            "users": users
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in strategy_users_detailed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching strategy users: {str(e)}"
        )


# ============================================================================
# HIGH-LOW STRATEGIES CRUD APIs (ViewSet endpoints)
# ============================================================================

@router.get("/highlow-strategies1/")
def highlow_strategies_list_authenticated(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/highlow-strategies1/
    List active strategies accessible to user (filtered by allowed_users)
    Matches: cryptoarth_backend/authenticate/views.py HighLowStrategyViewSet1.list
    """
    try:
        # Get strategies that are active and either have no allowed_users restriction
        # or include the current user in allowed_users
        query = text(f"""
            SELECT DISTINCT
                s.id, s.owner, s.stratergy_code, s.name, s.full_name, s.is_active, s.stratergy_description,
                s.tag, s.captial_requirement, s.entry_time, s.exit_time, s.created_date, s.target, s.sl,
                s.risk, s.overallReturn, s.strategy_allow, s.symbol, s.trading_type
            FROM {HIGH_LOW_STRATEGY_TABLE} s
            LEFT JOIN {STRATEGY_ALLOWED_USERS_TABLE} sau ON s.id = sau.highlowstratergy_id
            WHERE s.is_active = 1
            AND (sau.user_id IS NULL OR sau.user_id = :user_id)
            ORDER BY s.created_date DESC
        """)
        
        result = db.execute(query, {"user_id": user.external_user_id})
        
        strategies = []
        for row in result:
            strategies.append({
                "id": row[0],
                "owner": row[1] if row[1] else "NA",
                "stratergy_code": row[2] if row[2] else "NA",
                "name": row[3] if row[3] else "NA",
                "full_name": row[4] if row[4] else "NA",
                "is_active": bool(row[5]) if row[5] is not None else False,
                "stratergy_description": row[6] if row[6] else "NA",
                "tag": row[7] if row[7] else None,
                "captial_requirement": row[8] if row[8] else "NA",
                "entry_time": row[9] if row[9] else "NA",
                "exit_time": row[10] if row[10] else "NA",
                "created_date": row[11].isoformat() if row[11] else None,
                "target": row[12] if row[12] else "NA",
                "sl": row[13] if row[13] else "NA",
                "risk": row[14] if row[14] else "Low",
                "overallReturn": float(row[15]) if row[15] else 0.0,
                "strategy_allow": row[16] if row[16] else "All",
                "symbol": row[17] if row[17] else None,
                "trading_type": row[18] if row[18] else "Automatic"
            })
        
        return strategies
        
    except Exception as e:
        logger.error(f"Error in highlow_strategies_list_authenticated: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching strategies: {str(e)}"
        )


@router.get("/highlow-strategies/")
def highlow_strategies_list(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/highlow-strategies/
    List all strategies (admin/staff only)
    Matches: cryptoarth_backend/authenticate/views.py HighLowStrategyViewSet.list
    """
    try:
        query = text(f"""
            SELECT 
                id, owner, stratergy_code, name, full_name, is_active, stratergy_description,
                tag, captial_requirement, entry_time, exit_time, created_date, target, sl,
                risk, overallReturn, strategy_allow, symbol, trading_type
            FROM {HIGH_LOW_STRATEGY_TABLE}
            ORDER BY created_date DESC
        """)
        
        result = db.execute(query)
        
        strategies = []
        for row in result:
            strategies.append({
                "id": row[0],
                "owner": row[1] if row[1] else "NA",
                "stratergy_code": row[2] if row[2] else "NA",
                "name": row[3] if row[3] else "NA",
                "full_name": row[4] if row[4] else "NA",
                "is_active": bool(row[5]) if row[5] is not None else False,
                "stratergy_description": row[6] if row[6] else "NA",
                "tag": row[7] if row[7] else None,
                "captial_requirement": row[8] if row[8] else "NA",
                "entry_time": row[9] if row[9] else "NA",
                "exit_time": row[10] if row[10] else "NA",
                "created_date": row[11].isoformat() if row[11] else None,
                "target": row[12] if row[12] else "NA",
                "sl": row[13] if row[13] else "NA",
                "risk": row[14] if row[14] else "Low",
                "overallReturn": float(row[15]) if row[15] else 0.0,
                "strategy_allow": row[16] if row[16] else "All",
                "symbol": row[17] if row[17] else None,
                "trading_type": row[18] if row[18] else "Automatic"
            })
        
        return strategies
        
    except Exception as e:
        logger.error(f"Error in highlow_strategies_list: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching strategies: {str(e)}"
        )


@router.get("/highlow-strategies/{strategy_id}/")
def highlow_strategies_retrieve(
    strategy_id: int,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/highlow-strategies/{id}/
    Retrieve a single strategy
    Matches: cryptoarth_backend/authenticate/views.py HighLowStrategyViewSet.retrieve
    """
    try:
        query = text(f"""
            SELECT 
                id, owner, stratergy_code, name, full_name, is_active, stratergy_description,
                tag, captial_requirement, entry_time, exit_time, created_date, target, sl,
                risk, overallReturn, strategy_allow, symbol, trading_type
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        
        result = db.execute(query, {"strategy_id": strategy_id})
        row = result.first()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Not found"}
            )
        
        return {
            "id": row[0],
            "owner": row[1] if row[1] else "NA",
            "stratergy_code": row[2] if row[2] else "NA",
            "name": row[3] if row[3] else "NA",
            "full_name": row[4] if row[4] else "NA",
            "is_active": bool(row[5]) if row[5] is not None else False,
            "stratergy_description": row[6] if row[6] else "NA",
            "tag": row[7] if row[7] else None,
            "captial_requirement": row[8] if row[8] else "NA",
            "entry_time": row[9] if row[9] else "NA",
            "exit_time": row[10] if row[10] else "NA",
            "created_date": row[11].isoformat() if row[11] else None,
            "target": row[12] if row[12] else "NA",
            "sl": row[13] if row[13] else "NA",
            "risk": row[14] if row[14] else "Low",
            "overallReturn": float(row[15]) if row[15] else 0.0,
            "strategy_allow": row[16] if row[16] else "All",
            "symbol": row[17] if row[17] else None,
            "trading_type": row[18] if row[18] else "Automatic"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in highlow_strategies_retrieve: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching strategy: {str(e)}"
        )


@router.post("/highlow-strategies/")
def highlow_strategies_create(
    request: Dict[str, Any] = Body(...),
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/highlow-strategies/
    Create a new strategy
    Matches: cryptoarth_backend/authenticate/views.py HighLowStrategyViewSet.create
    """
    try:
        # Extract strategy data from request body
        data = request
        
        # Prepare strategy data
        strategy_data = {
            "owner": data.get("owner", str(user.external_user_id)),
            "stratergy_code": data.get("stratergy_code", generate_strategy_code()),
            "name": data.get("name", "Untitled Strategy")[:25],
            "full_name": data.get("full_name", data.get("name", "Untitled Strategy"))[:25],
            "symbol": (data.get("symbol") or "BTCUSD").upper()[:25],
            "stratergy_description": data.get("stratergy_description", "NA"),
            "risk": data.get("risk", "Low"),
            "strategy_allow": data.get("strategy_allow", "All"),
            "is_active": 1 if data.get("is_active", False) else 0,
            "tag": data.get("tag"),
            "trading_type": data.get("trading_type", "Automatic"),
            "created_date": data.get("created_date", date.today()),
            "overallReturn": float(data.get("overallReturn", 0.0)),
            "captial_requirement": data.get("captial_requirement", "NA"),
            "entry_time": data.get("entry_time", "NA"),
            "exit_time": data.get("exit_time", "NA"),
            "target": data.get("target", "NA"),
            "sl": data.get("sl", "NA")
        }
        
        # Insert strategy
        insert_query = text(f"""
            INSERT INTO {HIGH_LOW_STRATEGY_TABLE}
            (owner, stratergy_code, name, full_name, symbol, stratergy_description, risk,
             strategy_allow, is_active, tag, trading_type, created_date, overallReturn,
             captial_requirement, entry_time, exit_time, target, sl)
            VALUES
            (:owner, :stratergy_code, :name, :full_name, :symbol, :stratergy_description, :risk,
             :strategy_allow, :is_active, :tag, :trading_type, :created_date, :overallReturn,
             :captial_requirement, :entry_time, :exit_time, :target, :sl)
        """)
        
        db.execute(insert_query, strategy_data)
        db.commit()
        
        # Get the newly created strategy ID
        strategy_id_query = text(f"""
            SELECT id FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE stratergy_code = :stratergy_code
            ORDER BY id DESC LIMIT 1
        """)
        strategy_id_result = db.execute(
            strategy_id_query,
            {"stratergy_code": strategy_data["stratergy_code"]}
        )
        strategy_id = strategy_id_result.scalar()
        
        # Return the created strategy (fetch full data)
        return highlow_strategies_retrieve(strategy_id, user, db)
        
    except Exception as e:
        logger.error(f"Error in highlow_strategies_create: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating strategy: {str(e)}"
        )


@router.put("/highlow-strategies/{strategy_id}/")
def highlow_strategies_update(
    strategy_id: int,
    request: Dict[str, Any] = Body(...),
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    PUT /auth/highlow-strategies/{id}/
    Update a strategy
    Matches: cryptoarth_backend/authenticate/views.py HighLowStrategyViewSet.update
    """
    try:
        # Check if strategy exists
        check_query = text(f"""
            SELECT id FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        check_result = db.execute(check_query, {"strategy_id": strategy_id})
        if not check_result.first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Not found"}
            )
        
        # Extract update data from request body
        data = request
        
        # Build update query dynamically based on provided fields
        update_fields = []
        params = {"strategy_id": strategy_id}
        
        if "name" in data:
            update_fields.append("name = :name")
            params["name"] = data["name"][:25] if data["name"] else "NA"
        
        if "full_name" in data:
            update_fields.append("full_name = :full_name")
            params["full_name"] = data["full_name"][:25] if data["full_name"] else "NA"
        
        if "stratergy_description" in data:
            update_fields.append("stratergy_description = :stratergy_description")
            params["stratergy_description"] = data["stratergy_description"]
        
        if "is_active" in data:
            update_fields.append("is_active = :is_active")
            params["is_active"] = 1 if data["is_active"] else 0
        
        if "risk" in data:
            update_fields.append("risk = :risk")
            params["risk"] = data["risk"]
        
        if "strategy_allow" in data:
            update_fields.append("strategy_allow = :strategy_allow")
            params["strategy_allow"] = data["strategy_allow"]
        
        if "symbol" in data:
            update_fields.append("symbol = :symbol")
            params["symbol"] = (data["symbol"] or "BTCUSD").upper()[:25]
        
        if "trading_type" in data:
            update_fields.append("trading_type = :trading_type")
            params["trading_type"] = data["trading_type"]
        
        if "target" in data:
            update_fields.append("target = :target")
            params["target"] = data["target"]
        
        if "sl" in data:
            update_fields.append("sl = :sl")
            params["sl"] = data["sl"]
        
        if "tag" in data:
            update_fields.append("tag = :tag")
            params["tag"] = data["tag"]
        
        if not update_fields:
            # No fields to update, return current strategy
            return highlow_strategies_retrieve(strategy_id, user, db)
        
        # Execute update
        update_query = text(f"""
            UPDATE {HIGH_LOW_STRATEGY_TABLE}
            SET {', '.join(update_fields)}
            WHERE id = :strategy_id
        """)
        db.execute(update_query, params)
        db.commit()
        
        # Return updated strategy
        return highlow_strategies_retrieve(strategy_id, user, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in highlow_strategies_update: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating strategy: {str(e)}"
        )


@router.delete("/highlow-strategies/{strategy_id}/")
def highlow_strategies_delete(
    strategy_id: int,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    DELETE /auth/highlow-strategies/{id}/
    Delete a strategy
    Matches: cryptoarth_backend/authenticate/views.py HighLowStrategyViewSet.destroy
    """
    try:
        # Check if strategy exists
        check_query = text(f"""
            SELECT id FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        check_result = db.execute(check_query, {"strategy_id": strategy_id})
        if not check_result.first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Not found"}
            )
        
        # Delete strategy
        delete_query = text(f"""
            DELETE FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        db.execute(delete_query, {"strategy_id": strategy_id})
        db.commit()
        
        return {"message": "Strategy deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in highlow_strategies_delete: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting strategy: {str(e)}"
        )


# ============================================================================
# HIGH-LOW STRATEGIES LIMITED APIs
# ============================================================================

@router.post("/highlow-strategies-limited/")
def highlow_strategies_limited_create(
    request: Dict[str, Any] = Body(...),
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/highlow-strategies-limited/
    Create a limited strategy (non-admin users)
    Matches: cryptoarth_backend/authenticate/views.py HighLowStrategyLimitedCreateView.create
    Note: Forces strategy_allow to "limited" and adds user to allowed_users
    """
    try:
        # Get user's phone
        user_query = text(f"""
            SELECT phone FROM {USER_TABLE}
            WHERE id = :user_id
        """)
        user_result = db.execute(user_query, {"user_id": user.external_user_id})
        user_phone = user_result.scalar()
        
        if not user_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User phone not found"
            )
        
        # Extract strategy data from request body
        data = request
        
        # Force strategy_allow to "limited"
        strategy_allow = "limited"
        
        # Prepare strategy data
        strategy_data = {
            "owner": user_phone,
            "stratergy_code": data.get("stratergy_code", generate_strategy_code()),
            "name": data.get("name", "Untitled Strategy")[:25],
            "full_name": data.get("full_name", data.get("name", "Untitled Strategy"))[:25],
            "symbol": (data.get("symbol") or "BTCUSD").upper()[:25],
            "stratergy_description": data.get("stratergy_description", "NA"),
            "risk": data.get("risk", "Low"),
            "strategy_allow": strategy_allow,  # Forced to "limited"
            "is_active": 1 if data.get("is_active", False) else 0,
            "tag": data.get("tag"),
            "trading_type": data.get("trading_type", "Automatic"),
            "created_date": data.get("created_date", date.today()),
            "overallReturn": float(data.get("overallReturn", 0.0)),
            "captial_requirement": data.get("captial_requirement", "NA"),
            "entry_time": data.get("entry_time", "NA"),
            "exit_time": data.get("exit_time", "NA"),
            "target": data.get("target", "NA"),
            "sl": data.get("sl", "NA")
        }
        
        # Insert strategy
        insert_query = text(f"""
            INSERT INTO {HIGH_LOW_STRATEGY_TABLE}
            (owner, stratergy_code, name, full_name, symbol, stratergy_description, risk,
             strategy_allow, is_active, tag, trading_type, created_date, overallReturn,
             captial_requirement, entry_time, exit_time, target, sl)
            VALUES
            (:owner, :stratergy_code, :name, :full_name, :symbol, :stratergy_description, :risk,
             :strategy_allow, :is_active, :tag, :trading_type, :created_date, :overallReturn,
             :captial_requirement, :entry_time, :exit_time, :target, :sl)
        """)
        
        db.execute(insert_query, strategy_data)
        db.commit()
        
        # Get the newly created strategy ID
        strategy_id_query = text(f"""
            SELECT id FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE stratergy_code = :stratergy_code
            ORDER BY id DESC LIMIT 1
        """)
        strategy_id_result = db.execute(
            strategy_id_query,
            {"stratergy_code": strategy_data["stratergy_code"]}
        )
        strategy_id = strategy_id_result.scalar()
        
        # Add current user to allowed_users (M2M relationship)
        m2m_insert_query = text(f"""
            INSERT INTO {STRATEGY_ALLOWED_USERS_TABLE}
            (highlowstratergy_id, user_id)
            VALUES
            (:strategy_id, :user_id)
            ON DUPLICATE KEY UPDATE highlowstratergy_id = highlowstratergy_id
        """)
        db.execute(m2m_insert_query, {"strategy_id": strategy_id, "user_id": user.external_user_id})
        db.commit()
        
        # Return the created strategy
        return highlow_strategies_retrieve(strategy_id, user, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in highlow_strategies_limited_create: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating limited strategy: {str(e)}"
        )


@router.get("/get_admin_strategy_data/")
def get_admin_strategy_data(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/get_admin_strategy_data/
    Get strategies owned by user (Manual or Both trading types)
    Matches: cryptoarth_backend/authenticate/views.py get_admin_strategy_data
    """
    try:
        # Get user's username (used as owner in strategies)
        user_query = text(f"""
            SELECT username FROM {USER_TABLE}
            WHERE id = :user_id
        """)
        user_result = db.execute(user_query, {"user_id": user.external_user_id})
        user_username = user_result.scalar()
        
        if not user_username:
            return []
        
        query = text(f"""
            SELECT id, name, stratergy_code
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE owner = :owner
            AND trading_type IN ('Manual', 'Both')
            ORDER BY created_date DESC
        """)
        
        result = db.execute(query, {"owner": user_username})
        
        strategies = []
        for row in result:
            strategies.append({
                "id": row[0],
                "name": row[1] if row[1] else "NA",
                "stratergy_code": row[2] if row[2] else "NA"
            })
        
        return strategies
        
    except Exception as e:
        logger.error(f"Error in get_admin_strategy_data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching admin strategy data: {str(e)}"
        )

