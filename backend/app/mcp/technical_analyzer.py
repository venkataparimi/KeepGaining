from datetime import datetime, timedelta
import logging
import pandas as pd
import numpy as np
from sqlalchemy import select, desc
from typing import Dict, Any, Optional

from app.db.session import AsyncSessionLocal
from app.db.models import InstrumentMaster, CandleData
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, MACD

logger = logging.getLogger(__name__)

class TechnicalAnalyzer:
    """
    Analyzes historical data from the database to generate a technical score.
    """
    
    def __init__(self):
        pass

    async def get_technical_analysis(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch daily candles from DB (or aggregate from 1m) and calculate technical indicators.
        Returns a dictionary with score and indicator values.
        """
        async with AsyncSessionLocal() as session:
            # 1. Get Instrument ID
            stmt = select(InstrumentMaster).where(InstrumentMaster.trading_symbol == symbol)
            result = await session.execute(stmt)
            instrument = result.scalar_one_or_none()
            
            if not instrument:
                logger.warning(f"TechnicalAnalyzer: Symbol {symbol} not found in DB")
                return {"score": 0, "rating": "Unknown", "error": "Symbol not found"}
            
            # 2. Fetch Historical Data
            # First try '1d' timeframe
            stmt = select(CandleData).where(
                (CandleData.instrument_id == instrument.instrument_id) &
                (CandleData.timeframe == '1d')
            ).order_by(desc(CandleData.timestamp)).limit(200)
            
            result = await session.execute(stmt)
            candles = result.scalars().all()
            
            # If insufficient '1d' data, try aggregating '1minute' data
            if len(candles) < 50:
                logger.info(f"TechnicalAnalyzer: Insufficient 1d data for {symbol}, trying 1m aggregation...")
                
                # Fetch last 365 days of minute data (limit to reasonable amount)
                # We need enough data to form ~200 daily candles. 
                # 1 year * 375 minutes ~ 100k rows. 
                # Let's limit to last 6 months (approx 125 trading days) to be safe on performance
                cutoff_date = datetime.now() - timedelta(days=200)
                
                stmt_1m = select(CandleData).where(
                    (CandleData.instrument_id == instrument.instrument_id) &
                    (CandleData.timeframe == '1m') &
                    (CandleData.timestamp >= cutoff_date)
                ).order_by(CandleData.timestamp)
                
                result_1m = await session.execute(stmt_1m)
                candles_1m = result_1m.scalars().all()
                
                if not candles_1m:
                    logger.warning(f"TechnicalAnalyzer: No 1m data found for {symbol}")
                    return {"score": 0, "rating": "Unknown", "error": "Insufficient Data"}
                
                # Aggregate to Daily
                df_1m = pd.DataFrame([{
                    'timestamp': c.timestamp,
                    'open': float(c.open),
                    'high': float(c.high),
                    'low': float(c.low),
                    'close': float(c.close),
                    'volume': c.volume
                } for c in candles_1m])
                
                df_1m.set_index('timestamp', inplace=True)
                
                # Resample
                df = df_1m.resample('1D').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
                
            else:
                 # Convert to DataFrame (reverse to chronological order)
                df = pd.DataFrame([{
                    'timestamp': c.timestamp,
                    'close': float(c.close),
                    'high': float(c.high),
                    'low': float(c.low),
                    'open': float(c.open),
                    'volume': c.volume
                } for c in candles][::-1])
            
            if len(df) < 50:
                 logger.warning(f"TechnicalAnalyzer: Insufficient data after aggregation for {symbol} (Rows: {len(df)})")
                 return {"score": 0, "rating": "Unknown", "error": "Insufficient Data"}

            # 3. Calculate Indicators
            try:
                # RSI (14)
                rsi_indicator = RSIIndicator(close=df['close'], window=14)
                df['rsi'] = rsi_indicator.rsi()
                
                # SMA (20, 50)
                sma_20 = SMAIndicator(close=df['close'], window=20)
                sma_50 = SMAIndicator(close=df['close'], window=50)
                df['sma_20'] = sma_20.sma_indicator()
                df['sma_50'] = sma_50.sma_indicator()
                
                # MACD (12, 26, 9)
                macd = MACD(close=df['close'])
                df['macd'] = macd.macd()
                df['macd_signal'] = macd.macd_signal()
                
                # Get latest values
                latest = df.iloc[-1]
                
                # 4. Scoring Logic (0-10 Scale)
                score = 5  # Start neutral
                
                # RSI Logic
                rsi = latest['rsi']
                if pd.isna(rsi): rsi = 50 
                
                if rsi < 30:
                    score += 2  # Oversold (Bullish Reversal potential)
                    rsi_status = "Oversold"
                elif rsi > 70:
                    score -= 2  # Overbought (Bearish potential)
                    rsi_status = "Overbought"
                elif 50 <= rsi <= 70:
                    score += 1  # Bullish Momentum
                    rsi_status = "Bullish"
                else:
                    score -= 1  # Bearish Momentum
                    rsi_status = "Bearish"
                    
                # Trend Logic (SMA Crossover)
                trend_status = "Neutral"
                s20 = latest['sma_20']
                s50 = latest['sma_50']
                
                if not pd.isna(s20) and not pd.isna(s50):
                    if s20 > s50:
                        score += 2
                        trend_status = "Uptrend"
                    else:
                        score -= 2
                        trend_status = "Downtrend"
                else:
                    # Fallback if SMA50 is NaN (insufficient data)
                    score += 0 # Neutral
                    
                # MACD Logic
                macd_val = latest['macd']
                macd_sig = latest['macd_signal']
                
                macd_status = "Neutral"
                if not pd.isna(macd_val) and not pd.isna(macd_sig):
                    if macd_val > macd_sig:
                        score += 1
                        macd_status = "Bullish"
                    else:
                        score -= 1
                        macd_status = "Bearish"
                    
                # Clamp score 0-10
                score = max(0, min(10, score))
                
                # Determination
                if score >= 8: rating = "Strong Buy"
                elif score >= 6: rating = "Buy"
                elif score <= 2: rating = "Strong Sell"
                elif score <= 4: rating = "Sell"
                else: rating = "Neutral"
                
                return {
                    "score": score,
                    "rating": rating,
                    "indicators": {
                        "rsi": round(rsi, 2),
                        "rsi_status": rsi_status,
                        "sma_20": round(s20, 2) if not pd.isna(s20) else 0,
                        "sma_50": round(s50, 2) if not pd.isna(s50) else 0,
                        "trend": trend_status,
                        "macd_status": macd_status
                    },
                    "last_price": latest['close']
                }
                
            except Exception as e:
                logger.error(f"Error computing indicators for {symbol}: {e}")
                return {"score": 0, "rating": "Error", "error": str(e)}
