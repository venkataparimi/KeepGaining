"""
Utility to resample 1-minute candles to higher timeframes
"""
import pandas as pd
from typing import Literal

TimeframeType = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

class CandleResampler:
    """Resample 1-minute candles to any timeframe"""
    
    TIMEFRAME_MAP = {
        "1m": "1T",
        "5m": "5T",
        "15m": "15T",
        "30m": "30T",
        "1h": "1H",
        "2h": "2H",
        "4h": "4H",
        "1d": "1D",
    }
    
    @staticmethod
    def resample(df: pd.DataFrame, target_timeframe: TimeframeType) -> pd.DataFrame:
        """
        Resample 1-minute candles to target timeframe
        
        Args:
            df: DataFrame with 1-minute candles (must have timestamp index or column)
            target_timeframe: Target timeframe (5m, 15m, 1h, etc.)
            
        Returns:
            Resampled DataFrame with OHLCV data
        """
        if target_timeframe == "1m":
            return df  # Already 1-minute
        
        # Ensure timestamp is index
        if 'timestamp' in df.columns:
            df = df.set_index('timestamp')
        
        # Get pandas resample rule
        rule = CandleResampler.TIMEFRAME_MAP.get(target_timeframe)
        if not rule:
            raise ValueError(f"Unsupported timeframe: {target_timeframe}")
        
        # Resample OHLCV
        resampled = df.resample(rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
        })
        
        # Remove rows with no data
        resampled = resampled.dropna()
        
        # Reset index to have timestamp as column
        resampled = resampled.reset_index()
        
        return resampled
    
    @staticmethod
    def resample_with_indicators(
        df: pd.DataFrame, 
        target_timeframe: TimeframeType,
        indicator_service
    ) -> pd.DataFrame:
        """
        Resample and recompute all indicators
        
        Args:
            df: DataFrame with 1-minute candles
            target_timeframe: Target timeframe
            indicator_service: IndicatorComputationService instance
            
        Returns:
            Resampled DataFrame with all indicators
        """
        # Resample OHLCV
        resampled = CandleResampler.resample(df, target_timeframe)
        
        # Recompute indicators on resampled data
        with_indicators = indicator_service.compute_all_indicators(resampled)
        
        return with_indicators


# Example usage
"""
# Load 1-minute data
df_1m = await indicator_service.get_candles_with_indicators(
    symbol="NSE:NIFTY50-INDEX",
    timeframe="1m",
    start_date=datetime(2024, 1, 1)
)

# Resample to 5-minute
df_5m = CandleResampler.resample(df_1m, "5m")

# Resample to 5-minute with indicators
df_5m_indicators = CandleResampler.resample_with_indicators(
    df_1m, "5m", indicator_service
)

# Resample to hourly
df_1h = CandleResampler.resample(df_1m, "1h")
"""
