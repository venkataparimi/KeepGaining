"""
Instrument Repository
KeepGaining Trading Platform

Data access layer for instrument master data.
"""

from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type

from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.db.models.instrument import (
    InstrumentMaster,
    EquityMaster,
    FutureMaster,
    OptionMaster,
    SectorMaster,
    IndexConstituents,
)


class InstrumentRepository(BaseRepository[InstrumentMaster]):
    """Repository for instrument master data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(InstrumentMaster, session)
    
    async def get_by_symbol(self, symbol: str) -> Optional[InstrumentMaster]:
        """Get instrument by trading symbol."""
        return await self.get_by_field("trading_symbol", symbol)
    
    async def get_by_symbols(self, symbols: List[str]) -> List[InstrumentMaster]:
        """Get multiple instruments by trading symbols."""
        result = await self.session.execute(
            select(self.model).where(self.model.trading_symbol.in_(symbols))
        )
        return list(result.scalars().all())
    
    async def get_by_exchange_token(
        self,
        exchange: str,
        token: str,
    ) -> Optional[InstrumentMaster]:
        """Get instrument by exchange and token."""
        result = await self.session.execute(
            select(self.model).where(
                and_(
                    self.model.exchange == exchange,
                    self.model.exchange_token == token,
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def search_instruments(
        self,
        query: str,
        exchange: Optional[str] = None,
        segment: Optional[str] = None,
        instrument_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[InstrumentMaster]:
        """Search instruments by name or symbol."""
        conditions = [
            or_(
                self.model.trading_symbol.ilike(f"%{query}%"),
                self.model.name.ilike(f"%{query}%"),
            )
        ]
        
        if exchange:
            conditions.append(self.model.exchange == exchange)
        if segment:
            conditions.append(self.model.segment == segment)
        if instrument_type:
            conditions.append(self.model.instrument_type == instrument_type)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.trading_symbol)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_active_by_segment(
        self,
        segment: str,
        exchange: Optional[str] = None,
    ) -> List[InstrumentMaster]:
        """Get all active instruments in a segment."""
        conditions = [
            self.model.segment == segment,
            self.model.is_active == True,
        ]
        
        if exchange:
            conditions.append(self.model.exchange == exchange)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.trading_symbol)
        )
        return list(result.scalars().all())
    
    async def get_fo_stocks(self, exchange: str = "NSE") -> List[InstrumentMaster]:
        """Get all F&O eligible stocks."""
        # Get instruments that have corresponding futures/options
        result = await self.session.execute(
            select(self.model).where(
                and_(
                    self.model.exchange == exchange,
                    self.model.segment == "EQ",
                    self.model.is_active == True,
                    # Check if underlying exists in FO segment
                    self.model.trading_symbol.in_(
                        select(FutureMaster.underlying_symbol)
                        .where(FutureMaster.is_active == True)
                        .distinct()
                    )
                )
            ).order_by(self.model.trading_symbol)
        )
        return list(result.scalars().all())
    
    async def bulk_upsert(
        self,
        instruments: List[Dict[str, Any]],
        conflict_columns: List[str] = None,
    ) -> int:
        """
        Bulk upsert instruments.
        
        Returns number of rows affected.
        """
        from sqlalchemy.dialects.postgresql import insert
        
        if not instruments:
            return 0
        
        conflict_columns = conflict_columns or ["exchange", "trading_symbol"]
        
        stmt = insert(self.model).values(instruments)
        
        # Update columns on conflict
        update_columns = {
            col.name: col
            for col in stmt.excluded
            if col.name not in conflict_columns and col.name != "id"
        }
        
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_columns,
            set_=update_columns,
        )
        
        result = await self.session.execute(stmt)
        await self.session.commit()
        
        return result.rowcount


class EquityRepository(BaseRepository[EquityMaster]):
    """Repository for equity master data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(EquityMaster, session)
    
    async def get_by_symbol(self, symbol: str) -> Optional[EquityMaster]:
        """Get equity by symbol."""
        return await self.get_by_field("symbol", symbol)
    
    async def get_by_isin(self, isin: str) -> Optional[EquityMaster]:
        """Get equity by ISIN."""
        return await self.get_by_field("isin", isin)
    
    async def get_by_sector(self, sector: str) -> List[EquityMaster]:
        """Get equities by sector."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.sector == sector)
            .order_by(self.model.symbol)
        )
        return list(result.scalars().all())
    
    async def get_fo_eligible(self) -> List[EquityMaster]:
        """Get all F&O eligible stocks."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.is_fo_eligible == True)
            .order_by(self.model.symbol)
        )
        return list(result.scalars().all())


class FutureRepository(BaseRepository[FutureMaster]):
    """Repository for future contract data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(FutureMaster, session)
    
    async def get_active_contracts(
        self,
        underlying: str,
        as_of_date: Optional[date] = None,
    ) -> List[FutureMaster]:
        """Get active future contracts for an underlying."""
        as_of = as_of_date or date.today()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.expiry_date >= as_of,
                    self.model.is_active == True,
                )
            )
            .order_by(self.model.expiry_date)
        )
        return list(result.scalars().all())
    
    async def get_current_month_contract(
        self,
        underlying: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[FutureMaster]:
        """Get current month future contract."""
        contracts = await self.get_active_contracts(underlying, as_of_date)
        return contracts[0] if contracts else None
    
    async def get_next_month_contract(
        self,
        underlying: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[FutureMaster]:
        """Get next month future contract."""
        contracts = await self.get_active_contracts(underlying, as_of_date)
        return contracts[1] if len(contracts) > 1 else None
    
    async def get_expiring_contracts(
        self,
        expiry_date: date,
    ) -> List[FutureMaster]:
        """Get all contracts expiring on a specific date."""
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.expiry_date == expiry_date,
                    self.model.is_active == True,
                )
            )
            .order_by(self.model.underlying_symbol)
        )
        return list(result.scalars().all())


class OptionRepository(BaseRepository[OptionMaster]):
    """Repository for option contract data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(OptionMaster, session)
    
    async def get_option_chain(
        self,
        underlying: str,
        expiry_date: date,
        strike_range: Optional[Tuple[float, float]] = None,
    ) -> List[OptionMaster]:
        """Get option chain for an underlying and expiry."""
        conditions = [
            self.model.underlying_symbol == underlying,
            self.model.expiry_date == expiry_date,
            self.model.is_active == True,
        ]
        
        if strike_range:
            conditions.extend([
                self.model.strike_price >= strike_range[0],
                self.model.strike_price <= strike_range[1],
            ])
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.strike_price, self.model.option_type)
        )
        return list(result.scalars().all())
    
    async def get_atm_options(
        self,
        underlying: str,
        expiry_date: date,
        spot_price: float,
    ) -> Tuple[Optional[OptionMaster], Optional[OptionMaster]]:
        """Get ATM call and put options."""
        # Get nearest strikes
        chain = await self.get_option_chain(underlying, expiry_date)
        
        if not chain:
            return None, None
        
        # Find closest strike to spot
        closest_strike = min(
            set(o.strike_price for o in chain),
            key=lambda x: abs(x - spot_price),
        )
        
        atm_call = next(
            (o for o in chain if o.strike_price == closest_strike and o.option_type == "CE"),
            None,
        )
        atm_put = next(
            (o for o in chain if o.strike_price == closest_strike and o.option_type == "PE"),
            None,
        )
        
        return atm_call, atm_put
    
    async def get_available_expiries(
        self,
        underlying: str,
        as_of_date: Optional[date] = None,
    ) -> List[date]:
        """Get all available expiry dates for an underlying."""
        as_of = as_of_date or date.today()
        
        result = await self.session.execute(
            select(self.model.expiry_date)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.expiry_date >= as_of,
                    self.model.is_active == True,
                )
            )
            .distinct()
            .order_by(self.model.expiry_date)
        )
        return [row[0] for row in result.fetchall()]
    
    async def get_available_strikes(
        self,
        underlying: str,
        expiry_date: date,
    ) -> List[float]:
        """Get all available strike prices for an underlying and expiry."""
        result = await self.session.execute(
            select(self.model.strike_price)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.expiry_date == expiry_date,
                    self.model.is_active == True,
                )
            )
            .distinct()
            .order_by(self.model.strike_price)
        )
        return [row[0] for row in result.fetchall()]


class SectorRepository(BaseRepository[SectorMaster]):
    """Repository for sector master data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(SectorMaster, session)
    
    async def get_by_name(self, name: str) -> Optional[SectorMaster]:
        """Get sector by name."""
        return await self.get_by_field("sector_name", name)
    
    async def get_active_sectors(self) -> List[SectorMaster]:
        """Get all active sectors."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.is_active == True)
            .order_by(self.model.sector_name)
        )
        return list(result.scalars().all())


class IndexConstituentRepository(BaseRepository[IndexConstituents]):
    """Repository for index constituent data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(IndexConstituents, session)
    
    async def get_constituents(
        self,
        index_symbol: str,
        as_of_date: Optional[date] = None,
    ) -> List[IndexConstituent]:
        """Get current constituents of an index."""
        as_of = as_of_date or date.today()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.index_symbol == index_symbol,
                    self.model.inclusion_date <= as_of,
                    or_(
                        self.model.exclusion_date.is_(None),
                        self.model.exclusion_date > as_of,
                    ),
                )
            )
            .order_by(self.model.weight.desc())
        )
        return list(result.scalars().all())
    
    async def get_nifty50_constituents(
        self,
        as_of_date: Optional[date] = None,
    ) -> List[IndexConstituent]:
        """Get NIFTY 50 constituents."""
        return await self.get_constituents("NIFTY 50", as_of_date)
    
    async def get_banknifty_constituents(
        self,
        as_of_date: Optional[date] = None,
    ) -> List[IndexConstituent]:
        """Get BANK NIFTY constituents."""
        return await self.get_constituents("NIFTY BANK", as_of_date)
    
    async def get_stock_indices(
        self,
        symbol: str,
        as_of_date: Optional[date] = None,
    ) -> List[str]:
        """Get all indices a stock belongs to."""
        as_of = as_of_date or date.today()
        
        result = await self.session.execute(
            select(self.model.index_symbol)
            .where(
                and_(
                    self.model.constituent_symbol == symbol,
                    self.model.inclusion_date <= as_of,
                    or_(
                        self.model.exclusion_date.is_(None),
                        self.model.exclusion_date > as_of,
                    ),
                )
            )
            .distinct()
        )
        return [row[0] for row in result.fetchall()]


__all__ = [
    "InstrumentRepository",
    "EquityRepository",
    "FutureRepository",
    "OptionRepository",
    "SectorRepository",
    "IndexConstituentRepository",
]
