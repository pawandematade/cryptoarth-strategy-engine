"""
PromptBuilder: Converts structured runtime payload into a single prompt string.
All trading rules must exist ONLY inside the generated prompt.
No database or storage - runtime only.
"""
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


def build_prompt(
    strategy_description: str,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    chart_type: Optional[str] = None,
    take_profit: Optional[Dict[str, Any]] = None,
    stop_loss: Optional[Dict[str, Any]] = None,
    trailing_stop: Optional[Dict[str, Any]] = None,
    trading_session: Optional[str] = None,
    max_trades_per_day: Optional[int] = None,
    current_price: Optional[float] = None,
    market_context: Optional[str] = None
) -> str:
    """
    Build a comprehensive prompt string from structured payload.
    
    All trading parameters are embedded into a single prompt string.
    This prompt is the ONLY thing sent to OpenAI.
    
    Args:
        strategy_description: Core strategy description from user
        symbol: Trading symbol (e.g., BTCUSD)
        timeframe: Trading timeframe (e.g., 15MIN, 1H, 1D)
        chart_type: Chart type (candles or heikin_ashi)
        take_profit: TP settings {type: 'percent'|'point', value: number}
        stop_loss: SL settings {type: 'percent'|'point', value: number}
        trailing_stop: Trailing stop settings {enabled: bool, type: 'percent'|'point', value: number}
        trading_session: Trading session (e.g., 'asian', 'european', 'american', 'all')
        max_trades_per_day: Maximum trades per day
        current_price: Current market price (optional context)
        market_context: Additional market context (optional)
    
    Returns:
        str: Complete prompt string with all parameters embedded
    """
    prompt_parts = []
    
    # Core strategy description (required)
    if strategy_description and strategy_description.strip():
        prompt_parts.append(strategy_description.strip())
    else:
        raise ValueError("Strategy description is required")
    
    # Add symbol
    if symbol:
        symbol_upper = symbol.strip().upper()
        prompt_parts.append(f"Symbol: {symbol_upper}")
    
    # Add timeframe
    if timeframe:
        prompt_parts.append(f"Timeframe: {timeframe}")
    
    # Add chart type
    if chart_type:
        chart_type_name = "Heikin Ashi" if chart_type == "heikin_ashi" else "Candles"
        prompt_parts.append(f"Chart Type: {chart_type_name}")
    
    # Add take profit
    if take_profit and take_profit.get('value'):
        tp_type = take_profit.get('type', 'percent')
        tp_value = take_profit.get('value')
        if tp_type == 'percent':
            prompt_parts.append(f"Take Profit: {tp_value}%")
        else:
            prompt_parts.append(f"Take Profit: {tp_value} points")
    
    # Add stop loss
    if stop_loss and stop_loss.get('value'):
        sl_type = stop_loss.get('type', 'percent')
        sl_value = stop_loss.get('value')
        if sl_type == 'percent':
            prompt_parts.append(f"Stop Loss: {sl_value}%")
        else:
            prompt_parts.append(f"Stop Loss: {sl_value} points")
    
    # Add trailing stop
    if trailing_stop and trailing_stop.get('enabled') and trailing_stop.get('value'):
        tr_type = trailing_stop.get('type', 'percent')
        tr_value = trailing_stop.get('value')
        if tr_type == 'percent':
            prompt_parts.append(f"Trailing Stop: {tr_value}%")
        else:
            prompt_parts.append(f"Trailing Stop: {tr_value} points")
    
    # Add trading session
    if trading_session and str(trading_session).strip():
        session_name = str(trading_session).strip().capitalize() if str(trading_session).strip().lower() != 'all' else 'All Sessions'
        prompt_parts.append(f"Trading Session: {session_name}")
    
    # Add max trades per day
    if max_trades_per_day and max_trades_per_day > 0:
        prompt_parts.append(f"Maximum Trades Per Day: {max_trades_per_day}")
    
    # Add current price context (if provided)
    if current_price:
        symbol_display = symbol.strip().upper() if symbol else "the asset"
        prompt_parts.append(f"Current {symbol_display} price: ${current_price:,.2f}")
    
    # Add market context (if provided)
    if market_context:
        prompt_parts.append(f"Market Context: {market_context}")
    
    # Join all parts into a single prompt string
    final_prompt = ". ".join(prompt_parts) + "."
    
    # Do not log the final prompt (as per requirements)
    logger.info("✅ Prompt built successfully (all parameters merged)")
    
    return final_prompt
