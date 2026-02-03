"""
Time Series Repository
KeepGaining Trading Platform

Data access layer for time series data including candles, indicators, and option greeks.
"""

from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.db.models.timeseries import (
    CandleData,
    IndicatorData,
    OptionGreeks,
    OptionChainSnapshot,
)


class CandleRepository(BaseRepository[CandleData]):
    """Repository for OHLCV candle data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(CandleData, session)
    
    async def get_candles(
        self,
        instrument_id: str,
        timeframe: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[CandleData]:
        """Get candles for an instrument in a time range."""
        end = end_time or datetime.now()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.instrument_id == instrument_id,
                    self.model.timeframe == timeframe,
                    self.model.timestamp >= start_time,
                    self.model.timestamp <= end,
                )
            )
            .order_by(self.model.timestamp)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_latest_candles(
        self,
        instrument_id: str,
        timeframe: str,
        count: int = 100,
    ) -> List[CandleData]:
        """Get the latest N candles."""
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.instrument_id == instrument_id,
                    self.model.timeframe == timeframe,
                )
            )
            .order_by(self.model.timestamp.desc())
            .limit(count)
        )
        candles = list(result.scalars().all())
        return list(reversed(candles))  # Return in chronological order
    
    async def get_latest_candle(
        self,
        instrument_id: str,
        timeframe: str,
    ) -> Optional[CandleData]:
        """Get the most recent candle."""
        candles = await self.get_latest_candles(instrument_id, timeframe, 1)
        return candles[0] if candles else None
    
    async def get_daily_ohlc(
        self,
        instrument_id: str,
        start_date: date,
        end_date: Optional[date] = None,
    ) -> List[CandleData]:
        """Get daily OHLCV data."""
        end = end_date or date.today()
        
        return await self.get_candles(
            instrument_id=instrument_id,
            timeframe="1D",
            start_time=datetime.combine(start_date, datetime.min.time()),
            end_time=datetime.combine(end, datetime.max.time()),
        )
    
    async def get_intraday_candles(
        self,
        instrument_id: str,
        timeframe: str,
        trading_date: date,
    ) -> List[CandleData]:
        """Get all intraday candles for a specific date."""
        start = datetime.combine(trading_date, datetime.min.time())
        end = datetime.combine(trading_date, datetime.max.time())
        
        return await self.get_candles(
            instrument_id=instrument_id,
            timeframe=timeframe,
            start_time=start,
            end_time=end,
        )
    
    async def bulk_insert_candles(
        self,
        candles: List[Dict[str, Any]],
    ) -> int:
        """Bulk insert candles."""
        if not candles:
            return 0
        
        from sqlalchemy.dialects.postgresql import insert
        
        stmt = insert(self.model).values(candles)
        
        # On conflict, update OHLCV values
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "timeframe", "timestamp"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "oi": stmt.excluded.oi,
            },
        )
        
        result = await self.session.execute(stmt)
        await self.session.commit()
        
        return result.rowcount
    
    async def get_vwap(
        self,
        instrument_id: str,
        trading_date: date,
    ) -> Optional[float]:
        """Calculate VWAP for a trading day."""
        candles = await self.get_intraday_candles(instrument_id, "1m", trading_date)
        
        if not candles:
            return None
        
        total_volume = sum(c.volume or 0 for c in candles)
        if total_volume == 0:
            return None
        
        vwap = sum(
            ((c.high + c.low + c.close) / 3) * (c.volume or 0)
            for c in candles
        ) / total_volume
        
        return round(vwap, 2)
    
    async def get_gap_analysis(
        self,
        instrument_id: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Analyze gaps in daily data."""
        candles = await self.get_daily_ohlc(instrument_id, start_date, end_date)
        
        gaps = []
        for i in range(1, len(candles)):
            prev_close = candles[i-1].close
            curr_open = candles[i].open
            gap_pct = ((curr_open - prev_close) / prev_close) * 100
            
            if abs(gap_pct) > 0.5:  # Gap > 0.5%
                gaps.append({
                    "date": candles[i].timestamp.date(),
                    "prev_close": prev_close,
                    "open": curr_open,
                    "gap_pct": round(gap_pct, 2),
                    "gap_type": "UP" if gap_pct > 0 else "DOWN",
                })
        
        return gaps


class IndicatorRepository(BaseRepository[IndicatorData]):
    """Repository for technical indicator data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(IndicatorData, session)
    
    async def get_indicator(
        self,
        instrument_id: str,
        timeframe: str,
        indicator_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> List[IndicatorData]:
        """Get indicator values for a time range."""
        end = end_time or datetime.now()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.instrument_id == instrument_id,
                    self.model.timeframe == timeframe,
                    self.model.indicator_name == indicator_name,
                    self.model.timestamp >= start_time,
                    self.model.timestamp <= end,
                )
            )
            .order_by(self.model.timestamp)
        )
        return list(result.scalars().all())
    
    async def get_latest_indicators(
        self,
        instrument_id: str,
        timeframe: str,
        indicator_names: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """Get latest values for all or specific indicators."""
        # Subquery for latest timestamp per indicator
        subquery = (
            select(
                self.model.indicator_name,
                func.max(self.model.timestamp).label("max_ts"),
            )
            .where(
                and_(
                    self.model.instrument_id == instrument_id,
                    self.model.timeframe == timeframe,
                )
            )
            .group_by(self.model.indicator_name)
            .subquery()
        )
        
        query = (
            select(self.model)
            .join(
                subquery,
                and_(
                    self.model.indicator_name == subquery.c.indicator_name,
                    self.model.timestamp == subquery.c.max_ts,
                ),
            )
            .where(
                and_(
                    self.model.instrument_id == instrument_id,
                    self.model.timeframe == timeframe,
                )
            )
        )
        
        if indicator_names:
            query = query.where(self.model.indicator_name.in_(indicator_names))
        
        result = await self.session.execute(query)
        indicators = result.scalars().all()
        
        return {ind.indicator_name: ind.value for ind in indicators}
    
    async def bulk_insert_indicators(
        self,
        indicators: List[Dict[str, Any]],
    ) -> int:
        """Bulk insert indicator data."""
        if not indicators:
            return 0
        
        from sqlalchemy.dialects.postgresql import insert
        
        stmt = insert(self.model).values(indicators)
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "timeframe", "indicator_name", "timestamp"],
            set_={"value": stmt.excluded.value, "params": stmt.excluded.params},
        )
        
        result = await self.session.execute(stmt)
        await self.session.commit()
        
        return result.rowcount


class OptionGreeksRepository(BaseRepository[OptionGreeks]):
    """Repository for option greeks data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(OptionGreeks, session)
    
    async def get_greeks_history(
        self,
        option_id: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> List[OptionGreeks]:
        """Get greeks history for an option."""
        end = end_time or datetime.now()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.option_id == option_id,
                    self.model.timestamp >= start_time,
                    self.model.timestamp <= end,
                )
            )
            .order_by(self.model.timestamp)
        )
        return list(result.scalars().all())
    
    async def get_latest_greeks(
        self,
        option_id: str,
    ) -> Optional[OptionGreeks]:
        """Get latest greeks for an option."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.option_id == option_id)
            .order_by(self.model.timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def bulk_insert_greeks(
        self,
        greeks: List[Dict[str, Any]],
    ) -> int:
        """Bulk insert greeks data."""
        if not greeks:
            return 0
        
        from sqlalchemy.dialects.postgresql import insert
        
        stmt = insert(self.model).values(greeks)
        stmt = stmt.on_conflict_do_update(
            index_elements=["option_id", "timestamp"],
            set_={
                "iv": stmt.excluded.iv,
                "delta": stmt.excluded.delta,
                "gamma": stmt.excluded.gamma,
                "theta": stmt.excluded.theta,
                "vega": stmt.excluded.vega,
                "underlying_price": stmt.excluded.underlying_price,
            },
        )
        
        result = await self.session.execute(stmt)
        await self.session.commit()
        
        return result.rowcount


class OptionChainSnapshotRepository(BaseRepository[OptionChainSnapshot]):
    """Repository for option chain snapshot data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(OptionChainSnapshot, session)
    
    async def get_snapshots(
        self,
        underlying: str,
        expiry_date: date,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> List[OptionChainSnapshot]:
        """Get option chain snapshots."""
        end = end_time or datetime.now()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.expiry_date == expiry_date,
                    self.model.timestamp >= start_time,
                    self.model.timestamp <= end,
                )
            )
            .order_by(self.model.timestamp, self.model.strike_price)
        )
        return list(result.scalars().all())
    
    async def get_latest_chain(
        self,
        underlying: str,
        expiry_date: date,
    ) -> List[OptionChainSnapshot]:
        """Get latest option chain snapshot."""
        # Get latest timestamp
        latest_ts = await self.session.execute(
            select(func.max(self.model.timestamp))
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.expiry_date == expiry_date,
                )
            )
        )
        max_ts = latest_ts.scalar()
        
        if not max_ts:
            return []
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.expiry_date == expiry_date,
                    self.model.timestamp == max_ts,
                )
            )
            .order_by(self.model.strike_price)
        )
        return list(result.scalars().all())
    
    async def get_pcr_history(
        self,
        underlying: str,
        expiry_date: date,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get Put-Call Ratio history."""
        snapshots = await self.get_snapshots(
            underlying, expiry_date, start_time, end_time
        )
        
        # Group by timestamp
        from itertools import groupby
        
        pcr_history = []
        for ts, group in groupby(snapshots, key=lambda x: x.timestamp):
            chain = list(group)
            
            total_ce_oi = sum(s.ce_oi or 0 for s in chain)
            total_pe_oi = sum(s.pe_oi or 0 for s in chain)
            
            if total_ce_oi > 0:
                pcr_history.append({
                    "timestamp": ts,
                    "pcr_oi": round(total_pe_oi / total_ce_oi, 3),
                    "total_ce_oi": total_ce_oi,
                    "total_pe_oi": total_pe_oi,
                })
        
        return pcr_history
    
    async def bulk_insert_chain(
        self,
        chain_data: List[Dict[str, Any]],
    ) -> int:
        """Bulk insert option chain data."""
        if not chain_data:
            return 0
        
        from sqlalchemy.dialects.postgresql import insert
        
        stmt = insert(self.model).values(chain_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["underlying_symbol", "expiry_date", "strike_price", "timestamp"],
            set_={
                "ce_ltp": stmt.excluded.ce_ltp,
                "pe_ltp": stmt.excluded.pe_ltp,
                "ce_oi": stmt.excluded.ce_oi,
                "pe_oi": stmt.excluded.pe_oi,
                "ce_volume": stmt.excluded.ce_volume,
                "pe_volume": stmt.excluded.pe_volume,
                "ce_iv": stmt.excluded.ce_iv,
                "pe_iv": stmt.excluded.pe_iv,
            },
        )
        
        result = await self.session.execute(stmt)
        await self.session.commit()
        
        return result.rowcount


__all__ = [
    "CandleRepository",
    "IndicatorRepository",
    "OptionGreeksRepository",
    "OptionChainSnapshotRepository",
]
