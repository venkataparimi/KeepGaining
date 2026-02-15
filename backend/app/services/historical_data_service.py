from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
import pandas_ta as ta

from app.db.models.instrument import InstrumentMaster
from app.db.models.timeseries import CandleData

class HistoricalDataService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_instrument_id(self, symbol: str, instrument_type: str = None) -> Optional[str]:
        """
        Get instrument_id for a given symbol and optional instrument_type.
        """
        query = select(InstrumentMaster.instrument_id).where(InstrumentMaster.trading_symbol == symbol)
        if instrument_type:
            query = query.where(InstrumentMaster.instrument_type == instrument_type)
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_historical_data(
        self, 
        symbol: str, 
        start_date: datetime, 
        end_date: datetime, 
        time_frame: str = "1m",
        instrument_type: str = None,
        indicators: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical candle data for a symbol.
        """
        instrument_id = await self.get_instrument_id(symbol, instrument_type)
        if not instrument_id:
            raise ValueError(f"Instrument not found: {symbol}")

        query = select(CandleData).where(
            and_(
                CandleData.instrument_id == instrument_id,
                CandleData.timestamp >= start_date,
                CandleData.timestamp <= end_date
            )
        ).order_by(CandleData.timestamp.asc())

        result = await self.db.execute(query)
        candles = result.scalars().all()
        
        # Convert to DataFrame for resampling and indicator calculation
        data = [
            {
                "time": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume
            }
            for c in candles
        ]
        
        if not data:
            return []

        df = pd.DataFrame(data)
        df.set_index("time", inplace=True)

        # Resample if needed (assuming base data is 1m)
        if time_frame != "1m":
            resample_map = {
                "3m": "3min", "5m": "5min", "15m": "15min", 
                "30m": "30min", "1h": "1H", "1d": "1D"
            }
            freq = resample_map.get(time_frame)
            if freq:
                ohlc_dict = {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum"
                }
                df = df.resample(freq).agg(ohlc_dict).dropna()

        # Calculate indicators
        if indicators:
            for ind in indicators:
                parts = ind.split('_')
                if len(parts) == 2:
                    name = parts[0].lower()
                    length = int(parts[1])
                    if name == "sma":
                        df.ta.sma(length=length, append=True)
                    elif name == "ema":
                        df.ta.ema(length=length, append=True)
                    elif name == "rsi":
                        df.ta.rsi(length=length, append=True)
                else:
                    if ind == "sma":
                        df.ta.sma(length=20, append=True)
                    elif ind == "ema":
                        df.ta.ema(length=20, append=True)
                    elif ind == "rsi":
                        df.ta.rsi(length=14, append=True)

        resp_data = []
        for index, row in df.iterrows():
            item = {
                "time": int(index.timestamp()), # Unix timestamp
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"]
            }
            
            # append indicators
            for col in df.columns:
                if col not in ["open", "high", "low", "close", "volume"]:
                     # handle NaN values
                    val = row[col]
                    if pd.notna(val):
                        item[col] = float(val)
            
            resp_data.append(item)

        return resp_data
