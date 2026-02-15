"""
Instrument Synchronization Service
KeepGaining Trading Platform

Downloads and synchronizes instrument master data from:
- Upstox: NSE, BSE, MCX instruments (JSON format - recommended)
- Fyers: NSE CM, NSE FO, BSE CM, MCX COM (CSV format)

Provides:
- Daily BOD (Beginning of Day) instrument sync
- Broker-specific symbol mapping
- Unified instrument lookup
- F&O instrument filtering
- Expiry management
"""

import asyncio
import gzip
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID
import csv

import aiohttp
import pandas as pd
from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.instrument import (
    InstrumentMaster,
    EquityMaster, 
    FutureMaster,
    OptionMaster,
)
from app.db.models.broker import BrokerSymbolMapping


# =============================================================================
# Constants
# =============================================================================

class BrokerName(str, Enum):
    """Broker identifiers."""
    UPSTOX = "UPSTOX"
    FYERS = "FYERS"
    ZERODHA = "ZERODHA"


class Exchange(str, Enum):
    """Supported exchanges."""
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    NFO = "NFO"  # NSE F&O
    BFO = "BFO"  # BSE F&O
    CDS = "CDS"  # Currency Derivatives
    

class InstrumentType(str, Enum):
    """Instrument types."""
    EQUITY = "EQUITY"
    INDEX = "INDEX"
    FUTURE = "FUTURE"
    OPTION = "OPTION"


# Upstox Instrument URLs (JSON - recommended by docs)
UPSTOX_INSTRUMENT_URLS = {
    "NSE": "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
    "BSE": "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz",
    "MCX": "https://assets.upstox.com/market-quote/instruments/exchange/MCX.json.gz",
    "COMPLETE": "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
}

# Fyers Symbol Master URLs (CSV)
FYERS_SYMBOL_URLS = {
    "NSE_CM": "https://public.fyers.in/sym_details/NSE_CM.csv",
    "NSE_FO": "https://public.fyers.in/sym_details/NSE_FO.csv",
    "NSE_CD": "https://public.fyers.in/sym_details/NSE_CD.csv",
    "NSE_COM": "https://public.fyers.in/sym_details/NSE_COM.csv",
    "BSE_CM": "https://public.fyers.in/sym_details/BSE_CM.csv",
    "BSE_FO": "https://public.fyers.in/sym_details/BSE_FO.csv",
    "MCX_COM": "https://public.fyers.in/sym_details/MCX_COM.csv",
}

# Fyers JSON Symbol Master (alternative format)
FYERS_JSON_URLS = {
    "NSE_CM": "https://public.fyers.in/sym_details/NSE_CM_sym_master.json",
    "NSE_FO": "https://public.fyers.in/sym_details/NSE_FO_sym_master.json",
    "NSE_CD": "https://public.fyers.in/sym_details/NSE_CD_sym_master.json",
    "NSE_COM": "https://public.fyers.in/sym_details/NSE_COM_sym_master.json",
    "BSE_CM": "https://public.fyers.in/sym_details/BSE_CM_sym_master.json",
    "BSE_FO": "https://public.fyers.in/sym_details/BSE_FO_sym_master.json",
    "MCX_COM": "https://public.fyers.in/sym_details/MCX_COM_sym_master.json",
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class UpstoxInstrument:
    """Parsed Upstox instrument data."""
    instrument_key: str  # NSE_EQ|INE839G01010
    exchange: str
    segment: str
    name: str
    trading_symbol: str
    exchange_token: str
    isin: Optional[str] = None
    instrument_type: str = "EQ"
    lot_size: int = 1
    tick_size: float = 0.05
    freeze_quantity: Optional[float] = None
    expiry: Optional[date] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = None  # CE, PE
    underlying_symbol: Optional[str] = None
    short_name: Optional[str] = None
    security_type: str = "NORMAL"
    
    @property
    def is_fno(self) -> bool:
        """Check if instrument is F&O."""
        return self.segment in ("NSE_FO", "BSE_FO", "MCX_FO", "NCD_FO", "BCD_FO")
    
    @property
    def is_equity(self) -> bool:
        """Check if instrument is equity."""
        return self.instrument_type == "EQ"
    
    @property
    def is_index(self) -> bool:
        """Check if instrument is index."""
        return self.segment.endswith("_INDEX") or self.instrument_type == "INDEX"
    
    @property
    def is_future(self) -> bool:
        """Check if instrument is futures."""
        return self.instrument_type.startswith("FUT")
    
    @property
    def is_option(self) -> bool:
        """Check if instrument is options."""
        return self.instrument_type.startswith("OPT") or self.option_type in ("CE", "PE")


@dataclass
class FyersInstrument:
    """Parsed Fyers instrument data."""
    fytoken: str
    symbol_details: str
    exchange_instrument_type: int
    lot_size: int
    tick_size: float
    isin: Optional[str] = None
    trading_session: Optional[str] = None
    last_update_date: Optional[str] = None
    expiry_date: Optional[str] = None
    symbol_ticker: str = ""  # NSE:RELIANCE-EQ
    exchange: int = 10  # 10=NSE, 12=BSE, 11=MCX
    segment: int = 10  # 10=CM, 11=FO, 12=CD, 20=COM
    scrip_code: Optional[int] = None
    underlying_symbol: Optional[str] = None
    underlying_scrip_code: Optional[int] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = None  # CE, PE
    
    # Additional fields from JSON format
    ex_symbol: Optional[str] = None
    sym_ticker: Optional[str] = None
    
    @property
    def exchange_name(self) -> str:
        """Get exchange name from code."""
        return {10: "NSE", 11: "MCX", 12: "BSE"}.get(self.exchange, "NSE")
    
    @property
    def segment_name(self) -> str:
        """Get segment name from code."""
        return {10: "CM", 11: "FO", 12: "CD", 20: "COM"}.get(self.segment, "CM")
    
    @property
    def is_equity(self) -> bool:
        """Check if equity instrument."""
        return self.exchange_instrument_type == 0 and self.segment in (10,)
    
    @property
    def is_index(self) -> bool:
        """Check if index instrument."""
        return self.exchange_instrument_type == 10
    
    @property
    def is_future(self) -> bool:
        """Check if futures instrument."""
        return self.exchange_instrument_type in (11, 12, 13, 16, 30, 33, 34, 35)
    
    @property
    def is_option(self) -> bool:
        """Check if options instrument."""
        return self.exchange_instrument_type in (14, 15, 19, 31, 32, 36, 37)


@dataclass
class SyncStats:
    """Statistics from instrument sync."""
    broker: str
    total_instruments: int = 0
    equities_added: int = 0
    futures_added: int = 0
    options_added: int = 0
    indices_added: int = 0
    mappings_created: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


# =============================================================================
# Instrument Sync Service
# =============================================================================

class InstrumentSyncService:
    """
    Service for synchronizing instrument master data from brokers.
    
    Downloads instrument data from Upstox and Fyers, normalizes it,
    and stores in the database with broker-specific symbol mappings.
    """
    
    def __init__(self):
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._sync_lock = asyncio.Lock()
        
    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=120)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session
    
    async def close(self):
        """Close HTTP session."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
    
    # =========================================================================
    # Upstox Instrument Download
    # =========================================================================
    
    async def download_upstox_instruments(
        self,
        exchange: Optional[str] = None,
    ) -> List[UpstoxInstrument]:
        """
        Download instruments from Upstox.
        
        Args:
            exchange: Optional exchange filter (NSE, BSE, MCX) or None for all
            
        Returns:
            List of parsed Upstox instruments
        """
        url = UPSTOX_INSTRUMENT_URLS.get(exchange, UPSTOX_INSTRUMENT_URLS["NSE"])
        
        try:
            session = await self._get_http_session()
            
            logger.info(f"Downloading Upstox instruments from {url}")
            
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to download Upstox instruments: {response.status}")
                    return []
                
                # Decompress gzip content
                content = await response.read()
                decompressed = gzip.decompress(content)
                data = json.loads(decompressed.decode('utf-8'))
                
            logger.info(f"Downloaded {len(data)} Upstox instruments")
            
            # Parse instruments
            instruments = []
            for item in data:
                try:
                    inst = self._parse_upstox_instrument(item)
                    if inst:
                        instruments.append(inst)
                except Exception as e:
                    logger.debug(f"Error parsing Upstox instrument: {e}")
            
            return instruments
            
        except Exception as e:
            logger.error(f"Error downloading Upstox instruments: {e}")
            return []
    
    def _parse_upstox_instrument(self, data: Dict[str, Any]) -> Optional[UpstoxInstrument]:
        """Parse Upstox JSON instrument data."""
        try:
            # Parse expiry date if present
            expiry = None
            if data.get("expiry"):
                try:
                    expiry = datetime.strptime(data["expiry"], "%Y-%m-%d").date()
                except:
                    pass
            
            # Determine underlying for derivatives
            underlying = data.get("underlying_symbol") or data.get("name")
            if data.get("segment", "").endswith("_FO"):
                # Extract underlying from name for F&O
                underlying = data.get("name", "").split()[0]
            
            strike = data.get("strike")
            if strike is not None:
                try:
                    s_float = float(strike)
                    if s_float % 1 == 0:
                        strike = int(s_float)
                    else:
                        strike = s_float
                except:
                    pass

            return UpstoxInstrument(
                instrument_key=data.get("instrument_key", ""),
                exchange=data.get("exchange", "NSE"),
                segment=data.get("segment", "NSE_EQ"),
                name=data.get("name", ""),
                trading_symbol=data.get("trading_symbol", ""),
                exchange_token=str(data.get("exchange_token", "")),
                isin=data.get("isin"),
                instrument_type=data.get("instrument_type", "EQ"),
                lot_size=int(data.get("lot_size", 1)),
                tick_size=float(data.get("tick_size", 0.05)),
                freeze_quantity=data.get("freeze_quantity"),
                expiry=expiry,
                strike_price=strike,
                option_type=data.get("option_type"),
                underlying_symbol=underlying,
                short_name=data.get("short_name"),
                security_type=data.get("security_type", "NORMAL"),
            )
        except Exception as e:
            logger.debug(f"Error parsing Upstox instrument: {e}")
            return None
    
    # =========================================================================
    # Fyers Instrument Download
    # =========================================================================
    
    async def download_fyers_instruments(
        self,
        segment: str = "NSE_FO",
        use_json: bool = True,
    ) -> List[FyersInstrument]:
        """
        Download instruments from Fyers.
        
        Args:
            segment: Segment to download (NSE_CM, NSE_FO, etc.)
            use_json: Use JSON format (recommended) or CSV
            
        Returns:
            List of parsed Fyers instruments
        """
        if use_json:
            url = FYERS_JSON_URLS.get(segment)
        else:
            url = FYERS_SYMBOL_URLS.get(segment)
        
        if not url:
            logger.error(f"Unknown Fyers segment: {segment}")
            return []
        
        try:
            session = await self._get_http_session()
            
            logger.info(f"Downloading Fyers {segment} instruments from {url}")
            
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to download Fyers instruments: {response.status}")
                    return []
                
                content = await response.text()
            
            if use_json:
                return self._parse_fyers_json(content)
            else:
                return self._parse_fyers_csv(content)
                
        except Exception as e:
            logger.error(f"Error downloading Fyers instruments: {e}")
            return []
    
    def _parse_fyers_json(self, content: str) -> List[FyersInstrument]:
        """Parse Fyers JSON symbol master."""
        instruments = []
        try:
            data = json.loads(content)
            
            for symbol_ticker, info in data.items():
                try:
                    # Parse expiry date
                    expiry_date = None
                    if info.get("expiryDate"):
                        try:
                            # Fyers uses epoch timestamp for expiry
                            expiry_ts = int(info["expiryDate"])
                            expiry_date = datetime.fromtimestamp(expiry_ts).strftime("%Y-%m-%d")
                        except:
                            pass
                    
                    inst = FyersInstrument(
                        fytoken=info.get("fyToken", ""),
                        symbol_details=info.get("symDetails", info.get("symbolDesc", "")),
                        exchange_instrument_type=int(info.get("exInstType", 0)),
                        lot_size=int(info.get("minLotSize", 1)),
                        tick_size=float(info.get("tickSize", 0.05)),
                        isin=info.get("isin"),
                        trading_session=info.get("tradingSession"),
                        expiry_date=expiry_date,
                        symbol_ticker=symbol_ticker,
                        exchange=int(info.get("exchange", 10)),
                        segment=int(info.get("segment", 10)),
                        scrip_code=info.get("exToken"),
                        underlying_symbol=info.get("underSym"),
                        underlying_scrip_code=info.get("underFyTok"),
                        strike_price=info.get("strikePrice"),
                        option_type=info.get("optType"),
                        ex_symbol=info.get("exSymbol"),
                        sym_ticker=info.get("symTicker"),
                    )
                    instruments.append(inst)
                except Exception as e:
                    logger.debug(f"Error parsing Fyers JSON instrument {symbol_ticker}: {e}")
            
            logger.info(f"Parsed {len(instruments)} Fyers instruments from JSON")
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing Fyers JSON: {e}")
        
        return instruments
    
    def _parse_fyers_csv(self, content: str) -> List[FyersInstrument]:
        """Parse Fyers CSV symbol master."""
        instruments = []
        
        try:
            reader = csv.reader(io.StringIO(content))
            
            # CSV columns:
            # Fytoken, Symbol Details, Exchange Instrument type, Minimum lot size, 
            # Tick size, ISIN, Trading Session, Last update date, Expiry date,
            # Symbol ticker, Exchange, Segment, Scrip code, Underlying symbol,
            # Underlying scrip code, Strike price, Option type
            
            for row in reader:
                if len(row) < 10:
                    continue
                
                try:
                    inst = FyersInstrument(
                        fytoken=row[0],
                        symbol_details=row[1],
                        exchange_instrument_type=int(row[2]) if row[2] else 0,
                        lot_size=int(row[3]) if row[3] else 1,
                        tick_size=float(row[4]) if row[4] else 0.05,
                        isin=row[5] if len(row) > 5 and row[5] else None,
                        trading_session=row[6] if len(row) > 6 else None,
                        last_update_date=row[7] if len(row) > 7 else None,
                        expiry_date=row[8] if len(row) > 8 else None,
                        symbol_ticker=row[9] if len(row) > 9 else "",
                        exchange=int(row[10]) if len(row) > 10 and row[10] else 10,
                        segment=int(row[11]) if len(row) > 11 and row[11] else 10,
                        scrip_code=int(row[12]) if len(row) > 12 and row[12] else None,
                        underlying_symbol=row[13] if len(row) > 13 else None,
                        underlying_scrip_code=int(row[14]) if len(row) > 14 and row[14] else None,
                        strike_price=float(row[15]) if len(row) > 15 and row[15] else None,
                        option_type=row[16] if len(row) > 16 and row[16] and row[16] != "XX" else None,
                    )
                    instruments.append(inst)
                except Exception as e:
                    logger.debug(f"Error parsing Fyers CSV row: {e}")
            
            logger.info(f"Parsed {len(instruments)} Fyers instruments from CSV")
            
        except Exception as e:
            logger.error(f"Error parsing Fyers CSV: {e}")
        
        return instruments
    
    # =========================================================================
    # Database Sync
    # =========================================================================
    
    async def sync_upstox_instruments(
        self,
        session: AsyncSession,
        exchange: Optional[str] = None,
    ) -> SyncStats:
        """
        Sync Upstox instruments to database.
        
        Args:
            session: Database session
            exchange: Optional exchange filter
            
        Returns:
            Sync statistics
        """
        start_time = datetime.now()
        stats = SyncStats(broker=BrokerName.UPSTOX.value)
        
        async with self._sync_lock:
            instruments = await self.download_upstox_instruments(exchange)
            stats.total_instruments = len(instruments)
            
            if not instruments:
                logger.warning("No Upstox instruments downloaded")
                return stats
            
            # Group by instrument type
            equities = [i for i in instruments if i.is_equity]
            indices = [i for i in instruments if i.is_index]
            futures = [i for i in instruments if i.is_future]
            options = [i for i in instruments if i.is_option]
            
            logger.info(
                f"Upstox instruments: {len(equities)} equities, {len(indices)} indices, "
                f"{len(futures)} futures, {len(options)} options"
            )
            
            # Sync each type
            stats.equities_added = await self._sync_upstox_equities(session, equities)
            stats.indices_added = await self._sync_upstox_indices(session, indices)
            stats.futures_added = await self._sync_upstox_futures(session, futures)
            stats.options_added = await self._sync_upstox_options(session, options)
            
            await session.commit()
            
        stats.duration_seconds = (datetime.now() - start_time).total_seconds()
        logger.info(f"Upstox sync completed in {stats.duration_seconds:.1f}s")
        
        return stats
    
    async def _sync_upstox_equities(
        self,
        session: AsyncSession,
        instruments: List[UpstoxInstrument],
    ) -> int:
        """Sync equity instruments from Upstox."""
        count = 0
        
        for inst in instruments:
            try:
                # Create/update instrument master
                trading_symbol = f"{inst.exchange}:{inst.trading_symbol}"
                
                # Check if exists
                stmt = select(InstrumentMaster).where(
                    InstrumentMaster.trading_symbol == trading_symbol,
                    InstrumentMaster.exchange == inst.exchange,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing
                    existing.lot_size = inst.lot_size
                    existing.tick_size = Decimal(str(inst.tick_size))
                    existing.is_active = True
                else:
                    # Create new
                    instrument = InstrumentMaster(
                        trading_symbol=trading_symbol,
                        exchange=inst.exchange,
                        segment="EQ",
                        instrument_type=InstrumentType.EQUITY.value,
                        underlying=None,
                        isin=inst.isin,
                        lot_size=inst.lot_size,
                        tick_size=Decimal(str(inst.tick_size)),
                        is_active=True,
                    )
                    session.add(instrument)
                    await session.flush()
                    
                    # Create Upstox mapping
                    mapping = BrokerSymbolMapping(
                        instrument_id=instrument.instrument_id,
                        broker_name=BrokerName.UPSTOX.value,
                        broker_symbol=inst.trading_symbol,
                        broker_token=inst.exchange_token,
                        exchange_code=inst.segment,
                        is_active=True,
                    )
                    session.add(mapping)
                    count += 1
                    
            except Exception as e:
                logger.debug(f"Error syncing Upstox equity {inst.trading_symbol}: {e}")
        
        return count
    
    async def _sync_upstox_indices(
        self,
        session: AsyncSession,
        instruments: List[UpstoxInstrument],
    ) -> int:
        """Sync index instruments from Upstox."""
        count = 0
        
        for inst in instruments:
            try:
                trading_symbol = f"{inst.exchange}:{inst.trading_symbol}"
                
                stmt = select(InstrumentMaster).where(
                    InstrumentMaster.trading_symbol == trading_symbol,
                    InstrumentMaster.exchange == inst.exchange,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if not existing:
                    instrument = InstrumentMaster(
                        trading_symbol=trading_symbol,
                        exchange=inst.exchange,
                        segment="INDEX",
                        instrument_type=InstrumentType.INDEX.value,
                        underlying=None,
                        lot_size=1,
                        tick_size=Decimal("0.05"),
                        is_active=True,
                    )
                    session.add(instrument)
                    await session.flush()
                    
                    mapping = BrokerSymbolMapping(
                        instrument_id=instrument.instrument_id,
                        broker_name=BrokerName.UPSTOX.value,
                        broker_symbol=inst.trading_symbol,
                        broker_token=inst.exchange_token,
                        exchange_code=inst.segment,
                        is_active=True,
                    )
                    session.add(mapping)
                    count += 1
                    
            except Exception as e:
                logger.debug(f"Error syncing Upstox index {inst.trading_symbol}: {e}")
        
        return count
    
    async def _sync_upstox_futures(
        self,
        session: AsyncSession,
        instruments: List[UpstoxInstrument],
    ) -> int:
        """Sync futures instruments from Upstox."""
        count = 0
        
        for inst in instruments:
            try:
                if not inst.expiry:
                    continue
                
                trading_symbol = f"{inst.exchange}:{inst.trading_symbol}"
                
                stmt = select(InstrumentMaster).where(
                    InstrumentMaster.trading_symbol == trading_symbol,
                    InstrumentMaster.exchange == inst.exchange,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if not existing:
                    instrument = InstrumentMaster(
                        trading_symbol=trading_symbol,
                        exchange=inst.exchange,
                        segment="FO",
                        instrument_type=InstrumentType.FUTURE.value,
                        underlying=inst.underlying_symbol,
                        lot_size=inst.lot_size,
                        tick_size=Decimal(str(inst.tick_size)),
                        is_active=True,
                    )
                    session.add(instrument)
                    await session.flush()
                    
                    # Create future master record
                    future = FutureMaster(
                        instrument_id=instrument.instrument_id,
                        expiry_date=inst.expiry,
                        lot_size=inst.lot_size,
                    )
                    session.add(future)
                    
                    mapping = BrokerSymbolMapping(
                        instrument_id=instrument.instrument_id,
                        broker_name=BrokerName.UPSTOX.value,
                        broker_symbol=inst.trading_symbol,
                        broker_token=inst.exchange_token,
                        exchange_code=inst.segment,
                        is_active=True,
                    )
                    session.add(mapping)
                    count += 1
                    
            except Exception as e:
                logger.debug(f"Error syncing Upstox future {inst.trading_symbol}: {e}")
        
        return count
    
    async def _sync_upstox_options(
        self,
        session: AsyncSession,
        instruments: List[UpstoxInstrument],
    ) -> int:
        """Sync options instruments from Upstox."""
        count = 0
        
        for inst in instruments:
            try:
                if not inst.expiry or not inst.strike_price or not inst.option_type:
                    continue
                
                trading_symbol = f"{inst.exchange}:{inst.trading_symbol}"
                
                stmt = select(InstrumentMaster).where(
                    InstrumentMaster.trading_symbol == trading_symbol,
                    InstrumentMaster.exchange == inst.exchange,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if not existing:
                    instrument = InstrumentMaster(
                        trading_symbol=trading_symbol,
                        exchange=inst.exchange,
                        segment="FO",
                        instrument_type=InstrumentType.OPTION.value,
                        underlying=inst.underlying_symbol,
                        lot_size=inst.lot_size,
                        tick_size=Decimal(str(inst.tick_size)),
                        is_active=True,
                    )
                    session.add(instrument)
                    await session.flush()
                    
                    # Create option master record
                    option = OptionMaster(
                        instrument_id=instrument.instrument_id,
                        strike_price=Decimal(str(inst.strike_price)),
                        option_type=inst.option_type,
                        expiry_date=inst.expiry,
                        lot_size=inst.lot_size,
                    )
                    session.add(option)
                    
                    mapping = BrokerSymbolMapping(
                        instrument_id=instrument.instrument_id,
                        broker_name=BrokerName.UPSTOX.value,
                        broker_symbol=inst.trading_symbol,
                        broker_token=inst.exchange_token,
                        exchange_code=inst.segment,
                        is_active=True,
                    )
                    session.add(mapping)
                    count += 1
                    
            except Exception as e:
                logger.debug(f"Error syncing Upstox option {inst.trading_symbol}: {e}")
        
        return count
    
    async def sync_fyers_instruments(
        self,
        session: AsyncSession,
        segments: Optional[List[str]] = None,
    ) -> SyncStats:
        """
        Sync Fyers instruments to database.
        
        Args:
            session: Database session
            segments: Segments to sync (default: NSE_CM, NSE_FO)
            
        Returns:
            Sync statistics
        """
        start_time = datetime.now()
        stats = SyncStats(broker=BrokerName.FYERS.value)
        
        if segments is None:
            segments = ["NSE_CM", "NSE_FO"]
        
        async with self._sync_lock:
            all_instruments = []
            
            for segment in segments:
                instruments = await self.download_fyers_instruments(segment, use_json=True)
                all_instruments.extend(instruments)
            
            stats.total_instruments = len(all_instruments)
            
            if not all_instruments:
                logger.warning("No Fyers instruments downloaded")
                return stats
            
            # Process instruments
            for inst in all_instruments:
                try:
                    await self._sync_fyers_instrument(session, inst)
                    
                    if inst.is_equity:
                        stats.equities_added += 1
                    elif inst.is_index:
                        stats.indices_added += 1
                    elif inst.is_future:
                        stats.futures_added += 1
                    elif inst.is_option:
                        stats.options_added += 1
                        
                except Exception as e:
                    stats.errors += 1
                    logger.debug(f"Error syncing Fyers instrument: {e}")
            
            await session.commit()
        
        stats.duration_seconds = (datetime.now() - start_time).total_seconds()
        logger.info(f"Fyers sync completed in {stats.duration_seconds:.1f}s")
        
        return stats
    
    async def _sync_fyers_instrument(
        self,
        session: AsyncSession,
        inst: FyersInstrument,
    ) -> None:
        """Sync a single Fyers instrument."""
        trading_symbol = inst.symbol_ticker
        if not trading_symbol:
            return
        
        # Determine exchange and segment
        exchange = inst.exchange_name
        
        # Check if instrument exists
        stmt = select(InstrumentMaster).where(
            InstrumentMaster.trading_symbol == trading_symbol,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # Just add/update Fyers mapping
            mapping_stmt = select(BrokerSymbolMapping).where(
                BrokerSymbolMapping.instrument_id == existing.instrument_id,
                BrokerSymbolMapping.broker_name == BrokerName.FYERS.value,
            )
            mapping_result = await session.execute(mapping_stmt)
            existing_mapping = mapping_result.scalar_one_or_none()
            
            if not existing_mapping:
                mapping = BrokerSymbolMapping(
                    instrument_id=existing.instrument_id,
                    broker_name=BrokerName.FYERS.value,
                    broker_symbol=trading_symbol,
                    broker_token=inst.fytoken,
                    exchange_code=f"{exchange}_{inst.segment_name}",
                    is_active=True,
                )
                session.add(mapping)
        else:
            # Determine instrument type
            if inst.is_index:
                instr_type = InstrumentType.INDEX.value
                segment = "INDEX"
            elif inst.is_future:
                instr_type = InstrumentType.FUTURE.value
                segment = "FO"
            elif inst.is_option:
                instr_type = InstrumentType.OPTION.value
                segment = "FO"
            else:
                instr_type = InstrumentType.EQUITY.value
                segment = "EQ"
            
            # Create new instrument
            instrument = InstrumentMaster(
                trading_symbol=trading_symbol,
                exchange=exchange,
                segment=segment,
                instrument_type=instr_type,
                underlying=inst.underlying_symbol,
                isin=inst.isin,
                lot_size=inst.lot_size,
                tick_size=Decimal(str(inst.tick_size)),
                is_active=True,
            )
            session.add(instrument)
            await session.flush()
            
            # Create Fyers mapping
            mapping = BrokerSymbolMapping(
                instrument_id=instrument.instrument_id,
                broker_name=BrokerName.FYERS.value,
                broker_symbol=trading_symbol,
                broker_token=inst.fytoken,
                exchange_code=f"{exchange}_{inst.segment_name}",
                is_active=True,
            )
            session.add(mapping)
    
    # =========================================================================
    # Lookup Methods
    # =========================================================================
    
    async def get_fno_stocks(
        self,
        session: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """
        Get all F&O eligible stocks.
        
        Returns:
            List of F&O stock details
        """
        stmt = (
            select(InstrumentMaster)
            .join(EquityMaster, EquityMaster.instrument_id == InstrumentMaster.instrument_id)
            .where(
                EquityMaster.is_fno == True,
                InstrumentMaster.is_active == True,
            )
        )
        result = await session.execute(stmt)
        instruments = result.scalars().all()
        
        return [
            {
                "symbol": inst.trading_symbol,
                "exchange": inst.exchange,
                "lot_size": inst.lot_size,
            }
            for inst in instruments
        ]
    
    async def get_broker_symbol(
        self,
        session: AsyncSession,
        trading_symbol: str,
        broker: str,
    ) -> Optional[str]:
        """
        Get broker-specific symbol for a trading symbol.
        
        Args:
            session: Database session
            trading_symbol: Internal trading symbol
            broker: Broker name (UPSTOX, FYERS)
            
        Returns:
            Broker-specific symbol or None
        """
        stmt = (
            select(BrokerSymbolMapping.broker_symbol)
            .join(InstrumentMaster)
            .where(
                InstrumentMaster.trading_symbol == trading_symbol,
                BrokerSymbolMapping.broker_name == broker,
                BrokerSymbolMapping.is_active == True,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_upstox_instrument_key(
        self,
        session: AsyncSession,
        trading_symbol: str,
    ) -> Optional[str]:
        """Get Upstox instrument_key for a trading symbol."""
        stmt = (
            select(BrokerSymbolMapping)
            .join(InstrumentMaster)
            .where(
                InstrumentMaster.trading_symbol == trading_symbol,
                BrokerSymbolMapping.broker_name == BrokerName.UPSTOX.value,
                BrokerSymbolMapping.is_active == True,
            )
        )
        result = await session.execute(stmt)
        mapping = result.scalar_one_or_none()
        
        if mapping:
            # Construct instrument_key: {segment}|{broker_token or ISIN}
            return f"{mapping.exchange_code}|{mapping.broker_token}"
        return None
    
    async def get_active_expiries(
        self,
        session: AsyncSession,
        underlying: str,
        option_type: Optional[str] = None,
    ) -> List[date]:
        """
        Get active expiries for an underlying.
        
        Args:
            session: Database session
            underlying: Underlying symbol (e.g., "NIFTY", "BANKNIFTY")
            option_type: Optional filter for CE or PE
            
        Returns:
            List of expiry dates
        """
        today = date.today()
        
        stmt = (
            select(OptionMaster.expiry_date)
            .join(InstrumentMaster)
            .where(
                InstrumentMaster.underlying == underlying,
                OptionMaster.expiry_date >= today,
                InstrumentMaster.is_active == True,
            )
        )
        
        if option_type:
            stmt = stmt.where(OptionMaster.option_type == option_type)
        
        stmt = stmt.distinct().order_by(OptionMaster.expiry_date)
        
        result = await session.execute(stmt)
        return [row[0] for row in result.fetchall()]


# =============================================================================
# Factory Function
# =============================================================================

async def create_instrument_sync_service() -> InstrumentSyncService:
    """Create instrument sync service instance."""
    return InstrumentSyncService()


__all__ = [
    "BrokerName",
    "Exchange",
    "InstrumentType",
    "UpstoxInstrument",
    "FyersInstrument",
    "SyncStats",
    "InstrumentSyncService",
    "create_instrument_sync_service",
    "UPSTOX_INSTRUMENT_URLS",
    "FYERS_SYMBOL_URLS",
    "FYERS_JSON_URLS",
]
