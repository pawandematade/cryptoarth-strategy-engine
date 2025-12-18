"""
Strategy Performance API Routes
Provides lightweight performance metrics for strategy cards
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import json
from app.store.redis_client import redis_client
from app.strategies.loader import load_strategies

logger = logging.getLogger(__name__)

router = APIRouter()


class StrategyPerformanceResponse(BaseModel):
    """Response model for strategy performance"""
    success: bool
    strategy_id: str
    metrics: Optional[Dict[str, Any]] = None
    risk_level: Optional[str] = None
    message: Optional[str] = None


def calculate_risk_level(metrics: Dict[str, Any]) -> str:
    """
    Calculate risk level based on strategy metrics
    
    Risk Level Calculation:
    - Low: Win rate > 60%, Sharpe > 1.5, Max Drawdown < 10%
    - Medium: Win rate 40-60%, Sharpe 0.5-1.5, Max Drawdown 10-25%
    - High: Win rate < 40%, Sharpe < 0.5, Max Drawdown > 25%
    
    Args:
        metrics: Dictionary with backtest metrics
    
    Returns:
        str: 'Low', 'Medium', or 'High'
    """
    if not metrics:
        return 'High'  # Default to high risk if no metrics
    
    win_rate = metrics.get('winRate', 0)
    sharpe_ratio = metrics.get('sharpeRatio', 0)
    max_drawdown = abs(metrics.get('maxDrawdown', 0))
    
    # Convert drawdown percentage to absolute value if needed
    if max_drawdown > 100:
        max_drawdown = max_drawdown / 100  # Assume it's in basis points
    
    # Score-based risk calculation
    risk_score = 0
    
    # Win rate component (0-3 points)
    if win_rate >= 60:
        risk_score += 0  # Low risk
    elif win_rate >= 40:
        risk_score += 1  # Medium risk
    else:
        risk_score += 2  # High risk
    
    # Sharpe ratio component (0-3 points)
    if sharpe_ratio >= 1.5:
        risk_score += 0  # Low risk
    elif sharpe_ratio >= 0.5:
        risk_score += 1  # Medium risk
    else:
        risk_score += 2  # High risk
    
    # Drawdown component (0-3 points)
    if max_drawdown < 10:
        risk_score += 0  # Low risk
    elif max_drawdown < 25:
        risk_score += 1  # Medium risk
    else:
        risk_score += 2  # High risk
    
    # Determine risk level based on total score
    if risk_score <= 2:
        return 'Low'
    elif risk_score <= 4:
        return 'Medium'
    else:
        return 'High'


def extract_lightweight_metrics(backtest_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract lightweight metrics from full backtest results
    
    Args:
        backtest_results: Full backtest results dictionary
    
    Returns:
        Dictionary with only essential metrics
    """
    return {
        'net_pnl': backtest_results.get('netPNL', 0),
        'win_rate': backtest_results.get('winRate', 0),
        'max_drawdown': backtest_results.get('maxDrawdown', 0),
        'total_trades': backtest_results.get('totalTrades', 0),
        'sharpe_ratio': backtest_results.get('sharpeRatio', 0),
        'profit_factor': backtest_results.get('profitFactor', 0),
        'total_return': backtest_results.get('totalReturn', 0),
        'realized_pnl': backtest_results.get('realizedPNL', 0),
    }


@router.get("/strategy/performance/{strategy_id}", response_model=StrategyPerformanceResponse)
def get_strategy_performance(strategy_id: str):
    """
    Get performance metrics for a strategy.
    
    This endpoint retrieves cached backtest results from Redis.
    If no cached results are found, returns a message indicating
    that a backtest needs to be run first.
    
    Args:
        strategy_id: Strategy ID (UUID string for secure format, or integer for legacy)
    
    Returns:
        StrategyPerformanceResponse with metrics and risk_level
    """
    try:
        # Try to get strategy from Redis first (secure format with UUID)
        redis_key = f"STRATEGY:{strategy_id}"
        strategy_data = redis_client.get(redis_key)
        
        if strategy_data:
            # Strategy found in Redis (secure format)
            strategy = json.loads(strategy_data)
            logger.info(f"Found strategy in Redis: {strategy_id}")
        else:
            # Try to get from JSON file (legacy format with integer ID)
            try:
                strategy_id_int = int(strategy_id)
                strategies = load_strategies()
                strategy = next((s for s in strategies if s.get("id") == strategy_id_int), None)
                
                if not strategy:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Strategy not found: {strategy_id}"
                    )
                logger.info(f"Found strategy in JSON file: {strategy_id}")
            except ValueError:
                # strategy_id is not an integer, and not found in Redis
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Strategy not found: {strategy_id}"
                )
        
        # Check for cached backtest results in Redis
        backtest_key = f"BACKTEST:{strategy_id}"
        cached_backtest = redis_client.get(backtest_key)
        
        if not cached_backtest:
            # No cached backtest results
            return StrategyPerformanceResponse(
                success=False,
                strategy_id=strategy_id,
                metrics=None,
                risk_level=None,
                message="No backtest results found. Please run a backtest first."
            )
        
        # Parse cached backtest results
        try:
            backtest_results = json.loads(cached_backtest)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse cached backtest results: {e}")
            return StrategyPerformanceResponse(
                success=False,
                strategy_id=strategy_id,
                metrics=None,
                risk_level=None,
                message="Invalid backtest data. Please run a new backtest."
            )
        
        # Extract lightweight metrics
        metrics = extract_lightweight_metrics(backtest_results)
        
        # Calculate risk level
        risk_level = calculate_risk_level(backtest_results)
        
        return StrategyPerformanceResponse(
            success=True,
            strategy_id=strategy_id,
            metrics=metrics,
            risk_level=risk_level,
            message=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy performance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

