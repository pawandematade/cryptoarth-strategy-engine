"""
Backtest Engine - Strategy Execution Loop

Uses StrategyRunner to execute strategies on historical candles.
Tracks trades and computes performance metrics.

Pure deterministic execution - no side effects.
"""

import pandas as pd
from typing import Dict, List, Optional, Any
from engine.core.engine.strategy_runner import StrategyRunner


class BacktestEngine:
    """
    Backtest engine for strategy execution on historical data.
    
    Uses StrategyRunner internally - does not modify it.
    Stateless and deterministic.
    """
    
    def __init__(self, strategy: Dict[str, Any]):
        """
        Initialize BacktestEngine with strategy JSON.
        
        Args:
            strategy: Strategy JSON (single source of truth)
        """
        # Initialize StrategyRunner (immutable - we don't modify it)
        self.runner = StrategyRunner(strategy)
        self.strategy = strategy
    
    def _check_exit_conditions(
        self, 
        candles: pd.DataFrame, 
        trade: Dict[str, Any], 
        current_index: int
    ) -> Optional[Dict[str, Any]]:
        """
        Check if trade should exit (TP or SL hit).
        
        Args:
            candles: Full candles DataFrame
            trade: Current open trade dict
            current_index: Current candle index to check
        
        Returns:
            Exit dict with exit_price, exit_index, reason, or None if no exit
        """
        if current_index >= len(candles):
            return None
        
        direction = trade['direction']
        entry_price = trade['entry_price']
        stop_loss = trade['stop_loss']
        take_profit = trade['take_profit']
        
        # Get current candle OHLC
        candle_high = candles['high'].iloc[current_index]
        candle_low = candles['low'].iloc[current_index]
        candle_close = candles['close'].iloc[current_index]
        
        if direction == 'BUY':
            # BUY trade: exit on TP (high crosses above) or SL (low crosses below)
            # SL has priority if both hit in same candle
            
            # Check SL first (has priority)
            if candle_low <= stop_loss:
                return {
                    'exit_price': float(stop_loss),
                    'exit_index': current_index,
                    'reason': 'stop_loss',
                    'result': 'LOSS'
                }
            
            # Check TP
            if candle_high >= take_profit:
                return {
                    'exit_price': float(take_profit),
                    'exit_index': current_index,
                    'reason': 'take_profit',
                    'result': 'WIN'
                }
        
        elif direction == 'SELL':
            # SELL trade: exit on TP (low crosses below) or SL (high crosses above)
            # SL has priority if both hit in same candle
            
            # Check SL first (has priority)
            if candle_high >= stop_loss:
                return {
                    'exit_price': float(stop_loss),
                    'exit_index': current_index,
                    'reason': 'stop_loss',
                    'result': 'LOSS'
                }
            
            # Check TP
            if candle_low <= take_profit:
                return {
                    'exit_price': float(take_profit),
                    'exit_index': current_index,
                    'reason': 'take_profit',
                    'result': 'WIN'
                }
        
        return None
    
    def _calculate_trade_pnl(self, trade: Dict[str, Any]) -> float:
        """
        Calculate PnL for a closed trade.
        
        Args:
            trade: Trade dict with direction, entry_price, exit_price
        
        Returns:
            PnL value (positive for profit, negative for loss)
        """
        direction = trade['direction']
        entry_price = trade['entry_price']
        exit_price = trade['exit_price']
        
        if direction == 'BUY':
            # BUY: profit when exit > entry
            pnl = exit_price - entry_price
        else:  # SELL
            # SELL: profit when exit < entry
            pnl = entry_price - exit_price
        
        return float(pnl)
    
    def _compute_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compute performance metrics from trades.
        
        Args:
            trades: List of closed trade records
        
        Returns:
            Metrics dict
        """
        if not trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'net_pnl': 0.0,
                'max_drawdown': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0
            }
        
        # Basic counts
        total_trades = len(trades)
        wins = sum(1 for t in trades if t['result'] == 'WIN')
        losses = total_trades - wins
        win_rate = wins / total_trades if total_trades > 0 else 0.0
        
        # PnL calculations
        net_pnl = sum(t['pnl'] for t in trades)
        
        # Win/Loss averages
        winning_trades = [t for t in trades if t['result'] == 'WIN']
        losing_trades = [t for t in trades if t['result'] == 'LOSS']
        
        avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
        avg_loss = abs(sum(t['pnl'] for t in losing_trades) / len(losing_trades)) if losing_trades else 0.0
        
        # Profit factor
        total_profit = sum(t['pnl'] for t in winning_trades) if winning_trades else 0.0
        total_loss = abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else 0.0
        profit_factor = total_profit / total_loss if total_loss > 0 else (total_profit if total_profit > 0 else 0.0)
        
        # Max drawdown calculation
        cumulative_pnl = 0.0
        peak = 0.0
        max_drawdown = 0.0
        
        for trade in trades:
            cumulative_pnl += trade['pnl']
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            drawdown = peak - cumulative_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 4),
            'net_pnl': round(net_pnl, 2),
            'max_drawdown': round(max_drawdown, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 4)
        }
    
    def run(self, candles: pd.DataFrame) -> Dict[str, Any]:
        """
        Run backtest on historical candles.
        
        Args:
            candles: DataFrame with OHLCV data, sorted by time ascending.
                    Must have columns: 'open', 'high', 'low', 'close', 'volume'
        
        Returns:
            Backtest results dict:
            {
                "summary": {
                    "total_trades": int,
                    "wins": int,
                    "losses": int,
                    "win_rate": float,
                    "net_pnl": float,
                    "max_drawdown": float,
                    "profit_factor": float
                },
                "trades": [
                    {
                        "direction": "BUY" | "SELL",
                        "entry_price": float,
                        "exit_price": float,
                        "entry_index": int,
                        "exit_index": int,
                        "pnl": float,
                        "result": "WIN" | "LOSS",
                        "entry_reason": str,  # From StrategyRunner signal
                        "exit_reason": str    # "stop_loss" | "take_profit" | "end_of_data"
                    },
                    ...
                ]
            }
        """
        # Validate DataFrame
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in candles.columns]
        if missing_columns:
            raise ValueError(f"DataFrame missing required columns: {missing_columns}")
        
        if len(candles) == 0:
            return {
                'summary': {
                    'total_trades': 0,
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0.0,
                    'net_pnl': 0.0,
                    'max_drawdown': 0.0,
                    'profit_factor': 0.0
                },
                'trades': []
            }
        
        # Track trades
        trades = []
        current_trade = None
        last_exit_candle_index = -1  # Track last exit candle (prevent re-entry on same candle as exit)
        
        # Minimum required index for StrategyRunner
        min_required_index = max(self.runner.ema_periods)
        
        # Iterate through candles sequentially
        for i in range(min_required_index, len(candles)):
            # If we have an open trade, check exit conditions first
            if current_trade is not None:
                exit_info = self._check_exit_conditions(candles, current_trade, i)
                
                if exit_info is not None:
                    # Close trade
                    exit_candle_index = exit_info['exit_index']
                    current_trade['exit_price'] = exit_info['exit_price']
                    current_trade['exit_index'] = exit_candle_index
                    current_trade['result'] = exit_info['result']
                    current_trade['exit_reason'] = exit_info['reason']  # Preserve exit reason
                    # Keep entry_reason (from signal) - don't overwrite
                    if 'entry_reason' not in current_trade:
                        current_trade['entry_reason'] = current_trade.get('signal_reason', '')
                    current_trade['pnl'] = self._calculate_trade_pnl(current_trade)
                    
                    trades.append(current_trade.copy())
                    # CRITICAL FIX: Reset position state after trade exit
                    current_trade = None
                    last_exit_candle_index = exit_candle_index  # Track exit candle (prevent re-entry on same candle)
                    
                    # Continue to next candle (don't check for new signals on exit candle)
                    continue
            
            # No open trade - check for new signal
            # EXIT CANDLE RE-ENTRY PROTECTION: Don't allow entry on same candle as exit
            if i <= last_exit_candle_index:
                continue
            
            # CRITICAL ARCHITECTURAL FIX: Use incremental on_candle() method
            # This evaluates ONLY the current candle index, not full history
            # This supports multiple trades, grid strategies, and live/backtest parity
            # Contract: StrategyRunner.on_candle() is a PURE evaluator - it returns signal
            # if conditions are met at THIS candle, None otherwise.
            # BacktestEngine only blocks entries when: (1) trade is open, (2) on exit candle
            candle_slice = candles.iloc[:i + 1].copy()
            signal = self.runner.on_candle(candle_slice, i)
            
            if signal is not None:
                # Signal detected at current candle index by StrategyRunner
                # In incremental mode, we trust StrategyRunner's evaluation
                # Only blocking: no pyramiding (current_trade must be None)
                # This is already guaranteed by the outer if condition
                signal_index = signal['index']
                current_trade = {
                    'direction': signal['signal'],  # Strictly "BUY" or "SELL"
                    'entry_price': signal['entry_price'],
                    'stop_loss': signal['stop_loss'],
                    'take_profit': signal['take_profit'],
                    'entry_index': signal_index,
                    'entry_reason': signal.get('reason', '')  # Preserve entry reason
                }
        
        # Close any remaining open trade at end of candles
        if current_trade is not None:
            # Use last candle close as exit
            last_index = len(candles) - 1
            last_close = candles['close'].iloc[last_index]
            
            current_trade['exit_price'] = float(last_close)
            current_trade['exit_index'] = last_index
            current_trade['result'] = 'WIN' if self._calculate_trade_pnl(current_trade) > 0 else 'LOSS'
            current_trade['exit_reason'] = 'end_of_data'  # Preserve exit reason
            # Keep entry_reason (from signal) - don't overwrite
            if 'entry_reason' not in current_trade:
                current_trade['entry_reason'] = current_trade.get('signal_reason', '')
            current_trade['pnl'] = self._calculate_trade_pnl(current_trade)
            
            trades.append(current_trade)
        
        # Compute metrics
        summary = self._compute_metrics(trades)
        
        return {
            'summary': summary,
            'trades': trades
        }
