"""
Strategy Runner - Core Execution Engine

Pure deterministic strategy execution engine.
Works with FINAL, CLEAN, EXECUTION-READY strategy JSON.
No AI, no prompts, no UI data.

Supports:
- Backtesting
- Live trading
- Performance calculation

Usage:
    import pandas as pd
    from engine.core.engine.strategy_runner import StrategyRunner
    
    # Strategy JSON (single source of truth)
    strategy = {
        "symbol": "BTCUSD",
        "strategy_type": "ema_crossover",
        "logic": {
            "emas": [10, 20, 50, 100, 200],
            "entry": {
                "buy": {
                    "crossover": "ema_10_above_all",
                    "confirmation": {
                        "type": "candle_high_break",
                        "reference": "second_candle",
                        "max_wait_candles": 3
                    }
                },
                "sell": {
                    "crossover": "ema_10_below_all",
                    "confirmation": {
                        "type": "candle_low_break",
                        "reference": "second_candle",
                        "max_wait_candles": 3
                    }
                }
            }
        },
        "risk": {
            "take_profit_points": 4000,
            "stop_loss_points": 4000
        },
        "meta": {
            "timeframe": "30MIN",
            "chart_type": "candles"
        }
    }
    
    # OHLCV candles (pandas DataFrame, sorted by time ascending)
    candles = pd.DataFrame({
        'open': [...],
        'high': [...],
        'low': [...],
        'close': [...],
        'volume': [...]
    })
    
    # Run strategy
    runner = StrategyRunner(strategy)
    signal = runner.run(candles)
    
    # Signal format (or None if no signal):
    # {
    #     "signal": "BUY" | "SELL",
    #     "entry_price": float,
    #     "stop_loss": float,
    #     "take_profit": float,
    #     "index": int,  # Candle index where signal was confirmed
    #     "reason": str  # Optional: debug info (e.g., "ema_10_above_all + candle_high_break")
    # }
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Any, List


class StrategyRunner:
    """
    Pure execution engine for trading strategies.
    
    Takes strategy JSON and OHLCV candles, returns signals.
    No side effects - deterministic execution only.
    """
    
    def __init__(self, strategy: Dict[str, Any]):
        """
        Initialize StrategyRunner with strategy JSON.
        
        Args:
            strategy: Strategy JSON with structure:
                {
                    "symbol": str,
                    "strategy_type": str,
                    "logic": {
                        "emas": [int, ...],
                        "entry": {
                            "buy": {...},
                            "sell": {...}
                        }
                    },
                    "risk": {
                        "take_profit_points": float,
                        "stop_loss_points": float
                    },
                    "meta": {...}
                }
        """
        self.strategy = strategy
        self.logic = strategy.get('logic', {})
        self.risk = strategy.get('risk', {})
        self.meta = strategy.get('meta', {})
        
        # Extract EMA periods from strategy JSON
        self.ema_periods = self.logic.get('emas', [])
        if not self.ema_periods:
            raise ValueError("Strategy must contain logic.emas array with at least one EMA period")
        
        # Primary EMA is the first one (typically 10)
        self.primary_ema = self.ema_periods[0]
        self.other_emas = self.ema_periods[1:] if len(self.ema_periods) > 1 else []
        
        if not self.other_emas:
            raise ValueError("Strategy must contain at least 2 EMAs for crossover detection")
        
        # Extract entry conditions
        self.entry = self.logic.get('entry', {})
        self.buy_entry = self.entry.get('buy', {})
        self.sell_entry = self.entry.get('sell', {})
        
        # Extract risk parameters (points only, not percent)
        self.take_profit_points = self.risk.get('take_profit_points')
        self.stop_loss_points = self.risk.get('stop_loss_points')
        
        if self.take_profit_points is None or self.stop_loss_points is None:
            raise ValueError("Strategy must contain take_profit_points and stop_loss_points in risk section")
    
    def calculate_emas(self, df: pd.DataFrame) -> Dict[int, pd.Series]:
        """
        Calculate all EMAs from strategy JSON.
        
        Args:
            df: DataFrame with 'close' column (OHLCV data)
        
        Returns:
            Dict mapping EMA period -> Series of EMA values
        """
        if 'close' not in df.columns:
            raise ValueError("DataFrame must contain 'close' column")
        
        emas = {}
        close_prices = df['close']
        
        for period in self.ema_periods:
            # Use pandas ewm for EMA calculation
            ema = close_prices.ewm(span=period, adjust=False).mean()
            emas[period] = ema
        
        return emas
    
    def check_crossover_above(self, emas: Dict[int, pd.Series], index: int) -> bool:
        """
        Check if primary EMA crossed above all other EMAs.
        
        Args:
            emas: Dict of EMA period -> Series
            index: Current candle index (must be >= 1)
        
        Returns:
            True if crossover detected on this candle
        """
        if index < 1:
            return False
        
        # Get primary EMA values
        primary_ema_series = emas[self.primary_ema]
        primary_curr = primary_ema_series.iloc[index]
        primary_prev = primary_ema_series.iloc[index - 1]
        
        if pd.isna(primary_curr) or pd.isna(primary_prev):
            return False
        
        # Check if primary EMA crossed above ALL other EMAs
        for other_period in self.other_emas:
            other_ema_series = emas[other_period]
            other_curr = other_ema_series.iloc[index]
            other_prev = other_ema_series.iloc[index - 1]
            
            if pd.isna(other_curr) or pd.isna(other_prev):
                return False
            
            # Crossover: previous was below or equal, now is above
            if not (primary_prev <= other_prev and primary_curr > other_curr):
                return False
        
        return True
    
    def check_crossover_below(self, emas: Dict[int, pd.Series], index: int) -> bool:
        """
        Check if primary EMA crossed below all other EMAs.
        
        Args:
            emas: Dict of EMA period -> Series
            index: Current candle index (must be >= 1)
        
        Returns:
            True if crossover detected on this candle
        """
        if index < 1:
            return False
        
        # Get primary EMA values
        primary_ema_series = emas[self.primary_ema]
        primary_curr = primary_ema_series.iloc[index]
        primary_prev = primary_ema_series.iloc[index - 1]
        
        if pd.isna(primary_curr) or pd.isna(primary_prev):
            return False
        
        # Check if primary EMA crossed below ALL other EMAs
        for other_period in self.other_emas:
            other_ema_series = emas[other_period]
            other_curr = other_ema_series.iloc[index]
            other_prev = other_ema_series.iloc[index - 1]
            
            if pd.isna(other_curr) or pd.isna(other_prev):
                return False
            
            # Crossover: previous was above or equal, now is below
            if not (primary_prev >= other_prev and primary_curr < other_curr):
                return False
        
        return True
    
    def check_candle_break_confirmation(
        self, 
        df: pd.DataFrame, 
        crossover_index: int, 
        signal_type: str,
        confirmation: Dict[str, Any]
    ) -> Optional[int]:
        """
        Check candle break confirmation after crossover.
        
        Args:
            df: DataFrame with OHLCV data
            crossover_index: Index where crossover occurred
            signal_type: 'BUY' or 'SELL'
            confirmation: Confirmation config from strategy JSON
        
        Returns:
            Confirmed candle index, or None if not confirmed within max_wait_candles
        """
        confirmation_type = confirmation.get('type')
        reference = confirmation.get('reference', 'second_candle')
        max_wait_candles = confirmation.get('max_wait_candles', 3)
        
        # Determine reference candle index
        if reference == 'second_candle':
            start_index = crossover_index + 1
        elif reference == 'first_candle':
            start_index = crossover_index
        else:
            # Default to second candle
            start_index = crossover_index + 1
        
        # Check up to max_wait_candles after reference
        end_index = min(start_index + max_wait_candles, len(df))
        
        if start_index >= len(df):
            return None
        
        # Check candle break based on signal type
        if signal_type == 'BUY':
            # For BUY: check if candle HIGH breaks above crossover close
            if 'high' not in df.columns:
                return None
            
            crossover_close = df['close'].iloc[crossover_index]
            
            for i in range(start_index, end_index):
                candle_high = df['high'].iloc[i]
                if candle_high > crossover_close:
                    # Confirmation: candle HIGH broke above crossover close
                    return i
        
        elif signal_type == 'SELL':
            # For SELL: check if candle LOW breaks below crossover close
            if 'low' not in df.columns:
                return None
            
            crossover_close = df['close'].iloc[crossover_index]
            
            for i in range(start_index, end_index):
                candle_low = df['low'].iloc[i]
                if candle_low < crossover_close:
                    # Confirmation: candle LOW broke below crossover close
                    return i
        
        return None
    
    def _generate_reason(self, signal_type: str, confirmation: Dict[str, Any]) -> str:
        """
        Generate reason string for signal (debug/analysis only).
        
        Args:
            signal_type: 'BUY' or 'SELL'
            confirmation: Confirmation config from strategy JSON
        
        Returns:
            Reason string (e.g., "ema_10_above_all + candle_high_break")
        """
        # Primary EMA identifier
        primary_ema_name = f"ema_{self.primary_ema}"
        
        # Crossover type
        if signal_type == 'BUY':
            crossover_desc = f"{primary_ema_name}_above_all"
        else:  # SELL
            crossover_desc = f"{primary_ema_name}_below_all"
        
        # Confirmation type
        confirmation_type = confirmation.get('type', '')
        if confirmation_type == 'candle_high_break':
            confirmation_desc = "candle_high_break"
        elif confirmation_type == 'candle_low_break':
            confirmation_desc = "candle_low_break"
        else:
            confirmation_desc = confirmation_type or "confirmed"
        
        return f"{crossover_desc} + {confirmation_desc}"
    
    def calculate_risk_levels(self, entry_price: float, signal_type: str) -> Dict[str, float]:
        """
        Calculate stop loss and take profit levels.
        
        Args:
            entry_price: Entry price
            signal_type: 'BUY' or 'SELL'
        
        Returns:
            Dict with 'stop_loss' and 'take_profit'
        """
        if signal_type == 'BUY':
            stop_loss = entry_price - self.stop_loss_points
            take_profit = entry_price + self.take_profit_points
        elif signal_type == 'SELL':
            stop_loss = entry_price + self.stop_loss_points
            take_profit = entry_price - self.take_profit_points
        else:
            raise ValueError(f"Invalid signal_type: {signal_type}")
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    def on_candle(self, candles: pd.DataFrame, index: int) -> Optional[Dict[str, Any]]:
        """
        Evaluate strategy at a specific candle index (incremental mode).
        
        This is the CORRECT method for backtest and live trading.
        It evaluates ONLY the given candle index, not the full history.
        
        Args:
            candles: DataFrame with OHLCV data up to and including the index to evaluate.
                    Must have columns: 'open', 'high', 'low', 'close', 'volume'
            index: Specific candle index to evaluate (0-based)
        
        Returns:
            Signal dict if conditions met at this index, None otherwise:
            {
                "signal": "BUY" | "SELL",
                "entry_price": float,
                "stop_loss": float,
                "take_profit": float,
                "index": int,
                "reason": str
            }
        """
        # Validate DataFrame
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in candles.columns]
        if missing_columns:
            raise ValueError(f"DataFrame missing required columns: {missing_columns}")
        
        # Validate index
        if index < 0 or index >= len(candles):
            return None
        
        # Need enough candles for EMA calculation
        min_required_index = max(self.ema_periods)
        if index < min_required_index:
            return None
        
        # Calculate EMAs (immutable - creates new Series, doesn't modify candles)
        emas = self.calculate_emas(candles)
        
        # Evaluate ONLY the given index for signal conditions
        # Check for BUY signal first (has priority)
        if self.check_crossover_above(emas, index):
            # Crossover detected at this index, check confirmation
            confirmation = self.buy_entry.get('confirmation', {})
            confirmed_index = self.check_candle_break_confirmation(
                candles, index, 'BUY', confirmation
            )
            
            if confirmed_index is not None:
                # Signal confirmed - return signal for this specific index
                entry_price = candles['close'].iloc[confirmed_index]
                risk_levels = self.calculate_risk_levels(entry_price, 'BUY')
                reason = self._generate_reason('BUY', confirmation)
                
                return {
                    "signal": "BUY",
                    "entry_price": float(entry_price),
                    "stop_loss": float(risk_levels['stop_loss']),
                    "take_profit": float(risk_levels['take_profit']),
                    "index": int(confirmed_index),
                    "reason": reason
                }
        
        # Check for SELL signal (only if BUY didn't match/confirm)
        if self.check_crossover_below(emas, index):
            # Crossover detected at this index, check confirmation
            confirmation = self.sell_entry.get('confirmation', {})
            confirmed_index = self.check_candle_break_confirmation(
                candles, index, 'SELL', confirmation
            )
            
            if confirmed_index is not None:
                # Signal confirmed
                entry_price = candles['close'].iloc[confirmed_index]
                risk_levels = self.calculate_risk_levels(entry_price, 'SELL')
                reason = self._generate_reason('SELL', confirmation)
                
                return {
                    "signal": "SELL",
                    "entry_price": float(entry_price),
                    "stop_loss": float(risk_levels['stop_loss']),
                    "take_profit": float(risk_levels['take_profit']),
                    "index": int(confirmed_index),
                    "reason": reason
                }
        
        # No signal at this index
        return None
    
    def run(self, candles: pd.DataFrame, min_signal_index: int = -1) -> Optional[Dict[str, Any]]:
        """
        Run strategy on candles and return signal if conditions met.
        
        Args:
            candles: DataFrame with OHLCV data, sorted by time ascending.
                    Must have columns: 'open', 'high', 'low', 'close', 'volume'
            min_signal_index: Only return signals with index > min_signal_index.
                             Use -1 to return first signal found (default behavior).
                             Used by BacktestEngine to find new signals after trade exits.
        
        Returns:
            Signal dict or None:
            {
                "signal": "BUY" | "SELL",
                "entry_price": float,
                "stop_loss": float,
                "take_profit": float,
                "index": int,
                "reason": str  # Optional: debug info for analysis
            }
        """
        # Validate DataFrame
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in candles.columns]
        if missing_columns:
            raise ValueError(f"DataFrame missing required columns: {missing_columns}")
        
        if len(candles) < max(self.ema_periods) + 3:
            # Not enough data for EMA calculation and confirmation
            return None
        
        # Calculate EMAs (immutable - creates new Series, doesn't modify candles)
        emas = self.calculate_emas(candles)
        
        # Check each candle for signals (start from index where all EMAs are valid)
        min_required_index = max(self.ema_periods)
        # CRITICAL FIX: Start scanning from after min_signal_index to find NEW signals
        start_index = max(min_required_index, min_signal_index + 1)
        
        for i in range(start_index, len(candles)):
            # CRITICAL: Only ONE signal per candle index
            # BUY has priority if both conditions match on same crossover candle
            # Check BUY first, return immediately if confirmed (prevents double signal)
            
            # Check for BUY signal
            if self.check_crossover_above(emas, i):
                # Crossover detected, check confirmation
                confirmation = self.buy_entry.get('confirmation', {})
                confirmed_index = self.check_candle_break_confirmation(
                    candles, i, 'BUY', confirmation
                )
                
                if confirmed_index is not None:
                    # Signal confirmed - return immediately (BUY has priority)
                    entry_price = candles['close'].iloc[confirmed_index]
                    risk_levels = self.calculate_risk_levels(entry_price, 'BUY')
                    reason = self._generate_reason('BUY', confirmation)
                    
                    return {
                        "signal": "BUY",
                        "entry_price": float(entry_price),
                        "stop_loss": float(risk_levels['stop_loss']),
                        "take_profit": float(risk_levels['take_profit']),
                        "index": int(confirmed_index),
                        "reason": reason
                    }
            
            # Check for SELL signal (only if BUY didn't match/confirm)
            # This ensures only ONE signal can be returned per candle iteration
            if self.check_crossover_below(emas, i):
                # Crossover detected, check confirmation
                confirmation = self.sell_entry.get('confirmation', {})
                confirmed_index = self.check_candle_break_confirmation(
                    candles, i, 'SELL', confirmation
                )
                
                if confirmed_index is not None:
                    # Signal confirmed
                    entry_price = candles['close'].iloc[confirmed_index]
                    risk_levels = self.calculate_risk_levels(entry_price, 'SELL')
                    reason = self._generate_reason('SELL', confirmation)
                    
                    return {
                        "signal": "SELL",
                        "entry_price": float(entry_price),
                        "stop_loss": float(risk_levels['stop_loss']),
                        "take_profit": float(risk_levels['take_profit']),
                        "index": int(confirmed_index),
                        "reason": reason
                    }
        
        # No signal found
        return None
