"""
Trade Reporting APIs (Read-Only)

APIs for generating reports from strategy_trades table.
All reports are read-only aggregations from stored trade data.
"""

from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_, or_
from sqlalchemy.sql import text
from common.db import get_db
from app.models import StrategyTrade
from decimal import Decimal
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()


def _calculate_max_drawdown(net_pnl_list: List[float]) -> float:
    """
    Calculate max drawdown from a list of net PnL values.
    
    Args:
        net_pnl_list: List of net PnL values (cumulative)
    
    Returns:
        Max drawdown as a percentage
    """
    if not net_pnl_list:
        return 0.0
    
    peak = net_pnl_list[0]
    max_dd = 0.0
    
    for pnl in net_pnl_list:
        if pnl > peak:
            peak = pnl
        drawdown = ((peak - pnl) / peak * 100) if peak > 0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown
    
    return max_dd


@router.get("/reports/summary")
def get_summary_report(
    user_phone: str = Query(..., description="User phone number (10 digits)"),
    strategy_id: int = Query(..., description="Strategy ID"),
    db: Session = Depends(get_db)
):
    """
    Get summary report for a strategy.
    
    Aggregates all trades for the given user_phone and strategy_id.
    
    Returns:
        {
            "net_pnl": number,
            "gross_pnl": number,
            "brokerage": number,
            "win_rate": number,
            "max_drawdown": number,
            "total_trades": number
        }
    """
    try:
        # Query trades for this user and strategy
        trades = db.query(StrategyTrade).filter(
            and_(
                StrategyTrade.user_phone == user_phone,
                StrategyTrade.strategy_id == strategy_id
            )
        ).order_by(StrategyTrade.exit_time.asc()).all()
        
        if not trades:
            return {
                "net_pnl": 0.0,
                "gross_pnl": 0.0,
                "brokerage": 0.0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "total_trades": 0
            }
        
        # Aggregate metrics
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.is_win)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        
        gross_pnl = float(sum(t.gross_pnl for t in trades))
        brokerage = float(sum(t.brokerage for t in trades))
        net_pnl = float(sum(t.net_pnl for t in trades))
        
        # Calculate max drawdown (cumulative net PnL)
        cumulative_pnl = []
        running_total = 0.0
        for trade in trades:
            running_total += float(trade.net_pnl)
            cumulative_pnl.append(running_total)
        
        max_drawdown = _calculate_max_drawdown(cumulative_pnl)
        
        return {
            "net_pnl": round(net_pnl, 2),
            "gross_pnl": round(gross_pnl, 2),
            "brokerage": round(brokerage, 2),
            "win_rate": round(win_rate, 2),
            "max_drawdown": round(max_drawdown, 2),
            "total_trades": total_trades
        }
        
    except Exception as e:
        logger.error(f"Error generating summary report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating summary report: {str(e)}"
        )


@router.get("/reports/monthly")
def get_monthly_report(
    user_phone: str = Query(..., description="User phone number (10 digits)"),
    strategy_id: int = Query(..., description="Strategy ID"),
    db: Session = Depends(get_db)
):
    """
    Get monthly report grouped by YEAR(exit_time) and MONTH(exit_time).
    
    Only returns months with trades (excludes months with 0 trades).
    
    Returns:
        {
            "YYYY": {
                "MM": {
                    "net_pnl": number,
                    "gross_pnl": number,
                    "brokerage": number,
                    "win_rate": number,
                    "total_trades": number
                },
                ...
            },
            ...
        }
    """
    try:
        # Query trades grouped by year and month
        # Using raw SQL for cleaner grouping
        query = text("""
            SELECT 
                YEAR(exit_time) as year,
                MONTH(exit_time) as month,
                COUNT(*) as total_trades,
                SUM(gross_pnl) as gross_pnl,
                SUM(brokerage) as brokerage,
                SUM(net_pnl) as net_pnl,
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins
            FROM strategy_trades
            WHERE user_phone = :user_phone AND strategy_id = :strategy_id
            GROUP BY YEAR(exit_time), MONTH(exit_time)
            ORDER BY year ASC, month ASC
        """)
        
        result = db.execute(
            query,
            {"user_phone": user_phone, "strategy_id": strategy_id}
        ).fetchall()
        
        monthly_data = {}
        
        for row in result:
            year = str(row.year)
            month = str(row.month).zfill(2)  # Zero-padded month
            
            if year not in monthly_data:
                monthly_data[year] = {}
            
            total_trades = row.total_trades
            wins = row.wins
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            
            monthly_data[year][month] = {
                "net_pnl": round(float(row.net_pnl or 0), 2),
                "gross_pnl": round(float(row.gross_pnl or 0), 2),
                "brokerage": round(float(row.brokerage or 0), 2),
                "win_rate": round(win_rate, 2),
                "total_trades": total_trades
            }
        
        return monthly_data
        
    except Exception as e:
        logger.error(f"Error generating monthly report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating monthly report: {str(e)}"
        )


@router.get("/reports/yearly")
def get_yearly_report(
    user_phone: str = Query(..., description="User phone number (10 digits)"),
    strategy_id: int = Query(..., description="Strategy ID"),
    db: Session = Depends(get_db)
):
    """
    Get yearly report aggregated from monthly data.
    
    Year auto-expands if months > 1.
    
    Returns:
        {
            "YYYY": {
                "net_pnl": number,
                "gross_pnl": number,
                "brokerage": number,
                "win_rate": number,
                "total_trades": number,
                "months": ["MM", ...]  // List of months with trades
            },
            ...
        }
    """
    try:
        # Query trades grouped by year
        query = text("""
            SELECT 
                YEAR(exit_time) as year,
                COUNT(*) as total_trades,
                SUM(gross_pnl) as gross_pnl,
                SUM(brokerage) as brokerage,
                SUM(net_pnl) as net_pnl,
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                GROUP_CONCAT(DISTINCT MONTH(exit_time) ORDER BY MONTH(exit_time)) as months
            FROM strategy_trades
            WHERE user_phone = :user_phone AND strategy_id = :strategy_id
            GROUP BY YEAR(exit_time)
            ORDER BY year ASC
        """)
        
        result = db.execute(
            query,
            {"user_phone": user_phone, "strategy_id": strategy_id}
        ).fetchall()
        
        yearly_data = {}
        
        for row in result:
            year = str(row.year)
            
            total_trades = row.total_trades
            wins = row.wins
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            
            # Parse months list
            months_list = []
            if row.months:
                try:
                    months_list = [str(int(m)).zfill(2) for m in row.months.split(',') if m.strip().isdigit()]
                except (ValueError, AttributeError):
                    months_list = []
            
            yearly_data[year] = {
                "net_pnl": round(float(row.net_pnl or 0), 2),
                "gross_pnl": round(float(row.gross_pnl or 0), 2),
                "brokerage": round(float(row.brokerage or 0), 2),
                "win_rate": round(win_rate, 2),
                "total_trades": total_trades,
                "months": months_list
            }
        
        return yearly_data
        
    except Exception as e:
        logger.error(f"Error generating yearly report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating yearly report: {str(e)}"
        )

