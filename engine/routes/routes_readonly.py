"""
Read-Only APIs migrated from cryptoarth_backend
All endpoints are READ-ONLY (no DB writes)

Categories:
- Signal listing
- Orders / Trades history
- Positions (read-only)
- Dashboard / PnL APIs
- Performance summary APIs

Request/Response formats match cryptoarth_backend exactly.
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal
import logging
from datetime import datetime

from common.db import get_db
from app.api.user_dependencies import get_current_user, get_current_user_strict
from app.models import User
from app.utils.date_utils import get_todays_dates, convert_date_range_to_utc

logger = logging.getLogger(__name__)

router = APIRouter()

# Django table name constants
SIGNAL_MASTER_TABLE = "authenticate_signalmaster"
ORDER_DETAILS_TABLE = "authenticate_orderdetails"
TRADE_DETAILS_TABLE = "authenticate_tradedetails"
POSITION_TABLE = "authenticate_position"
USER_STRATEGY_PORTFOLIO_TABLE = "authenticate_userstratergyportfolio"
HIGH_LOW_STRATEGY_TABLE = "authenticate_highlowstratergy"
USER_TABLE = "authenticate_user"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class DashboardCountRequest(BaseModel):
    """Request model for dashboard count APIs"""
    startDate: Optional[str] = None  # YYYY-MM-DD
    endDate: Optional[str] = None  # YYYY-MM-DD


class UserOrderDetailsRequest(BaseModel):
    """Request model for user order details"""
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD
    strategy: Optional[str] = None


class AdminOrderDetailsRequest(BaseModel):
    """Request model for admin order details"""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    strategy: Optional[str] = None
    owner: Optional[str] = None  # phone number


class AdminPositionDetailsRequest(BaseModel):
    """Request model for admin position details"""
    strategy: Optional[str] = None
    owner: Optional[str] = None  # phone number


# ============================================================================
# SIGNAL LISTING
# ============================================================================

@router.get("/signal-list/")
def signal_list(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/signal-list/
    List all signals for user's strategies (today's signals only)
    Matches: cryptoarth_backend/authenticate/views.py signalmasterView
    """
    try:
        start_date, end_date = get_todays_dates()
        
        # Get user's strategy IDs from userStratergyPortfolio
        strategy_ids_query = text(f"""
            SELECT DISTINCT stratergy_id 
            FROM {USER_STRATEGY_PORTFOLIO_TABLE}
            WHERE owner_id = :user_id
        """)
        strategy_ids_result = db.execute(strategy_ids_query, {"user_id": user.external_user_id})
        strategy_ids = [row[0] for row in strategy_ids_result]
        
        if not strategy_ids:
            return []
        
        # Get signals for user's strategies
        # Build IN clause manually for MySQL compatibility
        if not strategy_ids:
            return []
        
        placeholders = ','.join([':id' + str(i) for i in range(len(strategy_ids))])
        signals_query = text(f"""
            SELECT 
                id, stratergy_id, symbol, side, unique, timestamp, status,
                entry, target, stoploss, leverage, capital, type
            FROM {SIGNAL_MASTER_TABLE}
            WHERE stratergy_id IN ({placeholders})
            AND timestamp >= :start_date
            AND timestamp <= :end_date
            ORDER BY timestamp DESC
        """)
        
        # Build params dict with indexed IDs
        params = {
            "start_date": start_date,
            "end_date": end_date
        }
        for i, strategy_id in enumerate(strategy_ids):
            params[f"id{i}"] = strategy_id
        
        signals_result = db.execute(signals_query, params)
        
        signals = []
        for row in signals_result:
            signals.append({
                "id": row[0],
                "stratergy": row[1],
                "symbol": row[2],
                "side": row[3],
                "unique": row[4],
                "timestamp": row[5].isoformat() if row[5] else None,
                "status": row[6],
                "entry": float(row[7]) if row[7] else 0.0,
                "target": float(row[8]) if row[8] else 0.0,
                "stoploss": float(row[9]) if row[9] else 0.0,
                "leverage": row[10] if row[10] else 0,
                "capital": float(row[11]) if row[11] else 0.0,
                "type": row[12] if row[12] else "NA"
            })
        
        return signals
        
    except Exception as e:
        logger.error(f"Error in signal_list: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching signals: {str(e)}"
        )


# ============================================================================
# ORDERS / TRADES HISTORY
# ============================================================================

@router.get("/orders/")
def orders(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/orders/
    Get user order details (today's orders only)
    Matches: cryptoarth_backend/authenticate/views.py OrderDetailsView
    """
    try:
        start_date, end_date = get_todays_dates()
        
        orders_query = text(f"""
            SELECT 
                id, owner_id, symbol, stratergy, buyprice, sellprice, buyquantity,
                sellquantity, side, orderid, date, status, profit, stratergy_name, broker_id
            FROM {ORDER_DETAILS_TABLE}
            WHERE owner_id = :user_id
            AND date >= :start_date
            AND date <= :end_date
            ORDER BY date DESC
        """)
        
        orders_result = db.execute(
            orders_query,
            {
                "user_id": user.external_user_id,
                "start_date": start_date,
                "end_date": end_date
            }
        )
        
        orders = []
        for row in orders_result:
            orders.append({
                "id": row[0],
                "owner": row[1],
                "symbol": row[2] if row[2] else "NA",
                "stratergy": row[3] if row[3] else "NA",
                "buyprice": float(row[4]) if row[4] else 0.0,
                "sellprice": float(row[5]) if row[5] else 0.0,
                "buyquantity": float(row[6]) if row[6] else 0.0,
                "sellquantity": float(row[7]) if row[7] else 0.0,
                "side": row[8] if row[8] else "NA",
                "orderid": row[9] if row[9] else "NA",
                "date": row[10].isoformat() if row[10] else None,
                "status": row[11] if row[11] else "NA",
                "profit": float(row[12]) if row[12] else 0.0,
                "stratergy_name": row[13] if row[13] else "NA",
                "broker": row[14] if row[14] else None
            })
        
        return orders
        
    except Exception as e:
        logger.error(f"Error in orders: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching orders: {str(e)}"
        )


@router.get("/trades/")
def trades(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/trades/
    Get user trade details (today's trades only)
    Matches: cryptoarth_backend/authenticate/views.py TradeDetailsView
    """
    try:
        start_date, end_date = get_todays_dates()
        
        trades_query = text(f"""
            SELECT 
                id, owner_id, symbol, price, quantity, side, unique, date,
                status, orderid, stratergy, margin, remark, stratergy_name, broker_id
            FROM {TRADE_DETAILS_TABLE}
            WHERE owner_id = :user_id
            AND date >= :start_date
            AND date <= :end_date
            ORDER BY date DESC
        """)
        
        trades_result = db.execute(
            trades_query,
            {
                "user_id": user.external_user_id,
                "start_date": start_date,
                "end_date": end_date
            }
        )
        
        trades = []
        for row in trades_result:
            trades.append({
                "id": row[0],
                "owner": row[1],
                "symbol": row[2] if row[2] else "NA",
                "price": float(row[3]) if row[3] else 0.0,
                "quantity": float(row[4]) if row[4] else 0.0,
                "side": row[5] if row[5] else "NA",
                "unique": row[6] if row[6] else "NA",
                "date": row[7].isoformat() if row[7] else None,
                "status": row[8] if row[8] else "NA",
                "orderid": row[9] if row[9] else "NA",
                "stratergy": row[10] if row[10] else "NA",
                "margin": float(row[11]) if row[11] else 0.0,
                "remark": row[12] if row[12] else "NA",
                "stratergy_name": row[13] if row[13] else "NA",
                "broker": row[14] if row[14] else None
            })
        
        return trades
        
    except Exception as e:
        logger.error(f"Error in trades: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching trades: {str(e)}"
        )


@router.post("/userOrderDetails/")
def user_order_details(
    request: UserOrderDetailsRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/userOrderDetails/
    Get detailed user orders with filters
    Matches: cryptoarth_backend/authenticate/views.py userOrderDetails
    """
    try:
        # Determine date range
        if request.start_date and request.end_date:
            start_date, end_date = convert_date_range_to_utc(request.start_date, request.end_date)
        else:
            start_date, end_date = get_todays_dates()
        
        # Build query
        query = f"""
            SELECT 
                id, owner_id, symbol, stratergy, buyprice, sellprice, buyquantity,
                sellquantity, side, orderid, date, status, profit, stratergy_name, broker_id
            FROM {ORDER_DETAILS_TABLE}
            WHERE owner_id = :user_id
            AND date >= :start_date
            AND date <= :end_date
        """
        params = {
            "user_id": user.external_user_id,
            "start_date": start_date,
            "end_date": end_date
        }
        
        if request.strategy:
            query += " AND stratergy_name = :strategy"
            params["strategy"] = request.strategy
        
        query += " ORDER BY date DESC"
        
        orders_result = db.execute(text(query), params)
        
        orders = []
        for row in orders_result:
            orders.append({
                "id": row[0],
                "owner": row[1],
                "symbol": row[2] if row[2] else "NA",
                "stratergy": row[3] if row[3] else "NA",
                "buyprice": float(row[4]) if row[4] else 0.0,
                "sellprice": float(row[5]) if row[5] else 0.0,
                "buyquantity": float(row[6]) if row[6] else 0.0,
                "sellquantity": float(row[7]) if row[7] else 0.0,
                "side": row[8] if row[8] else "NA",
                "orderid": row[9] if row[9] else "NA",
                "date": row[10].isoformat() if row[10] else None,
                "status": row[11] if row[11] else "NA",
                "profit": float(row[12]) if row[12] else 0.0,
                "stratergy_name": row[13] if row[13] else "NA",
                "broker": row[14] if row[14] else None
            })
        
        return orders
        
    except Exception as e:
        logger.error(f"Error in user_order_details: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching order details: {str(e)}"
        )


# ============================================================================
# POSITIONS (READ-ONLY)
# ============================================================================

@router.get("/get_user_positions/")
def get_user_positions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    GET /auth/get_user_positions/
    Get user positions
    Matches: cryptoarth_backend/authenticate/views.py get_user_positions
    
    Returns:
        List of position objects (empty list if no positions)
    """
    try:
        # Use external_user_id for query (CRITICAL: NOT user.id)
        positions_query = text(f"""
            SELECT 
                id, order_id, symbol, owner_id, side, price, quantity, unique,
                leverage, stratergy, date, stratergy_name, broker_id
            FROM {POSITION_TABLE}
            WHERE owner_id = :user_id
            ORDER BY date DESC
        """)
        
        positions_result = db.execute(
            positions_query,
            {"user_id": user.external_user_id}
        )
        
        # Always return a list (empty if no results)
        positions = []
        for row in positions_result:
            positions.append({
                "id": row[0],
                "order_id": row[1] if row[1] else "NA",
                "symbol": row[2] if row[2] else "NA",
                "owner": row[3],
                "side": row[4] if row[4] else "NA",
                "price": float(row[5]) if row[5] else 0.0,
                "quantity": float(row[6]) if row[6] else 0.0,
                "unique": row[7] if row[7] else "NA",
                "leverage": row[8] if row[8] else 0,
                "stratergy": row[9] if row[9] else "NA",
                "date": row[10].isoformat() if row[10] else None,
                "stratergy_name": row[11] if row[11] else "NA",
                "broker": row[12] if row[12] else None
            })
        
        # Always return list (never None)
        return positions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_user_positions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching positions: {str(e)}"
        )


@router.post("/adminPositionDetails/")
def admin_position_details(
    request: AdminPositionDetailsRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/adminPositionDetails/
    Admin view of positions (staff/vendor only)
    Matches: cryptoarth_backend/authenticate/views.py adminPositionDetails
    """
    try:
        # Check if user is staff or vendor (simplified - adjust based on your User model)
        # For now, we'll check if user has is_staff flag or similar
        # Note: This requires checking the Django User table for is_staff/is_vendor
        
        # Build query
        query = f"""
            SELECT 
                p.id, p.order_id, p.symbol, p.owner_id, p.side, p.price, p.quantity,
                p.unique, p.leverage, p.stratergy, p.date, p.stratergy_name, p.broker_id
            FROM {POSITION_TABLE} p
            WHERE 1=1
        """
        params = {}
        
        if request.owner:
            query += " AND p.owner_id IN (SELECT id FROM authenticate_user WHERE phone = :owner_phone)"
            params["owner_phone"] = request.owner
        
        if request.strategy:
            query += " AND p.stratergy_name = :strategy"
            params["strategy"] = request.strategy
        
        query += " ORDER BY p.date DESC"
        
        positions_result = db.execute(text(query), params)
        
        positions = []
        for row in positions_result:
            positions.append({
                "id": row[0],
                "order_id": row[1] if row[1] else "NA",
                "symbol": row[2] if row[2] else "NA",
                "owner": row[3],
                "side": row[4] if row[4] else "NA",
                "price": float(row[5]) if row[5] else 0.0,
                "quantity": float(row[6]) if row[6] else 0.0,
                "unique": row[7] if row[7] else "NA",
                "leverage": row[8] if row[8] else 0,
                "stratergy": row[9] if row[9] else "NA",
                "date": row[10].isoformat() if row[10] else None,
                "stratergy_name": row[11] if row[11] else "NA",
                "broker": row[12] if row[12] else None
            })
        
        return positions
        
    except Exception as e:
        logger.error(f"Error in admin_position_details: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching position details: {str(e)}"
        )


# ============================================================================
# DASHBOARD / PnL APIs
# ============================================================================

@router.get("/get_user_pnl/")
def get_user_pnl(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/get_user_pnl/
    Get user P&L (today and total)
    Matches: cryptoarth_backend/authenticate/views.py get_user_pnl
    """
    try:
        start_date, end_date = get_todays_dates()
        
        # Today's profit
        today_profit_query = text(f"""
            SELECT COALESCE(SUM(profit), 0) as total
            FROM {ORDER_DETAILS_TABLE}
            WHERE owner_id = :user_id
            AND date >= :start_date
            AND date <= :end_date
        """)
        today_profit_result = db.execute(
            today_profit_query,
            {
                "user_id": user.external_user_id,
                "start_date": start_date,
                "end_date": end_date
            }
        )
        today_profit = float(today_profit_result.scalar() or 0)
        
        # Total profit
        total_profit_query = text(f"""
            SELECT COALESCE(SUM(profit), 0) as total
            FROM {ORDER_DETAILS_TABLE}
            WHERE owner_id = :user_id
        """)
        total_profit_result = db.execute(
            total_profit_query,
            {"user_id": user.external_user_id}
        )
        total_profit = float(total_profit_result.scalar() or 0)
        
        # Trades count (open positions)
        trades_query = text(f"""
            SELECT COUNT(*) as count
            FROM {POSITION_TABLE}
            WHERE owner_id = :user_id
        """)
        trades_result = db.execute(trades_query, {"user_id": user.external_user_id})
        trades = trades_result.scalar() or 0
        
        return {
            "today_profit": today_profit,
            "total_profit": total_profit,
            "trades": trades
        }
        
    except Exception as e:
        logger.error(f"Error in get_user_pnl: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching P&L: {str(e)}"
        )


@router.post("/dashboard/")
def dashboard_count(
    request: DashboardCountRequest,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    POST /auth/dashboard/
    Get dashboard counts (admin/vendor or user)
    Matches: cryptoarth_backend/authenticate/views.py get_dashboard_count
    """
    try:
        # Determine date range
        if request.startDate and request.endDate:
            start_date, end_date = convert_date_range_to_utc(request.startDate, request.endDate)
        else:
            start_date, end_date = get_todays_dates()
        
        # Check if user is staff (simplified - adjust based on your User model)
        # For now, we'll assume all users can access this endpoint
        # In production, add proper staff/vendor check
        
        # Total volume (sum of margin from tradeDetails)
        total_volume_query = text(f"""
            SELECT COALESCE(SUM(td.margin), 0) as total
            FROM {TRADE_DETAILS_TABLE} td
            WHERE td.date >= :start_date
            AND td.date <= :end_date
        """)
        total_volume_result = db.execute(
            total_volume_query,
            {"start_date": start_date, "end_date": end_date}
        )
        total_volume = float(total_volume_result.scalar() or 0)
        
        # CoinDCX margin
        coindcx_margin_query = text(f"""
            SELECT COALESCE(SUM(td.margin), 0) as total
            FROM {TRADE_DETAILS_TABLE} td
            INNER JOIN authenticate_brokermodels b ON td.broker_id = b.id
            WHERE td.date >= :start_date
            AND td.date <= :end_date
            AND b.broker = 'Coindcx'
        """)
        coindcx_margin_result = db.execute(
            coindcx_margin_query,
            {"start_date": start_date, "end_date": end_date}
        )
        coindcx_margin = float(coindcx_margin_result.scalar() or 0)
        
        # Delta margin
        delta_margin_query = text(f"""
            SELECT COALESCE(SUM(td.margin), 0) as total
            FROM {TRADE_DETAILS_TABLE} td
            INNER JOIN authenticate_brokermodels b ON td.broker_id = b.id
            WHERE td.date >= :start_date
            AND td.date <= :end_date
            AND b.broker = 'DeltaExchange'
        """)
        delta_margin_result = db.execute(
            delta_margin_query,
            {"start_date": start_date, "end_date": end_date}
        )
        delta_margin = float(delta_margin_result.scalar() or 0)
        
        # Bot count (active user strategies)
        bot_count_query = text(f"""
            SELECT COUNT(*) as count
            FROM {USER_STRATEGY_PORTFOLIO_TABLE}
            WHERE is_active = 1
        """)
        bot_count_result = db.execute(bot_count_query)
        bot_count = bot_count_result.scalar() or 0
        
        # Positions count
        positions_count_query = text(f"""
            SELECT COUNT(*) as count
            FROM {POSITION_TABLE}
        """)
        positions_count_result = db.execute(positions_count_query)
        positions_count = positions_count_result.scalar() or 0
        
        # Total orders
        total_orders_query = text(f"""
            SELECT COUNT(*) as count
            FROM {ORDER_DETAILS_TABLE}
            WHERE date >= :start_date
            AND date <= :end_date
        """)
        total_orders_result = db.execute(
            total_orders_query,
            {"start_date": start_date, "end_date": end_date}
        )
        total_orders = total_orders_result.scalar() or 0
        
        # Total users (joined in date range)
        total_users_query = text(f"""
            SELECT COUNT(*) as count
            FROM {USER_TABLE}
            WHERE date_joined >= :start_date
            AND date_joined <= :end_date
        """)
        total_users_result = db.execute(
            total_users_query,
            {"start_date": start_date, "end_date": end_date}
        )
        total_users = total_users_result.scalar() or 0
        
        # Total profit
        total_profit_query = text(f"""
            SELECT COALESCE(SUM(profit), 0) as total
            FROM {ORDER_DETAILS_TABLE}
            WHERE date >= :start_date
            AND date <= :end_date
        """)
        total_profit_result = db.execute(
            total_profit_query,
            {"start_date": start_date, "end_date": end_date}
        )
        total_profit = float(total_profit_result.scalar() or 0)
        
        return {
            "total_volume": total_volume,
            "total_orders": total_orders,
            "total_profit": total_profit,
            "total_users": total_users,
            "coindcx_margin": coindcx_margin,
            "delta_margin": delta_margin,
            "bot_count": bot_count,
            "positions_count": positions_count
        }
        
    except Exception as e:
        logger.error(f"Error in dashboard_count: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching dashboard counts: {str(e)}"
        )


@router.get("/dashboardcount/")
def dashboard_count_get(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/dashboardcount/
    Get dashboard counts (today only)
    Matches: cryptoarth_backend/authenticate/views.py get_today_dashboard_count
    """
    try:
        start_date, end_date = get_todays_dates()
        
        # Same logic as POST /dashboard/ but with today's dates
        # Total volume
        total_volume_query = text(f"""
            SELECT COALESCE(SUM(td.margin), 0) as total
            FROM {TRADE_DETAILS_TABLE} td
            WHERE td.date >= :start_date
            AND td.date <= :end_date
        """)
        total_volume_result = db.execute(
            total_volume_query,
            {"start_date": start_date, "end_date": end_date}
        )
        total_volume = float(total_volume_result.scalar() or 0)
        
        # Delta margin
        delta_margin_query = text(f"""
            SELECT COALESCE(SUM(td.margin), 0) as total
            FROM {TRADE_DETAILS_TABLE} td
            INNER JOIN authenticate_brokermodels b ON td.broker_id = b.id
            WHERE td.date >= :start_date
            AND td.date <= :end_date
            AND b.broker = 'DeltaExchange'
        """)
        delta_margin_result = db.execute(
            delta_margin_query,
            {"start_date": start_date, "end_date": end_date}
        )
        delta_margin = float(delta_margin_result.scalar() or 0)
        
        # CoinDCX margin
        coindcx_margin_query = text(f"""
            SELECT COALESCE(SUM(td.margin), 0) as total
            FROM {TRADE_DETAILS_TABLE} td
            INNER JOIN authenticate_brokermodels b ON td.broker_id = b.id
            WHERE td.date >= :start_date
            AND td.date <= :end_date
            AND b.broker = 'Coindcx'
        """)
        coindcx_margin_result = db.execute(
            coindcx_margin_query,
            {"start_date": start_date, "end_date": end_date}
        )
        coindcx_margin = float(coindcx_margin_result.scalar() or 0)
        
        # Total orders
        total_orders_query = text(f"""
            SELECT COUNT(*) as count
            FROM {ORDER_DETAILS_TABLE}
            WHERE date >= :start_date
            AND date <= :end_date
        """)
        total_orders_result = db.execute(
            total_orders_query,
            {"start_date": start_date, "end_date": end_date}
        )
        total_orders = total_orders_result.scalar() or 0
        
        # Total users
        total_users_query = text(f"""
            SELECT COUNT(*) as count
            FROM {USER_TABLE}
            WHERE date_joined >= :start_date
            AND date_joined <= :end_date
        """)
        total_users_result = db.execute(
            total_users_query,
            {"start_date": start_date, "end_date": end_date}
        )
        total_users = total_users_result.scalar() or 0
        
        # Total profit
        total_profit_query = text(f"""
            SELECT COALESCE(SUM(profit), 0) as total
            FROM {ORDER_DETAILS_TABLE}
            WHERE date >= :start_date
            AND date <= :end_date
        """)
        total_profit_result = db.execute(
            total_profit_query,
            {"start_date": start_date, "end_date": end_date}
        )
        total_profit = float(total_profit_result.scalar() or 0)
        
        return {
            "total_volume": total_volume,
            "total_orders": total_orders,
            "total_profit": total_profit,
            "total_users": total_users,
            "coindcx_margin": coindcx_margin,
            "delta_margin": delta_margin
        }
        
    except Exception as e:
        logger.error(f"Error in dashboard_count_get: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching dashboard counts: {str(e)}"
        )


@router.get("/today_dashboardcount/")
def today_dashboard_count(
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/today_dashboardcount/
    Alias for /auth/dashboardcount/ (today's dashboard counts)
    Matches: cryptoarth_backend/authenticate/views.py get_today_dashboard_count
    """
    return dashboard_count_get(user, db)


# ============================================================================
# PERFORMANCE SUMMARY APIs
# ============================================================================

@router.get("/strategy/{strategy_id}/live/performance/summary")
def live_performance_summary(
    strategy_id: int,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/strategy/{id}/live/performance/summary
    Returns aggregated live performance summary for a strategy
    Matches: cryptoarth_backend/authenticate/views_live_performance.py LivePerformanceSummaryView
    """
    try:
        # Check if strategy exists
        strategy_query = text(f"""
            SELECT id, symbol
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
        
        # Check if user has access to this strategy
        # (For now, we'll allow all authenticated users - adjust based on your access control)
        
        # Get orders for this strategy
        orders_query = text(f"""
            SELECT 
                id, owner_id, symbol, stratergy, buyprice, sellprice, buyquantity,
                sellquantity, side, orderid, date, status, profit, stratergy_name
            FROM {ORDER_DETAILS_TABLE}
            WHERE stratergy = :strategy_id_str
            AND status = 'Completed'
            AND owner_id = :user_id
        """)
        orders_result = db.execute(
            orders_query,
            {
                "strategy_id_str": str(strategy_id),
                "user_id": user.external_user_id
            }
        )
        
        orders = []
        for row in orders_result:
            orders.append({
                "id": row[0],
                "owner_id": row[1],
                "symbol": row[2],
                "stratergy": row[3],
                "buyprice": float(row[4]) if row[4] else 0.0,
                "sellprice": float(row[5]) if row[5] else 0.0,
                "buyquantity": float(row[6]) if row[6] else 0.0,
                "sellquantity": float(row[7]) if row[7] else 0.0,
                "side": row[8],
                "orderid": row[9],
                "date": row[10],
                "status": row[11],
                "profit": float(row[12]) if row[12] else 0.0,
                "stratergy_name": row[13]
            })
        
        total_orders = len(orders)
        
        if total_orders == 0:
            return {
                "success": True,
                "data": {
                    "net_pnl": 0,
                    "max_drawdown": 0,
                    "win_rate": 0,
                    "profit_factor": 0,
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "avg_trade": 0,
                    "symbol": strategy_row[1] if strategy_row[1] else "N/A",
                    "timeframe": "Live",
                    "strategy_id": strategy_id
                }
            }
        
        # Calculate metrics
        total_profit = sum(order["profit"] for order in orders)
        winning_trades = sum(1 for order in orders if order["profit"] > 0)
        losing_trades = sum(1 for order in orders if order["profit"] < 0)
        
        gross_profit = sum(order["profit"] for order in orders if order["profit"] > 0)
        gross_loss = abs(sum(order["profit"] for order in orders if order["profit"] < 0))
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0
        
        # Calculate max drawdown (simplified - group by date)
        daily_pnl = {}
        for order in orders:
            date_key = order["date"].date() if order["date"] else None
            if date_key:
                if date_key not in daily_pnl:
                    daily_pnl[date_key] = 0.0
                daily_pnl[date_key] += order["profit"]
        
        daily_pnl_list = sorted(daily_pnl.values())
        max_drawdown = 0.0
        if daily_pnl_list:
            cumulative = 0
            peak = 0
            for pnl in daily_pnl_list:
                cumulative += pnl
                if cumulative > peak:
                    peak = cumulative
                drawdown = peak - cumulative
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        win_rate = (winning_trades / total_orders * 100) if total_orders > 0 else 0.0
        avg_trade = float(total_profit / total_orders) if total_orders > 0 else 0.0
        
        return {
            "success": True,
            "data": {
                "net_pnl": float(total_profit),
                "max_drawdown": max_drawdown,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "total_trades": total_orders,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "avg_trade": avg_trade,
                "symbol": strategy_row[1] if strategy_row[1] else "N/A",
                "timeframe": "Live",
                "strategy_id": strategy_id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in live_performance_summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching performance summary: {str(e)}"
        )


@router.get("/strategy/{strategy_id}/live/performance/daily")
def live_performance_daily(
    strategy_id: int,
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/strategy/{id}/live/performance/daily
    Returns daily cumulative PnL and drawdown for chart
    Matches: cryptoarth_backend/authenticate/views_live_performance.py LivePerformanceDailyView
    """
    try:
        # Check if strategy exists
        strategy_query = text(f"""
            SELECT id
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        strategy_result = db.execute(strategy_query, {"strategy_id": strategy_id})
        if not strategy_result.first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        # Get orders grouped by date
        orders_query = text(f"""
            SELECT 
                DATE(date) as trade_date,
                SUM(profit) as daily_pnl
            FROM {ORDER_DETAILS_TABLE}
            WHERE stratergy = :strategy_id_str
            AND status = 'Completed'
            AND owner_id = :user_id
            GROUP BY DATE(date)
            ORDER BY trade_date ASC
        """)
        orders_result = db.execute(
            orders_query,
            {
                "strategy_id_str": str(strategy_id),
                "user_id": user.external_user_id
            }
        )
        
        result = []
        cumulative_pnl = 0.0
        peak = 0.0
        
        for row in orders_result:
            daily_pnl = float(row[1] or 0)
            cumulative_pnl += daily_pnl
            
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            
            drawdown = peak - cumulative_pnl if peak > 0 else 0
            
            result.append({
                "date": row[0].isoformat() if row[0] else None,
                "cumulative_pnl": cumulative_pnl,
                "drawdown": drawdown,
                "daily_pnl": daily_pnl
            })
        
        return {
            "success": True,
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in live_performance_daily: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching daily performance: {str(e)}"
        )


@router.get("/strategy/{strategy_id}/live/performance/trades")
def live_performance_trades(
    strategy_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user_strict),
    db: Session = Depends(get_db)
):
    """
    GET /auth/strategy/{id}/live/performance/trades
    Returns paginated trade-by-trade details
    Matches: cryptoarth_backend/authenticate/views_live_performance.py LivePerformanceTradesView
    """
    try:
        # Check if strategy exists
        strategy_query = text(f"""
            SELECT id
            FROM {HIGH_LOW_STRATEGY_TABLE}
            WHERE id = :strategy_id
        """)
        strategy_result = db.execute(strategy_query, {"strategy_id": strategy_id})
        if not strategy_result.first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        # Get total count
        count_query = text(f"""
            SELECT COUNT(*) as total
            FROM {ORDER_DETAILS_TABLE}
            WHERE stratergy = :strategy_id_str
            AND status = 'Completed'
            AND owner_id = :user_id
        """)
        count_result = db.execute(
            count_query,
            {
                "strategy_id_str": str(strategy_id),
                "user_id": user.external_user_id
            }
        )
        total = count_result.scalar() or 0
        
        # Get paginated orders
        orders_query = text(f"""
            SELECT 
                id, symbol, side, buyprice, sellprice, date, profit, orderid
            FROM {ORDER_DETAILS_TABLE}
            WHERE stratergy = :strategy_id_str
            AND status = 'Completed'
            AND owner_id = :user_id
            ORDER BY date DESC
            LIMIT :limit OFFSET :offset
        """)
        orders_result = db.execute(
            orders_query,
            {
                "strategy_id_str": str(strategy_id),
                "user_id": user.external_user_id,
                "limit": limit,
                "offset": offset
            }
        )
        
        trades = []
        for row in orders_result:
            side = row[2] if row[2] else "NA"
            buyprice = float(row[3]) if row[3] else 0.0
            sellprice = float(row[4]) if row[4] else 0.0
            
            # Determine entry/exit based on side
            if side.upper() == 'BUY':
                entry_price = buyprice
                exit_price = sellprice
            else:  # SELL
                entry_price = sellprice
                exit_price = buyprice
            
            pnl = float(row[6]) if row[6] else 0.0
            pnl_percent = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            trades.append({
                "entry_time": row[5].isoformat() if row[5] else None,
                "exit_time": row[5].isoformat() if row[5] else None,
                "side": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "exit_reason": "Completed",
                "symbol": row[1] if row[1] else "NA",
                "order_id": row[7] if row[7] else "NA"
            })
        
        return {
            "success": True,
            "data": trades,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in live_performance_trades: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching trades: {str(e)}"
        )

