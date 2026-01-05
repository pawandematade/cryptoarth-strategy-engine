"""
Strategy Performance API Routes
Provides lightweight performance metrics for strategy cards
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import json

from common.redis import redis_client
from strategies.loader import load_strategies

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================
# RESPONSE MODEL
# ============================

class StrategyPerformanceResponse(BaseModel):
    success: bool
    strategy_id: str
    metrics: Optional[Dict[str, Any]] = None
    risk_level: Optional[str] = None
    message: Optional[str] = None


# ============================
# RISK LEVEL CALCULATION
# ============================

def calculate_risk_level(metrics: Dict[str, Any]) -> str:
    """
    Calculate risk level based on strategy metrics.
    """

    if not metrics:
        return "High"

    win_rate = metrics.get("win_rate", 0)
    sharpe_ratio = metrics.get("sharpe_ratio", 0)
    max_drawdown = abs(metrics.get("max_drawdown", 0))

    risk_score = 0

    # Win rate
    if win_rate >= 60:
        risk_score += 0
    elif win_rate >= 40:
        risk_score += 1
    else:
        risk_score += 2

    # Sharpe
    if sharpe_ratio >= 1.5:
        risk_score += 0
    elif sharpe_ratio >= 0.5:
        risk_score += 1
    else:
        risk_score += 2

    # Drawdown
    if max_drawdown < 10:
        risk_score += 0
    elif max_drawdown < 25:
        risk_score += 1
    else:
        risk_score += 2

    if risk_score <= 2:
        return "Low"
    elif risk_score <= 4:
        return "Medium"
    return "High"


# ============================
# METRICS EXTRACTION (FIXED)
# ============================

def extract_lightweight_metrics(backtest_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract only UI-safe, lightweight metrics.
    """

    max_dd = backtest_results.get("maxDrawdown", 0)

    # Guard: if trades > 1 and DD is zero → treat as unavailable
    total_trades = backtest_results.get("totalTrades", 0)
    if total_trades > 1 and max_dd == 0:
        max_dd = None

    return {
        "net_pnl": backtest_results.get("netPNL", 0),
        "win_rate": backtest_results.get("winRate", 0),
        "max_drawdown": max_dd,
        "total_trades": total_trades,
        "sharpe_ratio": backtest_results.get("sharpeRatio", 0),
        "profit_factor": backtest_results.get("profitFactor", 0),
        "total_return": backtest_results.get("totalReturn", 0),
        "realized_pnl": backtest_results.get("realizedPNL", 0),
    }


# ============================
# API ENDPOINT
# ============================

@router.get(
    "/strategy/performance/{strategy_id}",
    response_model=StrategyPerformanceResponse
)
def get_strategy_performance(strategy_id: str):
    """
    Returns lightweight performance metrics for a strategy card.
    Uses Redis cached backtest results only.
    """

    try:
        # --------------------
        # Load strategy
        # --------------------
        redis_key = f"STRATEGY:{strategy_id}"
        strategy_data = redis_client.get(redis_key)

        if strategy_data:
            strategy = json.loads(strategy_data)
        else:
            try:
                strategy_id_int = int(strategy_id)
                strategies = load_strategies()
                strategy = next(
                    (s for s in strategies if s.get("id") == strategy_id_int),
                    None
                )
                if not strategy:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Strategy not found: {strategy_id}"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Strategy not found: {strategy_id}"
                )

        # --------------------
        # Load cached backtest
        # --------------------
        backtest_key = f"BACKTEST:{strategy_id}"
        cached_backtest = redis_client.get(backtest_key)

        if not cached_backtest:
            return StrategyPerformanceResponse(
                success=False,
                strategy_id=strategy_id,
                message="No backtest results found. Please run a backtest first."
            )

        try:
            backtest_results = json.loads(cached_backtest)
        except json.JSONDecodeError:
            return StrategyPerformanceResponse(
                success=False,
                strategy_id=strategy_id,
                message="Invalid backtest data. Please run backtest again."
            )

        metrics = extract_lightweight_metrics(backtest_results)
        risk_level = calculate_risk_level(metrics)

        return StrategyPerformanceResponse(
            success=True,
            strategy_id=strategy_id,
            metrics=metrics,
            risk_level=risk_level
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error getting strategy performance: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
