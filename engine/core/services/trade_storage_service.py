"""
Trade Storage Service
Saves individual trades to strategy_trades table for reporting.
"""
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from engine.models import StrategyTrade
from common.db import get_db
import logging

logger = logging.getLogger(__name__)


def calculate_brokerage(
    entry_price: float,
    exit_price: float,
    quantity: float,
    maker_rate: float,
    taker_rate: float,
    brokerage_type: str = "maker"
) -> float:
    """
    Calculate brokerage for a trade.
    
    Args:
        entry_price: Trade entry price
        exit_price: Trade exit price
        quantity: Trade quantity
        maker_rate: Maker brokerage rate (e.g., 0.0002 for 0.02%)
        taker_rate: Taker brokerage rate (e.g., 0.0005 for 0.05%)
        brokerage_type: "maker" or "taker"
    
    Returns:
        Total brokerage amount
    """
    rate = maker_rate if brokerage_type == "maker" else taker_rate
    
    # Brokerage on entry: capital_used * rate
    # Brokerage on exit: quantity * exit_price * rate
    entry_brokerage = entry_price * quantity * rate
    exit_brokerage = exit_price * quantity * rate
    total_brokerage = entry_brokerage + exit_brokerage
    
    return float(total_brokerage)


def save_trade(
    db: Session,
    strategy_id: int,
    user_phone: str,
    user_name: str,
    symbol: str,
    timeframe: str,
    direction: str,
    entry_time: datetime,
    exit_time: datetime,
    entry_price: float,
    exit_price: float,
    quantity: float,
    capital_used: float,
    brokerage_mode: str,
    brokerage_type: str,
    maker_rate: float,
    taker_rate: float,
    max_drawdown_trade: float = 0.0
) -> Optional[StrategyTrade]:
    """
    Save a trade to strategy_trades table.
    
    Args:
        db: Database session
        strategy_id: Strategy ID
        user_phone: User phone number
        user_name: User name
        symbol: Trading symbol (e.g., "BTCUSD")
        timeframe: Timeframe (e.g., "5m")
        direction: "BUY" or "SELL"
        entry_time: Trade entry timestamp
        exit_time: Trade exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        quantity: Trade quantity
        capital_used: Capital used for this trade
        brokerage_mode: "default" or "custom"
        brokerage_type: "maker" or "taker"
        maker_rate: Maker rate (e.g., 0.0002)
        taker_rate: Taker rate (e.g., 0.0005)
        max_drawdown_trade: Max drawdown for this trade (default 0.0)
    
    Returns:
        StrategyTrade model instance or None if save failed
    """
    try:
        # Calculate gross PnL
        if direction == "BUY":
            gross_pnl = (exit_price - entry_price) * quantity
        else:  # SELL
            gross_pnl = (entry_price - exit_price) * quantity
        
        # Calculate brokerage
        brokerage = calculate_brokerage(
            entry_price,
            exit_price,
            quantity,
            maker_rate,
            taker_rate,
            brokerage_type
        )
        
        # Calculate net PnL
        net_pnl = gross_pnl - brokerage
        
        # Determine if win
        is_win = net_pnl > 0
        
        # Calculate PnL percent
        pnl_percent = (net_pnl / capital_used * 100) if capital_used > 0 else 0.0
        
        # Create trade record
        trade = StrategyTrade(
            strategy_id=strategy_id,
            user_phone=user_phone,
            user_name=user_name,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=Decimal(str(entry_price)),
            exit_price=Decimal(str(exit_price)),
            quantity=Decimal(str(quantity)),
            capital_used=Decimal(str(capital_used)),
            gross_pnl=Decimal(str(gross_pnl)),
            brokerage=Decimal(str(brokerage)),
            net_pnl=Decimal(str(net_pnl)),
            pnl_percent=Decimal(str(pnl_percent)),
            is_win=is_win,
            max_drawdown_trade=Decimal(str(max_drawdown_trade)),
            brokerage_mode=brokerage_mode,
            maker_rate=Decimal(str(maker_rate)),
            taker_rate=Decimal(str(taker_rate))
        )
        
        db.add(trade)
        db.commit()
        db.refresh(trade)
        
        logger.info(f"Saved trade: strategy_id={strategy_id}, symbol={symbol}, direction={direction}, net_pnl={net_pnl}")
        return trade
        
    except Exception as e:
        logger.error(f"Error saving trade: {e}", exc_info=True)
        db.rollback()
        return None


def save_trades_from_backtest(
    db: Session,
    strategy_id: int,
    user_phone: str,
    user_name: str,
    symbol: str,
    timeframe: str,
    trades: list,
    backtest_settings: Dict[str, Any],
    candles_list: list
) -> int:
    """
    Save multiple trades from backtest results.
    
    Args:
        db: Database session
        strategy_id: Strategy ID
        user_phone: User phone number
        user_name: User name
        symbol: Trading symbol
        timeframe: Timeframe
        trades: List of trade dicts from backtest
        backtest_settings: Backtest settings dict with initialCapital, leverage, capitalPerTrade, brokerageMode, brokerageType, brokerage
        candles_list: List of candle dicts with 'time' field
    
    Returns:
        Number of trades saved successfully
    """
    if not trades:
        return 0
    
    # Extract backtest settings
    initial_capital = float(backtest_settings.get('initialCapital', 100000))
    leverage = float(backtest_settings.get('leverage', 1))
    capital_per_trade_pct = float(backtest_settings.get('capitalPerTrade', 10)) / 100.0
    brokerage_mode = backtest_settings.get('brokerageMode', 'default')
    brokerage_type = backtest_settings.get('brokerageType', 'maker')
    
    # Get brokerage rates
    if brokerage_mode == 'custom' and 'brokerage' in backtest_settings:
        custom_rate = float(backtest_settings['brokerage'].get('rate', 0.0002))
        maker_rate = custom_rate if brokerage_type == 'maker' else 0.0002
        taker_rate = custom_rate if brokerage_type == 'taker' else 0.0005
    else:
        maker_rate = 0.0002  # 0.02%
        taker_rate = 0.0005  # 0.05%
    
    capital_per_trade = initial_capital * capital_per_trade_pct
    
    # Create timestamp map from candles
    index_to_timestamp = {}
    for idx, candle in enumerate(candles_list):
        if idx < len(candles_list):
            index_to_timestamp[idx] = candle.get('time', 0)
    
    saved_count = 0
    
    for trade in trades:
        try:
            entry_index = trade.get('entry_index', 0)
            exit_index = trade.get('exit_index', 0)
            entry_price = float(trade.get('entry_price', 0))
            exit_price = float(trade.get('exit_price', 0))
            
            # Get timestamps
            entry_timestamp = index_to_timestamp.get(entry_index, 0)
            exit_timestamp = index_to_timestamp.get(exit_index, 0)
            
            if entry_timestamp == 0 or exit_timestamp == 0:
                logger.warning(f"Skipping trade with invalid timestamp: entry_index={entry_index}, exit_index={exit_index}")
                continue
            
            entry_time = datetime.fromtimestamp(entry_timestamp)
            exit_time = datetime.fromtimestamp(exit_timestamp)
            
            # Calculate position size
            leveraged_capital = capital_per_trade * leverage
            quantity = leveraged_capital / entry_price if entry_price > 0 else 0
            
            # Get max_drawdown_trade (if available)
            max_drawdown_trade = float(trade.get('max_drawdown_trade', 0.0))
            
            # Save trade
            saved_trade = save_trade(
                db=db,
                strategy_id=strategy_id,
                user_phone=user_phone,
                user_name=user_name,
                symbol=symbol,
                timeframe=timeframe,
                direction=trade.get('direction', 'BUY'),
                entry_time=entry_time,
                exit_time=exit_time,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                capital_used=capital_per_trade,
                brokerage_mode=brokerage_mode,
                brokerage_type=brokerage_type,
                maker_rate=maker_rate,
                taker_rate=taker_rate,
                max_drawdown_trade=max_drawdown_trade
            )
            
            if saved_trade:
                saved_count += 1
                
        except Exception as e:
            logger.error(f"Error saving trade from backtest: {e}", exc_info=True)
            continue
    
    logger.info(f"Saved {saved_count}/{len(trades)} trades from backtest: strategy_id={strategy_id}")
    return saved_count

