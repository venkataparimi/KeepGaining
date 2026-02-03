"""
Service for computing and storing indicators in database
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.candle_data import CandleData
from loguru import logger


class IndicatorComputationService:
    """Pre-compute and store all indicators for faster backtesting"""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    @staticmethod
    def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all standard indicators for a DataFrame of candles
        
        Args:
            df: DataFrame with columns: open, high, low, close, volume
            
        Returns:
            DataFrame with all indicators added
        """
        if len(df) < 200:
            logger.warning(f"Only {len(df)} candles - some indicators need 200+")
        
        # Moving Averages
        df['sma_9'] = df['close'].rolling(window=9).mean()
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['sma_200'] = df['close'].rolling(window=200).mean()
        
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # RSI
        df['rsi_14'] = IndicatorComputationService._compute_rsi(df['close'], 14)
        df['rsi_9'] = IndicatorComputationService._compute_rsi(df['close'], 9)
        
        # MACD
        macd_data = IndicatorComputationService._compute_macd(df['close'])
        df['macd'] = macd_data['macd']
        df['macd_signal'] = macd_data['signal']
        df['macd_histogram'] = macd_data['histogram']
        
        # Stochastic
        stoch = IndicatorComputationService._compute_stochastic(
            df['high'], df['low'], df['close']
        )
        df['stoch_k'] = stoch['k']
        df['stoch_d'] = stoch['d']
        
        # Bollinger Bands
        bb = IndicatorComputationService._compute_bollinger_bands(df['close'])
        df['bb_upper'] = bb['upper']
        df['bb_middle'] = bb['middle']
        df['bb_lower'] = bb['lower']
        
        # ATR
        df['atr_14'] = IndicatorComputationService._compute_atr(
            df['high'], df['low'], df['close'], 14
        )
        
        # SuperTrend
        supertrend = IndicatorComputationService._compute_supertrend(
            df['high'], df['low'], df['close']
        )
        df['supertrend'] = supertrend['supertrend']
        df['supertrend_direction'] = supertrend['direction']
        
        # ADX
        df['adx'] = IndicatorComputationService._compute_adx(
            df['high'], df['low'], df['close']
        )
        
        # VWAP (resets daily)
        df['vwap'] = IndicatorComputationService._compute_vwap(
            df['high'], df['low'], df['close'], df['volume'], df['timestamp']
        )
        
        # VWMA (Volume Weighted Moving Average) - Multiple periods
        df['vwma_20'] = IndicatorComputationService._compute_vwma(
            df['close'], df['volume'], 20
        )
        df['vwma_22'] = IndicatorComputationService._compute_vwma(
            df['close'], df['volume'], 22
        )
        df['vwma_31'] = IndicatorComputationService._compute_vwma(
            df['close'], df['volume'], 31
        )
        df['vwma_50'] = IndicatorComputationService._compute_vwma(
            df['close'], df['volume'], 50
        )
        
        # OBV
        df['obv'] = IndicatorComputationService._compute_obv(
            df['close'], df['volume']
        )
        
        # Pivot Points - All three types
        pivots = IndicatorComputationService._compute_all_pivots(df)
        df = pd.concat([df, pivots], axis=1)
        
        return df
    
    @staticmethod
    def _compute_rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def _compute_macd(data: pd.Series, fast=12, slow=26, signal=9):
        """MACD"""
        ema_fast = data.ewm(span=fast, adjust=False).mean()
        ema_slow = data.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    @staticmethod
    def _compute_stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                           k_period=14, d_period=3):
        """Stochastic Oscillator"""
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        k_line = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        d_line = k_line.rolling(window=d_period).mean()
        
        return {'k': k_line, 'd': d_line}
    
    @staticmethod
    def _compute_bollinger_bands(data: pd.Series, period=20, std_dev=2):
        """Bollinger Bands"""
        sma = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()
        
        return {
            'upper': sma + (std * std_dev),
            'middle': sma,
            'lower': sma - (std * std_dev)
        }
    
    @staticmethod
    def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14):
        """Average True Range"""
        high_low = high - low
        high_close = np.abs(high - close.shift())
        low_close = np.abs(low - close.shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        
        return true_range.rolling(window=period).mean()
    
    @staticmethod
    def _compute_supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                           period=10, multiplier=3):
        """SuperTrend"""
        atr = IndicatorComputationService._compute_atr(high, low, close, period)
        hl_avg = (high + low) / 2
        
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        supertrend = pd.Series(index=close.index, dtype=float)
        direction = pd.Series(index=close.index, dtype=int)
        
        supertrend.iloc[0] = lower_band.iloc[0]
        direction.iloc[0] = 1
        
        for i in range(1, len(close)):
            if pd.isna(upper_band.iloc[i]) or pd.isna(lower_band.iloc[i]):
                supertrend.iloc[i] = supertrend.iloc[i-1]
                direction.iloc[i] = direction.iloc[i-1]
                continue
                
            if close.iloc[i] > upper_band.iloc[i-1]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            elif close.iloc[i] < lower_band.iloc[i-1]:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = supertrend.iloc[i-1]
                direction.iloc[i] = direction.iloc[i-1]
        
        return {'supertrend': supertrend, 'direction': direction}
    
    @staticmethod
    def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period=14):
        """Average Directional Index"""
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = IndicatorComputationService._compute_atr(high, low, close, 1)
        
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr)
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx
    
    @staticmethod
    def _compute_vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, timestamp: pd.Series):
        """Volume Weighted Average Price - Resets daily"""
        typical_price = (high + low + close) / 3
        
        # Convert timestamp to date for grouping
        dates = pd.to_datetime(timestamp).dt.date
        
        # Calculate VWAP per day
        vwap = pd.Series(index=high.index, dtype=float)
        
        for date in dates.unique():
            mask = dates == date
            daily_tp = typical_price[mask]
            daily_vol = volume[mask]
            
            # Cumulative sum within the day
            daily_vwap = (daily_tp * daily_vol).cumsum() / daily_vol.cumsum()
            vwap[mask] = daily_vwap
        
        return vwap
    
    @staticmethod
    def _compute_vwma(close: pd.Series, volume: pd.Series, period: int = 20):
        """Volume Weighted Moving Average"""
        # VWMA = SUM(close * volume, period) / SUM(volume, period)
        pv = close * volume
        return pv.rolling(window=period).sum() / volume.rolling(window=period).sum()
    
    @staticmethod
    def _compute_obv(close: pd.Series, volume: pd.Series):
        """On-Balance Volume"""
        obv = pd.Series(index=close.index, dtype=float)
        obv.iloc[0] = volume.iloc[0]
        
        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
        return obv
    
    @staticmethod
    def _compute_all_pivots(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all pivot types: Standard, Fibonacci, and Camarilla"""
        pivots = pd.DataFrame(index=df.index)
        
        # Group by date
        if 'timestamp' in df.columns:
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
        else:
            df['date'] = df.index.date
        
        for date in df['date'].unique():
            prev_date_idx = df['date'] == date
            if prev_date_idx.sum() == 0:
                continue
            
            prev_data = df[prev_date_idx]
            high = prev_data['high'].max()
            low = prev_data['low'].min()
            close = prev_data['close'].iloc[-1]
            
            # === STANDARD PIVOT POINTS ===
            pp = (high + low + close) / 3
            pivots.loc[prev_date_idx, 'pivot_point'] = pp
            pivots.loc[prev_date_idx, 'pivot_r1'] = (2 * pp) - low
            pivots.loc[prev_date_idx, 'pivot_r2'] = pp + (high - low)
            pivots.loc[prev_date_idx, 'pivot_r3'] = high + 2 * (pp - low)
            pivots.loc[prev_date_idx, 'pivot_s1'] = (2 * pp) - high
            pivots.loc[prev_date_idx, 'pivot_s2'] = pp - (high - low)
            pivots.loc[prev_date_idx, 'pivot_s3'] = low - 2 * (high - pp)
            
            # === FIBONACCI PIVOT POINTS ===
            range_hl = high - low
            fib_pp = (high + low + close) / 3
            
            pivots.loc[prev_date_idx, 'fib_pivot'] = fib_pp
            pivots.loc[prev_date_idx, 'fib_r1'] = fib_pp + (0.382 * range_hl)
            pivots.loc[prev_date_idx, 'fib_r2'] = fib_pp + (0.618 * range_hl)
            pivots.loc[prev_date_idx, 'fib_r3'] = fib_pp + (1.000 * range_hl)
            pivots.loc[prev_date_idx, 'fib_s1'] = fib_pp - (0.382 * range_hl)
            pivots.loc[prev_date_idx, 'fib_s2'] = fib_pp - (0.618 * range_hl)
            pivots.loc[prev_date_idx, 'fib_s3'] = fib_pp - (1.000 * range_hl)
            
            # === CAMARILLA PIVOT POINTS ===
            # Camarilla uses different formula with tighter levels
            pivots.loc[prev_date_idx, 'cam_r4'] = close + (range_hl * 1.1 / 2)
            pivots.loc[prev_date_idx, 'cam_r3'] = close + (range_hl * 1.1 / 4)
            pivots.loc[prev_date_idx, 'cam_r2'] = close + (range_hl * 1.1 / 6)
            pivots.loc[prev_date_idx, 'cam_r1'] = close + (range_hl * 1.1 / 12)
            pivots.loc[prev_date_idx, 'cam_s1'] = close - (range_hl * 1.1 / 12)
            pivots.loc[prev_date_idx, 'cam_s2'] = close - (range_hl * 1.1 / 6)
            pivots.loc[prev_date_idx, 'cam_s3'] = close - (range_hl * 1.1 / 4)
            pivots.loc[prev_date_idx, 'cam_s4'] = close - (range_hl * 1.1 / 2)
        
        return pivots
    
    async def store_candles_with_indicators(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame
    ) -> int:
        """
        Compute indicators and store in database
        
        Returns:
            Number of candles stored
        """
        # Compute all indicators
        df_with_indicators = self.compute_all_indicators(df.copy())
        
        # Prepare records for bulk insert
        records = []
        for idx, row in df_with_indicators.iterrows():
            record = CandleData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=row.get('timestamp', idx),
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['volume'],
                # Moving averages
                sma_9=row.get('sma_9'),
                sma_20=row.get('sma_20'),
                sma_50=row.get('sma_50'),
                sma_200=row.get('sma_200'),
                ema_9=row.get('ema_9'),
                ema_21=row.get('ema_21'),
                ema_50=row.get('ema_50'),
                ema_200=row.get('ema_200'),
                # Momentum
                rsi_14=row.get('rsi_14'),
                rsi_9=row.get('rsi_9'),
                macd=row.get('macd'),
                macd_signal=row.get('macd_signal'),
                macd_histogram=row.get('macd_histogram'),
                stoch_k=row.get('stoch_k'),
                stoch_d=row.get('stoch_d'),
                # Volatility
                bb_upper=row.get('bb_upper'),
                bb_middle=row.get('bb_middle'),
                bb_lower=row.get('bb_lower'),
                atr_14=row.get('atr_14'),
                # Trend
                supertrend=row.get('supertrend'),
                supertrend_direction=int(row.get('supertrend_direction', 0)) if pd.notna(row.get('supertrend_direction')) else None,
                adx=row.get('adx'),
                # Standard Pivots
                pivot_point=row.get('pivot_point'),
                pivot_r1=row.get('pivot_r1'),
                pivot_r2=row.get('pivot_r2'),
                pivot_r3=row.get('pivot_r3'),
                pivot_s1=row.get('pivot_s1'),
                pivot_s2=row.get('pivot_s2'),
                pivot_s3=row.get('pivot_s3'),
                # Fibonacci Pivots
                fib_pivot=row.get('fib_pivot'),
                fib_r1=row.get('fib_r1'),
                fib_r2=row.get('fib_r2'),
                fib_r3=row.get('fib_r3'),
                fib_s1=row.get('fib_s1'),
                fib_s2=row.get('fib_s2'),
                fib_s3=row.get('fib_s3'),
                # Camarilla Pivots
                cam_r4=row.get('cam_r4'),
                cam_r3=row.get('cam_r3'),
                cam_r2=row.get('cam_r2'),
                cam_r1=row.get('cam_r1'),
                cam_s1=row.get('cam_s1'),
                cam_s2=row.get('cam_s2'),
                cam_s3=row.get('cam_s3'),
                cam_s4=row.get('cam_s4'),
                # Volume
                vwap=row.get('vwap'),
                vwma_20=row.get('vwma_20'),
                vwma_22=row.get('vwma_22'),
                vwma_31=row.get('vwma_31'),
                vwma_50=row.get('vwma_50'),
                obv=int(row.get('obv', 0)) if pd.notna(row.get('obv')) else None,
            )
            records.append(record)
        
        # Bulk insert
        self.db.add_all(records)
        await self.db.commit()
        
        logger.info(f"Stored {len(records)} candles with indicators for {symbol} {timeframe}")
        return len(records)
    
    async def get_candles_with_indicators(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Retrieve candles with pre-computed indicators
        
        Returns:
            DataFrame with all OHLCV and indicator data
        """
        query = select(CandleData).where(
            and_(
                CandleData.symbol == symbol,
                CandleData.timeframe == timeframe
            )
        )
        
        if start_date:
            query = query.where(CandleData.timestamp >= start_date)
        if end_date:
            query = query.where(CandleData.timestamp <= end_date)
        
        query = query.order_by(CandleData.timestamp)
        
        if limit:
            query = query.limit(limit)
        
        result = await self.db.execute(query)
        candles = result.scalars().all()
        
        # Convert to DataFrame
        data = []
        for candle in candles:
            data.append({
                'timestamp': candle.timestamp,
                'open': candle.open,
                'high': candle.high,
                'low': candle.low,
                'close': candle.close,
                'volume': candle.volume,
                'sma_9': candle.sma_9,
                'sma_20': candle.sma_20,
                'sma_50': candle.sma_50,
                'sma_200': candle.sma_200,
                'ema_9': candle.ema_9,
                'ema_21': candle.ema_21,
                'ema_50': candle.ema_50,
                'ema_200': candle.ema_200,
                'rsi_14': candle.rsi_14,
                'rsi_9': candle.rsi_9,
                'macd': candle.macd,
                'macd_signal': candle.macd_signal,
                'macd_histogram': candle.macd_histogram,
                'stoch_k': candle.stoch_k,
                'stoch_d': candle.stoch_d,
                'bb_upper': candle.bb_upper,
                'bb_middle': candle.bb_middle,
                'bb_lower': candle.bb_lower,
                'atr_14': candle.atr_14,
                'supertrend': candle.supertrend,
                'supertrend_direction': candle.supertrend_direction,
                'adx': candle.adx,
                'pivot_point': candle.pivot_point,
                'pivot_r1': candle.pivot_r1,
                'pivot_r2': candle.pivot_r2,
                'pivot_r3': candle.pivot_r3,
                'pivot_s1': candle.pivot_s1,
                'pivot_s2': candle.pivot_s2,
                'pivot_s3': candle.pivot_s3,
                # Fibonacci pivots
                'fib_pivot': candle.fib_pivot,
                'fib_r1': candle.fib_r1,
                'fib_r2': candle.fib_r2,
                'fib_r3': candle.fib_r3,
                'fib_s1': candle.fib_s1,
                'fib_s2': candle.fib_s2,
                'fib_s3': candle.fib_s3,
                # Camarilla pivots
                'cam_r4': candle.cam_r4,
                'cam_r3': candle.cam_r3,
                'cam_r2': candle.cam_r2,
                'cam_r1': candle.cam_r1,
                'cam_s1': candle.cam_s1,
                'cam_s2': candle.cam_s2,
                'cam_s3': candle.cam_s3,
                'cam_s4': candle.cam_s4,
                # Volume
                'vwap': candle.vwap,
                'vwma_20': candle.vwma_20,
                'vwma_22': candle.vwma_22,
                'vwma_31': candle.vwma_31,
                'vwma_50': candle.vwma_50,
                'obv': candle.obv,
            })
        
        return pd.DataFrame(data)
