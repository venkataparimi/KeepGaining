"""
Data Download Service

Unified service for downloading and managing historical market data.
Uses broker-agnostic data provider interface.

Features:
- Downloads F&O stocks and indices data
- Stores in PostgreSQL with proper schema
- Supports resumable downloads
- Tracks progress and logs
"""

import asyncio
import gzip
import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.db.models import (
    InstrumentMaster, EquityMaster, SectorMaster, 
    CandleData, BrokerSymbolMapping, IndexConstituents,
    MasterDataRefreshLog
)
from app.services.data_providers.base import (
    BaseDataProvider, Interval, Exchange, Instrument as ProviderInstrument
)
from app.services.data_providers.upstox import create_upstox_provider

logger = logging.getLogger(__name__)


# =============================================================================
# Sector and Index Mappings for NSE F&O Stocks
# =============================================================================

# Sector mappings for NSE F&O stocks
SECTOR_MAPPINGS = {
    "BANKING": [
        "HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN", "AXISBANK", "INDUSINDBK",
        "BANKBARODA", "PNB", "AUBANK", "IDFCFIRSTB", "FEDERALBNK", "BANDHANBNK",
        "RBLBANK", "CANBK", "BANKINDIA", "INDIANB", "UNIONBANK", "CENTRALBK", "IOB"
    ],
    "IT": [
        "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "MPHASIS", "COFORGE",
        "PERSISTENT", "LTTS", "TATAELXSI"
    ],
    "AUTO": [
        "TMCV", "M&M", "MARUTI", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT",
        "TVSMOTOR", "ASHOKLEY", "ESCORTS", "BALKRISIND", "MRF", "APOLLOTYRE",
        "BHARATFORG", "MOTHERSON", "EXIDEIND", "BOSCHLTD"
    ],
    "PHARMA": [
        "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "AUROPHARMA",
        "LUPIN", "TORNTPHARM", "ALKEM", "GLENMARK", "BIOCON", "IPCALAB", "LALPATHLAB",
        "METROPOLIS", "NATCOPHARM", "LAURUSLABS", "GRANULES"
    ],
    "FMCG": [
        "HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "GODREJCP",
        "MARICO", "COLPAL", "TATACONSUM", "UBL", "VBL", "PGHH", "EMAMILTD"
    ],
    "METALS": [
        "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "COALINDIA", "NMDC", "SAIL",
        "JINDALSTEL", "NATIONALUM", "HINDZINC", "APLAPOLLO", "RATNAMANI"
    ],
    "OIL_GAS": [
        "RELIANCE", "ONGC", "IOC", "BPCL", "GAIL", "PETRONET", "HINDPETRO",
        "CASTROLIND", "GUJGASLTD", "MGL", "IGL", "ATGL", "OIL", "MRPL"
    ],
    "POWER": [
        "NTPC", "POWERGRID", "TATAPOWER", "ADANIPOWER", "ADANIGREEN", "TORNTPOWER",
        "NHPC", "SJVN", "CESC", "JSWENERGY", "RECLTD", "PFC", "IREDA"
    ],
    "REALTY": [
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "BRIGADE", "PHOENIXLTD",
        "SOBHA"
    ],
    "CEMENT": [
        "ULTRACEMCO", "SHREECEM", "AMBUJACEM", "ACC", "DALBHARAT", "JKCEMENT",
        "RAMCOCEM", "JKLAKSHMI", "INDIACEM"
    ],
    "INFRASTRUCTURE": [
        "LT", "ADANIENT", "ADANIPORTS", "CONCOR", "IRB", "KEC", "GMRAIRPORT",
        "WELCORP", "ENGINERSIN", "HCC", "NBCC", "NCC"
    ],
    "TELECOM": [
        "BHARTIARTL", "IDEA"
    ],
    "FINANCE": [
        "BAJFINANCE", "BAJAJFINSV", "HDFCLIFE", "SBILIFE", "ICICIPRULI", "ICICIGI",
        "HDFCAMC", "SBICARD", "MUTHOOTFIN", "CHOLAFIN", "M&MFIN", "SHRIRAMFIN",
        "MANAPPURAM", "POONAWALLA", "LICHSGFIN", "CANFINHOME", "ABCAPITAL"
    ],
    "CHEMICALS": [
        "PIDILITIND", "SRF", "AARTIIND", "DEEPAKNTR", "NAVINFLUOR", "CLEAN",
        "ATUL", "FLUOROCHEM", "GNFC"
    ],
    "CONSUMER": [
        "TITAN", "PAGEIND", "ASIANPAINT", "BERGEPAINT", "HAVELLS", "VOLTAS",
        "CROMPTON", "WHIRLPOOL", "BATAINDIA", "RELAXO", "TRENT", "ETERNAL"
    ],
    "CAPITAL_GOODS": [
        "SIEMENS", "ABB", "BHEL", "CUMMINSIND", "THERMAX", "CGPOWER", "POLYCAB"
    ],
    "MEDIA": [
        "ZEEL", "PVRINOX"
    ],
    "LOGISTICS": [
        "DELHIVERY"
    ]
}

# Index constituents (major indices)
INDEX_MAPPINGS = {
    "NIFTY50": [
        "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
        "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BHARTIARTL", "BPCL",
        "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY", "EICHERMOT",
        "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
        "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "ITC", "JSWSTEEL",
        "KOTAKBANK", "LT", "M&M", "MARUTI", "NESTLEIND", "NTPC",
        "ONGC", "POWERGRID", "RELIANCE", "SBIN", "SHRIRAMFIN", "SUNPHARMA",
        "TATACONSUM", "TMCV", "TATASTEEL", "TCS", "TECHM", "TITAN",
        "ULTRACEMCO", "WIPRO"
    ],
    "BANKNIFTY": [
        "HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN", "AXISBANK", "INDUSINDBK",
        "BANKBARODA", "PNB", "FEDERALBNK", "IDFCFIRSTB", "AUBANK", "BANDHANBNK"
    ],
    "NIFTYIT": [
        "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "MPHASIS", 
        "COFORGE", "PERSISTENT", "LTTS"
    ],
    "NIFTYPHARMA": [
        "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "AUROPHARMA", "LUPIN",
        "TORNTPHARM", "ALKEM", "BIOCON", "GLENMARK"
    ],
    "NIFTYPSE": [
        "NTPC", "POWERGRID", "ONGC", "COALINDIA", "IOC", "BPCL", "GAIL",
        "RECLTD", "PFC", "NHPC"
    ],
    "NIFTYMETAL": [
        "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "COALINDIA", "NMDC",
        "SAIL", "JINDALSTEL", "NATIONALUM", "APLAPOLLO"
    ],
    "NIFTYAUTO": [
        "TMCV", "M&M", "MARUTI", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT",
        "TVSMOTOR", "ASHOKLEY", "ESCORTS", "MRF"
    ],
    "NIFTYFMCG": [
        "HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "GODREJCP",
        "MARICO", "COLPAL", "TATACONSUM", "UBL"
    ],
    "NIFTYFIN": [
        "HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN", "AXISBANK", "BAJFINANCE",
        "BAJAJFINSV", "HDFCLIFE", "SBILIFE", "ICICIPRULI"
    ]
}


class DataDownloadService:
    """
    Unified service for downloading and storing market data.
    """
    
    def __init__(
        self, 
        data_provider: BaseDataProvider,
        db_url: str = "postgresql+asyncpg://user:password@localhost:5432/keepgaining"
    ):
        self.provider = data_provider
        self.engine = create_async_engine(db_url, echo=False)
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
    
    async def initialize(self):
        """Initialize database connection and authenticate provider."""
        await self.provider.authenticate()
        logger.info(f"Initialized with provider: {self.provider.name}")
    
    async def close(self):
        """Cleanup resources."""
        await self.provider.close()
        await self.engine.dispose()
    
    # =========================================================================
    # Master Data Management
    # =========================================================================
    
    async def sync_fo_stocks_to_db(self) -> int:
        """
        Sync F&O stocks from provider to database with sector/index mappings.
        
        Returns:
            Number of stocks synced
        """
        logger.info("Syncing F&O stocks to database...")
        
        # Try getting from provider first, fallback to our static list
        try:
            fo_stocks = await self.provider.get_fo_stocks()
            logger.info(f"Found {len(fo_stocks)} F&O stocks from provider")
        except Exception as e:
            logger.warning(f"Failed to get F&O stocks from provider: {e}")
            # Fallback to our static list from sector mappings
            fo_stocks = self._get_all_fo_stocks_from_mappings()
            logger.info(f"Using static list: {len(fo_stocks)} F&O stocks")
        
        if not fo_stocks:
            fo_stocks = self._get_all_fo_stocks_from_mappings()
            logger.info(f"Using static list: {len(fo_stocks)} F&O stocks")
        
        async with self.async_session() as session:
            # Now create/update instruments
            synced_count = 0
            for symbol in fo_stocks:
                # Find sector for this stock
                sector_name = self._get_sector_for_stock(symbol)
                
                # Find indices for this stock
                indices = self._get_indices_for_stock(symbol)
                
                # Upsert instrument
                await self._upsert_fo_instrument(
                    session, symbol, sector_name, indices
                )
                synced_count += 1
            
            await session.commit()
            
            # Log refresh
            await self._log_refresh(
                session, "FO_STOCKS", synced_count, 0, synced_count, self.provider.name
            )
            await session.commit()
        
        logger.info(f"Synced {synced_count} F&O stocks to database")
        return synced_count
    
    async def _upsert_fo_instrument(
        self,
        session: AsyncSession,
        symbol: str,
        sector_name: Optional[str],
        indices: List[str]
    ):
        """Insert or update F&O enabled instrument."""
        # Check if exists
        result = await session.execute(
            select(InstrumentMaster).where(InstrumentMaster.trading_symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            instrument = InstrumentMaster(
                trading_symbol=symbol,
                exchange="NSE",
                segment="EQ",
                instrument_type="EQUITY",
                lot_size=1,
                is_active=True
            )
            session.add(instrument)
            await session.flush()
            
            # Create equity details with sector
            equity = EquityMaster(
                instrument_id=instrument.instrument_id,
                company_name=symbol,
                sector=sector_name,
                is_fno=True,
                is_index_constituent=len(indices) > 0
            )
            session.add(equity)
        else:
            # Update existing - update equity details
            result = await session.execute(
                select(EquityMaster).where(
                    EquityMaster.instrument_id == instrument.instrument_id
                )
            )
            equity = result.scalar_one_or_none()
            
            if equity:
                equity.sector = sector_name
                equity.is_fno = True
                equity.is_index_constituent = len(indices) > 0
            else:
                equity = EquityMaster(
                    instrument_id=instrument.instrument_id,
                    company_name=symbol,
                    sector=sector_name,
                    is_fno=True,
                    is_index_constituent=len(indices) > 0
                )
                session.add(equity)
        
        # Add broker symbol mapping
        await self._add_broker_mapping(
            session, instrument.instrument_id, symbol
        )
    
    async def _add_broker_mapping(
        self,
        session: AsyncSession,
        instrument_id: UUID,
        symbol: str
    ):
        """Add broker symbol mapping for instrument."""
        broker_symbol = f"NSE_EQ|{symbol}"
        
        result = await session.execute(
            select(BrokerSymbolMapping).where(
                BrokerSymbolMapping.instrument_id == instrument_id,
                BrokerSymbolMapping.broker_name == self.provider.name
            )
        )
        mapping = result.scalar_one_or_none()
        
        if not mapping:
            mapping = BrokerSymbolMapping(
                instrument_id=instrument_id,
                broker_name=self.provider.name,
                broker_symbol=broker_symbol,
                broker_token=broker_symbol,
                exchange_code="NSE_EQ"
            )
            session.add(mapping)
    
    def _get_sector_for_stock(self, symbol: str) -> Optional[str]:
        """Get sector name for a stock symbol."""
        for sector_name, stocks in SECTOR_MAPPINGS.items():
            if symbol in stocks:
                return sector_name
        return None
    
    def _get_indices_for_stock(self, symbol: str) -> List[str]:
        """Get list of indices that include this stock."""
        indices = []
        for index_name, constituents in INDEX_MAPPINGS.items():
            if symbol in constituents:
                indices.append(index_name)
        return indices
    
    def _get_all_fo_stocks_from_mappings(self) -> List[str]:
        """Get all F&O stocks from our static sector mappings."""
        all_stocks = set()
        for stocks in SECTOR_MAPPINGS.values():
            all_stocks.update(stocks)
        return sorted(list(all_stocks))
    
    # =========================================================================
    # Historical Data Download
    # =========================================================================
    
    async def build_instrument_key_cache(self) -> Dict[str, str]:
        """
        Build symbol to instrument_key mapping from Upstox instrument master.
        
        Returns:
            Dict mapping symbol (e.g., 'RELIANCE') to instrument_key (e.g., 'NSE_EQ|INE002A01018')
        """
        import aiohttp
        import gzip
        import io
        import json
        
        cache = {}
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                            data = json.loads(f.read().decode('utf-8'))
                        
                        for item in data:
                            symbol = item.get('trading_symbol', '')
                            key = item.get('instrument_key', '')
                            if symbol and key and item.get('instrument_type') == 'EQ':
                                cache[symbol] = key
                        
                        logger.info(f"Built instrument key cache with {len(cache)} symbols")
        except Exception as e:
            logger.error(f"Failed to build instrument key cache: {e}")
        
        return cache
    
    async def download_historical_data(
        self,
        symbols: Optional[List[str]] = None,
        from_date: date = None,
        to_date: date = None,
        interval: Interval = Interval.MINUTE_1,
        force_redownload: bool = False
    ) -> Dict[str, Any]:
        """
        Download historical candle data for instruments.
        
        Args:
            symbols: List of symbols to download. If None, downloads all F&O stocks.
            from_date: Start date. Defaults to data provider's earliest date.
            to_date: End date. Defaults to today.
            interval: Candle interval.
            force_redownload: If True, redownloads even if data exists.
            
        Returns:
            Summary of download results.
        """
        # Get data availability limits
        availability = self.provider.get_data_availability(interval)
        
        # Set defaults
        if from_date is None:
            from_date = availability.get("start_date", date(2022, 1, 1))
        if to_date is None:
            to_date = date.today()
        
        # Get symbols to download - use our static list if not provided
        if symbols is None:
            # Try provider first, fallback to static list
            try:
                symbols = await self.provider.get_fo_stocks()
            except:
                pass
            
            if not symbols:
                symbols = self._get_all_fo_stocks_from_mappings()
                logger.info(f"Using static F&O list with {len(symbols)} symbols")
        
        logger.info(f"Starting download for {len(symbols)} symbols from {from_date} to {to_date}")
        
        # Build instrument key cache
        key_cache = await self.build_instrument_key_cache()
        
        results = {
            "total_symbols": len(symbols),
            "successful": 0,
            "failed": 0,
            "total_candles": 0,
            "errors": []
        }
        
        for i, symbol in enumerate(symbols):
            # Use separate session per stock to avoid memory buildup
            async with self.async_session() as session:
                try:
                    logger.info(f"[{i+1}/{len(symbols)}] Downloading {symbol}...")
                    
                    # Get or create instrument
                    instrument_id = await self._get_or_create_instrument(session, symbol)
                    await session.commit()
                    
                    # Get last timestamp if not force redownload
                    actual_from = from_date
                    if not force_redownload:
                        last_ts = await self._get_last_candle_timestamp(
                            session, instrument_id, interval
                        )
                        if last_ts:
                            actual_from = max(from_date, last_ts.date() + timedelta(days=1))
                    
                    if actual_from >= to_date:
                        logger.info(f"  {symbol}: Already up to date")
                        results["successful"] += 1
                        continue
                    
                    # Get proper instrument key from cache
                    instrument_key = key_cache.get(symbol)
                    if not instrument_key:
                        logger.warning(f"  {symbol}: Not found in instrument master")
                        results["failed"] += 1
                        results["errors"].append({"symbol": symbol, "error": "Not found in instrument master"})
                        continue
                    
                    # Create provider instrument object with correct key
                    provider_instrument = ProviderInstrument(
                        symbol=symbol,
                        name=symbol,
                        instrument_type="EQUITY",
                        exchange=Exchange.NSE,
                        provider_token=instrument_key
                    )
                    
                    # Download candles
                    candles = await self.provider.get_historical_candles(
                        provider_instrument, interval, actual_from, to_date
                    )
                    
                    if candles:
                        # Store in database with small batches
                        stored = await self._store_candles(session, instrument_id, candles)
                        results["total_candles"] += stored
                        logger.info(f"  {symbol}: Stored {stored:,} candles")
                        
                        # Clear candles from memory
                        del candles
                    else:
                        logger.warning(f"  {symbol}: No candles returned")
                    
                    results["successful"] += 1
                    
                except Exception as e:
                    logger.error(f"  {symbol}: Error - {e}")
                    results["failed"] += 1
                    results["errors"].append({"symbol": symbol, "error": str(e)})
                    # Continue with next stock
                    continue
            
            # Force garbage collection after each stock
            import gc
            gc.collect()
        
        logger.info(f"Download complete: {results['successful']}/{results['total_symbols']} successful, "
                   f"{results['total_candles']:,} total candles")
        
        return results
    
    # Index instrument keys for Upstox (NSE + BSE indices with F&O)
    INDEX_KEYS = {
        # NSE Indices
        "NIFTY 50": "NSE_INDEX|Nifty 50",
        "NIFTY BANK": "NSE_INDEX|Nifty Bank",
        "NIFTY IT": "NSE_INDEX|Nifty IT",
        "NIFTY FIN SERVICE": "NSE_INDEX|Nifty Fin Service",
        "NIFTY MIDCAP SELECT": "NSE_INDEX|Nifty Midcap Select",
        "NIFTY MIDCAP 50": "NSE_INDEX|Nifty Midcap 50",
        "NIFTY NEXT 50": "NSE_INDEX|Nifty Next 50",
        "NIFTY AUTO": "NSE_INDEX|Nifty Auto",
        "NIFTY PHARMA": "NSE_INDEX|Nifty Pharma",
        "NIFTY METAL": "NSE_INDEX|Nifty Metal",
        "NIFTY REALTY": "NSE_INDEX|Nifty Realty",
        "NIFTY ENERGY": "NSE_INDEX|Nifty Energy",
        "NIFTY FMCG": "NSE_INDEX|Nifty FMCG",
        "NIFTY PSE": "NSE_INDEX|Nifty PSE",
        "NIFTY INFRA": "NSE_INDEX|Nifty Infra",
        "INDIA VIX": "NSE_INDEX|India VIX",
        # BSE Indices  
        "SENSEX": "BSE_INDEX|SENSEX",
        "BANKEX": "BSE_INDEX|BANKEX",
        "SENSEX 50": "BSE_INDEX|BSE SENSEX 50",
    }
    
    # Underlying instrument keys for F&O derivatives
    FO_UNDERLYING_KEYS = {
        # Index F&O
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank",
        "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
        "MIDCPNIFTY": "NSE_INDEX|Nifty Midcap Select",
        "SENSEX": "BSE_INDEX|SENSEX",
        "BANKEX": "BSE_INDEX|BANKEX",
    }
    
    async def download_index_data(
        self,
        indices: Optional[List[str]] = None,
        from_date: date = None,
        to_date: date = None,
        interval: Interval = Interval.MINUTE_1,
        force_redownload: bool = False
    ) -> Dict[str, Any]:
        """
        Download historical data for indices.
        
        Args:
            indices: List of index names (e.g., ["NIFTY 50", "NIFTY BANK"]).
                    If None, downloads all major indices.
            from_date: Start date.
            to_date: End date.
            interval: Candle interval.
            force_redownload: If True, redownloads even if data exists.
        """
        availability = self.provider.get_data_availability(interval)
        
        if from_date is None:
            from_date = availability.get("start_date", date(2022, 1, 1))
        if to_date is None:
            to_date = date.today()
        
        if indices is None:
            indices = list(self.INDEX_KEYS.keys())
        
        logger.info(f"Downloading {len(indices)} indices from {from_date} to {to_date}")
        
        results = {
            "total_indices": len(indices),
            "successful": 0,
            "failed": 0,
            "total_candles": 0,
            "errors": []
        }
        
        for i, index_name in enumerate(indices):
            async with self.async_session() as session:
                try:
                    logger.info(f"[{i+1}/{len(indices)}] Downloading {index_name}...")
                    
                    instrument_key = self.INDEX_KEYS.get(index_name)
                    if not instrument_key:
                        logger.warning(f"  {index_name}: Unknown index")
                        results["failed"] += 1
                        results["errors"].append({"symbol": index_name, "error": "Unknown index"})
                        continue
                    
                    # Get or create index instrument
                    instrument_id = await self._get_or_create_index_instrument(session, index_name)
                    await session.commit()
                    
                    # Check last timestamp
                    actual_from = from_date
                    if not force_redownload:
                        last_ts = await self._get_last_candle_timestamp(session, instrument_id, interval)
                        if last_ts:
                            actual_from = max(from_date, last_ts.date() + timedelta(days=1))
                    
                    if actual_from >= to_date:
                        logger.info(f"  {index_name}: Already up to date")
                        results["successful"] += 1
                        continue
                    
                    # Create provider instrument
                    provider_instrument = ProviderInstrument(
                        symbol=index_name,
                        name=index_name,
                        instrument_type="INDEX",
                        exchange=Exchange.NSE,
                        provider_token=instrument_key
                    )
                    
                    # Download candles
                    candles = await self.provider.get_historical_candles(
                        provider_instrument, interval, actual_from, to_date
                    )
                    
                    if candles:
                        stored = await self._store_candles(session, instrument_id, candles)
                        results["total_candles"] += stored
                        logger.info(f"  {index_name}: Stored {stored:,} candles")
                        del candles
                    else:
                        logger.warning(f"  {index_name}: No candles returned")
                    
                    results["successful"] += 1
                    
                except Exception as e:
                    logger.error(f"  {index_name}: Error - {e}")
                    results["failed"] += 1
                    results["errors"].append({"symbol": index_name, "error": str(e)})
                    continue
            
            import gc
            gc.collect()
        
        logger.info(f"Index download complete: {results['successful']}/{results['total_indices']} successful")
        return results
    
    async def _get_or_create_index_instrument(self, session: AsyncSession, index_name: str) -> UUID:
        """Get or create index instrument, return instrument_id."""
        result = await session.execute(
            select(InstrumentMaster).where(InstrumentMaster.trading_symbol == index_name)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            instrument = InstrumentMaster(
                trading_symbol=index_name,
                exchange="NSE",
                segment="INDEX",
                instrument_type="INDEX",
                is_active=True
            )
            session.add(instrument)
            await session.flush()
        
        return instrument.instrument_id

    async def get_fo_instruments_from_upstox(self) -> Dict[str, List[Dict]]:
        """
        Fetch F&O instruments from Upstox instrument master.
        Returns dict with 'futures' and 'options' lists.
        """
        import aiohttp
        import gzip
        
        url = 'https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz'
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to fetch instruments: {resp.status}")
                
                data = gzip.decompress(await resp.read())
                instruments = json.loads(data)
                
                # Filter NSE_FO
                fo = [i for i in instruments if i.get('segment') == 'NSE_FO']
                
                futures = [i for i in fo if i.get('instrument_type') == 'FUT']
                options = [i for i in fo if i.get('instrument_type') in ('CE', 'PE')]
                
                logger.info(f"Fetched {len(futures)} futures and {len(options)} options from Upstox")
                return {'futures': futures, 'options': options}

    async def download_futures_data(
        self,
        underlyings: Optional[List[str]] = None,
        expiries: Optional[List[str]] = None,  # 'current', 'next', 'far' or specific dates
        from_date: date = None,
        to_date: date = None,
        interval: Interval = Interval.MINUTE_1,
        force_redownload: bool = False
    ) -> Dict[str, Any]:
        """
        Download historical data for futures contracts.
        
        Args:
            underlyings: List of underlying symbols (e.g., ['NIFTY', 'BANKNIFTY', 'RELIANCE']).
                        If None, downloads for NIFTY and BANKNIFTY only.
            expiries: List of expiry types ('current', 'next', 'far') or None for all available.
            from_date: Start date.
            to_date: End date.
            interval: Candle interval.
            force_redownload: If True, redownloads even if data exists.
        """
        from datetime import datetime as dt
        
        availability = self.provider.get_data_availability(interval)
        
        if from_date is None:
            from_date = availability.get("start_date", date(2022, 1, 1))
        if to_date is None:
            to_date = date.today()
        
        # Default to index futures
        if underlyings is None:
            underlyings = ['NIFTY', 'BANKNIFTY', 'FINNIFTY']
        
        # Fetch F&O instruments
        fo_data = await self.get_fo_instruments_from_upstox()
        all_futures = fo_data['futures']
        
        # Filter by underlying
        futures_to_download = []
        for fut in all_futures:
            underlying = fut.get('underlying_symbol')
            if underlying in underlyings:
                expiry_ts = fut.get('expiry', 0) / 1000
                expiry_date = dt.fromtimestamp(expiry_ts)
                
                # Filter by expiry if specified
                if expiries:
                    # Sort futures by expiry to determine current/next/far
                    pass  # Download all for now
                
                futures_to_download.append({
                    'symbol': fut.get('trading_symbol'),
                    'instrument_key': fut.get('instrument_key'),
                    'underlying': underlying,
                    'expiry': expiry_date,
                    'lot_size': fut.get('lot_size', 1)
                })
        
        logger.info(f"Downloading {len(futures_to_download)} futures contracts from {from_date} to {to_date}")
        
        results = {
            "total_contracts": len(futures_to_download),
            "successful": 0,
            "failed": 0,
            "total_candles": 0,
            "errors": []
        }
        
        for i, fut in enumerate(futures_to_download):
            async with self.async_session() as session:
                try:
                    symbol = fut['symbol']
                    logger.info(f"[{i+1}/{len(futures_to_download)}] Downloading {symbol}...")
                    
                    # Get or create instrument
                    instrument_id = await self._get_or_create_futures_instrument(
                        session, fut['symbol'], fut['underlying'], fut['expiry'], fut['lot_size']
                    )
                    await session.commit()
                    
                    # Check last timestamp
                    actual_from = from_date
                    if not force_redownload:
                        last_ts = await self._get_last_candle_timestamp(session, instrument_id, interval)
                        if last_ts:
                            actual_from = max(from_date, last_ts.date() + timedelta(days=1))
                    
                    if actual_from >= to_date:
                        logger.info(f"  {symbol}: Already up to date")
                        results["successful"] += 1
                        continue
                    
                    # Create provider instrument
                    provider_instrument = ProviderInstrument(
                        symbol=symbol,
                        name=symbol,
                        instrument_type="FUTURES",
                        exchange=Exchange.NFO,
                        provider_token=fut['instrument_key']
                    )
                    
                    # Download candles
                    candles = await self.provider.get_historical_candles(
                        provider_instrument, interval, actual_from, to_date
                    )
                    
                    if candles:
                        stored = await self._store_candles(session, instrument_id, candles)
                        results["total_candles"] += stored
                        logger.info(f"  {symbol}: Stored {stored:,} candles")
                        del candles
                    else:
                        logger.warning(f"  {symbol}: No candles returned")
                    
                    results["successful"] += 1
                    
                except Exception as e:
                    logger.error(f"  {fut['symbol']}: Error - {e}")
                    results["failed"] += 1
                    results["errors"].append({"symbol": fut['symbol'], "error": str(e)})
                    continue
            
            import gc
            gc.collect()
        
        logger.info(f"Futures download complete: {results['successful']}/{results['total_contracts']} successful")
        return results
    
    async def _get_or_create_futures_instrument(
        self, session: AsyncSession, symbol: str, underlying: str, expiry: datetime, lot_size: int
    ) -> UUID:
        """Get or create futures instrument."""
        result = await session.execute(
            select(InstrumentMaster).where(InstrumentMaster.trading_symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            instrument = InstrumentMaster(
                trading_symbol=symbol,
                exchange="NSE",
                segment="FO",
                instrument_type="FUTURES",
                underlying=underlying,
                lot_size=lot_size,
                is_active=True
            )
            session.add(instrument)
            await session.flush()
        
        return instrument.instrument_id

    async def download_options_data(
        self,
        underlyings: Optional[List[str]] = None,
        strike_range: int = 10,  # Number of strikes above/below ATM
        from_date: date = None,
        to_date: date = None,
        interval: Interval = Interval.MINUTE_1,
        force_redownload: bool = False
    ) -> Dict[str, Any]:
        """
        Download historical data for options contracts.
        
        Args:
            underlyings: List of underlying symbols (e.g., ['NIFTY', 'BANKNIFTY']).
            strike_range: Number of strikes above/below ATM to download.
            from_date: Start date.
            to_date: End date.
            interval: Candle interval.
            force_redownload: If True, redownloads even if data exists.
        """
        from datetime import datetime as dt
        
        availability = self.provider.get_data_availability(interval)
        
        if from_date is None:
            from_date = availability.get("start_date", date(2022, 1, 1))
        if to_date is None:
            to_date = date.today()
        
        # Default to index options only (stock options are too many)
        if underlyings is None:
            underlyings = ['NIFTY', 'BANKNIFTY']
        
        # Fetch F&O instruments
        fo_data = await self.get_fo_instruments_from_upstox()
        all_options = fo_data['options']
        
        # Filter options by underlying
        options_to_download = []
        for opt in all_options:
            underlying = opt.get('underlying_symbol')
            if underlying in underlyings:
                expiry_ts = opt.get('expiry', 0) / 1000
                expiry_date = dt.fromtimestamp(expiry_ts)
                
                options_to_download.append({
                    'symbol': opt.get('trading_symbol'),
                    'instrument_key': opt.get('instrument_key'),
                    'underlying': underlying,
                    'expiry': expiry_date,
                    'strike': opt.get('strike_price'),
                    'option_type': opt.get('instrument_type'),  # CE or PE
                    'lot_size': opt.get('lot_size', 1)
                })
        
        logger.info(f"Downloading {len(options_to_download)} options contracts from {from_date} to {to_date}")
        
        results = {
            "total_contracts": len(options_to_download),
            "successful": 0,
            "failed": 0,
            "total_candles": 0,
            "errors": []
        }
        
        for i, opt in enumerate(options_to_download):
            async with self.async_session() as session:
                try:
                    symbol = opt['symbol']
                    if i % 100 == 0:
                        logger.info(f"[{i+1}/{len(options_to_download)}] Downloading {symbol}...")
                    
                    # Get or create instrument
                    instrument_id = await self._get_or_create_options_instrument(
                        session, opt['symbol'], opt['underlying'], opt['expiry'], 
                        opt['strike'], opt['option_type'], opt['lot_size']
                    )
                    await session.commit()
                    
                    # Check last timestamp
                    actual_from = from_date
                    if not force_redownload:
                        last_ts = await self._get_last_candle_timestamp(session, instrument_id, interval)
                        if last_ts:
                            actual_from = max(from_date, last_ts.date() + timedelta(days=1))
                    
                    if actual_from >= to_date:
                        results["successful"] += 1
                        continue
                    
                    # Create provider instrument
                    provider_instrument = ProviderInstrument(
                        symbol=symbol,
                        name=symbol,
                        instrument_type="OPTIONS",
                        exchange=Exchange.NFO,
                        provider_token=opt['instrument_key']
                    )
                    
                    # Download candles
                    candles = await self.provider.get_historical_candles(
                        provider_instrument, interval, actual_from, to_date
                    )
                    
                    if candles:
                        stored = await self._store_candles(session, instrument_id, candles)
                        results["total_candles"] += stored
                        del candles
                    
                    results["successful"] += 1
                    
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({"symbol": opt['symbol'], "error": str(e)})
                    continue
            
            # GC every 50 options
            if i % 50 == 0:
                import gc
                gc.collect()
        
        logger.info(f"Options download complete: {results['successful']}/{results['total_contracts']} successful, {results['total_candles']:,} candles")
        return results
    
    async def _get_or_create_options_instrument(
        self, session: AsyncSession, symbol: str, underlying: str, expiry: datetime,
        strike: float, option_type: str, lot_size: int
    ) -> UUID:
        """Get or create options instrument."""
        result = await session.execute(
            select(InstrumentMaster).where(InstrumentMaster.trading_symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            instrument = InstrumentMaster(
                trading_symbol=symbol,
                exchange="NSE",
                segment="FO",
                instrument_type=option_type,  # CE or PE
                underlying=underlying,
                lot_size=lot_size,
                is_active=True
            )
            session.add(instrument)
            await session.flush()
        
        return instrument.instrument_id

    # =========================================================================
    # Historical Expired F&O Data Download
    # =========================================================================
    
    async def download_historical_expired_futures(
        self,
        underlyings: Optional[List[str]] = None,
        months_back: int = 6,
        interval: Interval = Interval.MINUTE_1,
    ) -> Dict[str, Any]:
        """
        Download historical data for EXPIRED futures contracts.
        
        Args:
            underlyings: List of underlying symbols. If None, downloads all F&O stocks + indices.
            months_back: How many months of historical expiries to fetch (max 6).
            interval: Candle interval.
        """
        # Build underlying_key mapping from instrument master
        fo_data = await self.get_fo_instruments_from_upstox()
        
        # Create symbol -> underlying_key mapping from F&O instruments
        underlying_key_map = {}
        for f in fo_data['futures']:
            symbol = f.get('underlying_symbol')
            key = f.get('underlying_key')
            if symbol and key and symbol not in underlying_key_map:
                underlying_key_map[symbol] = key
        
        # Add index underlyings (these use different format)
        for symbol, key in self.FO_UNDERLYING_KEYS.items():
            underlying_key_map[symbol] = key
        
        logger.info(f"Built underlying_key mapping for {len(underlying_key_map)} symbols")
        
        # Filter to requested underlyings or use all
        if underlyings is None:
            underlyings = list(underlying_key_map.keys())
        else:
            # Filter to only symbols we have keys for
            underlyings = [u for u in underlyings if u in underlying_key_map]
        
        logger.info(f"Will download expired futures for {len(underlyings)} underlyings")
        
        results = {
            "total_underlyings": len(underlyings),
            "total_expiries": 0,
            "total_contracts": 0,
            "successful": 0,
            "failed": 0,
            "total_candles": 0,
            "errors": []
        }
        
        for ui, underlying in enumerate(underlyings):
            print(f"[{ui+1}/{len(underlyings)}] {underlying}...", end=" ", flush=True)
            
            # Get instrument key for underlying from our mapping
            instrument_key = underlying_key_map.get(underlying)
            if not instrument_key:
                print("SKIP (no key)", flush=True)
                continue
            
            # Get expiries for this underlying
            try:
                expiries = await self.provider.get_expiries(instrument_key)
                if not expiries:
                    print("SKIP (no expiries)", flush=True)
                    continue
                
                results["total_expiries"] += len(expiries)
                underlying_candles = 0
                underlying_contracts = 0
                underlying_skipped = 0
                
                # Collect all contracts from all expiries first
                all_contracts = []
                for expiry_date in expiries:
                    contracts = await self.provider.get_expired_future_contracts(
                        instrument_key, expiry_date
                    )
                    if contracts:
                        for c in contracts:
                            c['_expiry_date'] = expiry_date  # Tag with expiry
                            all_contracts.append(c)
                
                if not all_contracts:
                    print(f"{len(expiries)} exp, 0 contracts", flush=True)
                    continue
                
                # Process contracts in smaller batches with delays to avoid rate limiting
                BATCH_SIZE = 3  # Reduced from 10 to avoid rate limits
                DELAY_BETWEEN_BATCHES = 0.5  # 500ms delay between batches
                
                async def process_futures_contract(contract):
                    """Process a single futures contract - returns (success, skipped, candles, error)"""
                    try:
                        expired_key = contract.get('instrument_key')
                        symbol = contract.get('trading_symbol')
                        lot_size = contract.get('lot_size', 1)
                        expiry_str = contract.get('_expiry_date')
                        
                        exp_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
                        
                        async with self.async_session() as session:
                            instrument_id = await self._get_or_create_futures_instrument(
                                session, symbol, underlying, 
                                datetime.combine(exp_date, datetime.min.time()),
                                lot_size
                            )
                            await session.commit()
                            
                            existing_count = await self._get_candle_count(session, instrument_id)
                            if existing_count > 0:
                                return (True, True, 0, None)
                            
                            from_date = exp_date - timedelta(days=30)
                            to_date = exp_date
                            
                            candles = await self.provider.get_expired_historical_candles(
                                expired_key, interval, from_date, to_date
                            )
                            
                            if candles:
                                stored = await self._store_candles(session, instrument_id, candles)
                                del candles
                                return (True, False, stored, None)
                            return (True, False, 0, None)
                            
                    except Exception as e:
                        return (False, False, 0, str(e))
                
                # Process in batches with delays
                for batch_start in range(0, len(all_contracts), BATCH_SIZE):
                    batch = all_contracts[batch_start:batch_start + BATCH_SIZE]
                    batch_results = await asyncio.gather(*[process_futures_contract(c) for c in batch])
                    
                    # Add delay between batches to avoid rate limiting
                    if batch_start + BATCH_SIZE < len(all_contracts):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                    
                    for (success, skipped, candles, error), contract in zip(batch_results, batch):
                        results["total_contracts"] += 1
                        underlying_contracts += 1
                        
                        if success:
                            results["successful"] += 1
                            if skipped:
                                results["skipped"] = results.get("skipped", 0) + 1
                                underlying_skipped += 1
                            else:
                                results["total_candles"] += candles
                                underlying_candles += candles
                        else:
                            results["failed"] += 1
                            if error:
                                results["errors"].append({"symbol": contract.get('trading_symbol'), "error": error})
                
                print(f"{len(expiries)} exp, {underlying_contracts} contracts, {underlying_candles:,} candles (skipped {underlying_skipped})", flush=True)
                        
            except Exception as e:
                print(f"ERROR: {e}", flush=True)
                results["errors"].append({"underlying": underlying, "error": str(e)})
            
            # GC after each underlying
            import gc
            gc.collect()
        
        logger.info(f"Expired futures download complete: {results['successful']}/{results['total_contracts']} contracts, "
                   f"{results['total_candles']:,} candles")
        return results
    
    async def download_historical_expired_options(
        self,
        underlyings: Optional[List[str]] = None,
        months_back: int = 6,
        interval: Interval = Interval.MINUTE_1,
    ) -> Dict[str, Any]:
        """
        Download historical data for EXPIRED options contracts.
        
        Args:
            underlyings: List of underlying symbols. If None, downloads for major indices only.
            months_back: How many months of historical expiries to fetch (max 6).
            interval: Candle interval.
        """
        # Build underlying_key mapping from instrument master
        fo_data = await self.get_fo_instruments_from_upstox()
        
        # Create symbol -> underlying_key mapping from F&O instruments
        underlying_key_map = {}
        for f in fo_data['options']:
            symbol = f.get('underlying_symbol')
            key = f.get('underlying_key')
            if symbol and key and symbol not in underlying_key_map:
                underlying_key_map[symbol] = key
        
        # Add index underlyings (these use different format)
        for symbol, key in self.FO_UNDERLYING_KEYS.items():
            underlying_key_map[symbol] = key
        
        # Default to index options only (stock options are massive)
        if underlyings is None:
            underlyings = list(self.FO_UNDERLYING_KEYS.keys())
            logger.info(f"Will download expired options for {len(underlyings)} index underlyings")
        else:
            # Filter to only symbols we have keys for
            underlyings = [u for u in underlyings if u in underlying_key_map]
        
        results = {
            "total_underlyings": len(underlyings),
            "total_expiries": 0,
            "total_contracts": 0,
            "successful": 0,
            "failed": 0,
            "total_candles": 0,
            "errors": []
        }
        
        for ui, underlying in enumerate(underlyings):
            print(f"[{ui+1}/{len(underlyings)}] {underlying}...", flush=True)
            
            # Get instrument key for underlying from our mapping
            instrument_key = underlying_key_map.get(underlying)
            if not instrument_key:
                print("  SKIP (no key)", flush=True)
                continue
            
            # Get expiries for this underlying
            try:
                expiries = await self.provider.get_expiries(instrument_key)
                if not expiries:
                    print("  SKIP (no expiries)", flush=True)
                    continue
                
                results["total_expiries"] += len(expiries)
                underlying_candles = 0
                underlying_contracts = 0
                underlying_skipped = 0
                
                # Process each expiry
                for ei, expiry_date in enumerate(expiries):
                    print(f"  Expiry {ei+1}/{len(expiries)}: {expiry_date}...", end=" ", flush=True)
                    
                    # Get expired option contracts for this expiry
                    contracts = await self.provider.get_expired_option_contracts(
                        instrument_key, expiry_date
                    )
                    
                    if not contracts:
                        print("0 contracts", flush=True)
                        continue
                    
                    expiry_candles = 0
                    expiry_skipped = 0
                    
                    # Process contracts in smaller batches with delays to avoid rate limiting
                    BATCH_SIZE = 3  # Reduced from 10 to avoid rate limits
                    DELAY_BETWEEN_BATCHES = 0.5  # 500ms delay between batches
                    
                    async def process_contract(contract):
                        """Process a single contract - returns (success, skipped, candles, error)"""
                        nonlocal results
                        try:
                            expired_key = contract.get('instrument_key')
                            symbol = contract.get('trading_symbol')
                            strike = contract.get('strike_price')
                            opt_type = contract.get('instrument_type')  # CE or PE
                            lot_size = contract.get('lot_size', 1)
                            
                            # Skip if key is missing or malformed
                            if not expired_key or '|' not in expired_key or expired_key.endswith('|'):
                                return (False, False, 0, "malformed key")
                            
                            # Parse expiry date
                            exp_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                            
                            async with self.async_session() as session:
                                # Get or create instrument
                                instrument_id = await self._get_or_create_options_instrument(
                                    session, symbol, underlying,
                                    datetime.combine(exp_date, datetime.min.time()),
                                    strike, opt_type, lot_size
                                )
                                await session.commit()
                                
                                # Check if we already have data for this contract
                                existing_count = await self._get_candle_count(session, instrument_id)
                                if existing_count > 0:
                                    return (True, True, 0, None)  # Skipped
                                
                                # Calculate date range (download full month before expiry)
                                from_date = exp_date - timedelta(days=30)
                                to_date = exp_date
                                
                                # Download expired candles
                                candles = await self.provider.get_expired_historical_candles(
                                    expired_key, interval, from_date, to_date
                                )
                                
                                if candles:
                                    stored = await self._store_candles(session, instrument_id, candles)
                                    del candles
                                    return (True, False, stored, None)
                                else:
                                    return (True, False, 0, None)
                                    
                        except Exception as e:
                            return (False, False, 0, str(e))
                    
                    # Process in batches with delays
                    for batch_start in range(0, len(contracts), BATCH_SIZE):
                        batch = contracts[batch_start:batch_start + BATCH_SIZE]
                        batch_results = await asyncio.gather(*[process_contract(c) for c in batch])
                        
                        # Add delay between batches to avoid rate limiting
                        if batch_start + BATCH_SIZE < len(contracts):
                            await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                        
                        for (success, skipped, candles, error), contract in zip(batch_results, batch):
                            results["total_contracts"] += 1
                            underlying_contracts += 1
                            
                            if success:
                                results["successful"] += 1
                                if skipped:
                                    results["skipped"] = results.get("skipped", 0) + 1
                                    expiry_skipped += 1
                                    underlying_skipped += 1
                                else:
                                    results["total_candles"] += candles
                                    underlying_candles += candles
                                    expiry_candles += candles
                            else:
                                results["failed"] += 1
                                if error and len(results["errors"]) < 100:
                                    results["errors"].append({"symbol": contract.get('trading_symbol'), "error": error})
                    
                    print(f"{len(contracts)} contracts, {expiry_candles:,} candles (skipped {expiry_skipped})", flush=True)
                    
                    # GC after each expiry
                    import gc
                    gc.collect()
                
                print(f"  => {underlying} TOTAL: {underlying_contracts} contracts, {underlying_candles:,} candles (skipped {underlying_skipped})", flush=True)
                        
            except Exception as e:
                print(f"  ERROR: {e}", flush=True)
                results["errors"].append({"underlying": underlying, "error": str(e)})
        
        print(f"\nExpired options complete: {results['successful']}/{results['total_contracts']} contracts, "
              f"{results['total_candles']:,} candles", flush=True)
        return results

    async def _get_or_create_instrument(self, session: AsyncSession, symbol: str) -> UUID:
        """Get or create instrument, return instrument_id."""
        result = await session.execute(
            select(InstrumentMaster).where(InstrumentMaster.trading_symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            instrument = InstrumentMaster(
                trading_symbol=symbol,
                exchange="NSE",
                segment="EQ",
                instrument_type="EQUITY",
                is_active=True
            )
            session.add(instrument)
            await session.flush()
        
        return instrument.instrument_id
    
    async def _get_candle_count(
        self,
        session: AsyncSession,
        instrument_id: UUID
    ) -> int:
        """Get count of candles for an instrument (to check if already downloaded)."""
        from sqlalchemy import func
        result = await session.execute(
            select(func.count()).select_from(CandleData)
            .where(CandleData.instrument_id == instrument_id)
        )
        return result.scalar() or 0
    
    async def _get_last_candle_timestamp(
        self,
        session: AsyncSession,
        instrument_id: UUID,
        interval: Interval
    ) -> Optional[datetime]:
        """Get last candle timestamp for an instrument."""
        result = await session.execute(
            select(CandleData.timestamp)
            .where(CandleData.instrument_id == instrument_id)
            .order_by(CandleData.timestamp.desc())
            .limit(1)
        )
        row = result.first()
        return row[0] if row else None
    
    async def _store_candles(
        self,
        session: AsyncSession,
        instrument_id: UUID,
        candles: List,
        timeframe: str = "1m",
        batch_size: int = 100  # Small batches to avoid memory issues
    ):
        """Store candles in database using small batch inserts with error recovery."""
        if not candles:
            return 0
        
        stored_count = 0
        
        # Process in small batches to avoid memory issues
        for i in range(0, len(candles), batch_size):
            batch = candles[i:i + batch_size]
            
            try:
                values = [
                    {
                        "instrument_id": instrument_id,
                        "timeframe": timeframe,
                        "timestamp": candle.timestamp,
                        "open": Decimal(str(candle.open)),
                        "high": Decimal(str(candle.high)),
                        "low": Decimal(str(candle.low)),
                        "close": Decimal(str(candle.close)),
                        "volume": candle.volume,
                        "oi": candle.oi
                    }
                    for candle in batch
                ]
                
                # Batch upsert
                stmt = insert(CandleData).values(values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["instrument_id", "timeframe", "timestamp"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                        "oi": stmt.excluded.oi
                    }
                )
                await session.execute(stmt)
                await session.commit()  # Commit each batch immediately
                stored_count += len(batch)
                
            except Exception as e:
                logger.error(f"Error storing batch {i//batch_size + 1}: {e}")
                await session.rollback()
                # Continue with next batch instead of failing completely
                continue
        
        return stored_count
    
    async def _log_refresh(
        self,
        session: AsyncSession,
        data_type: str,
        added: int,
        updated: int,
        processed: int,
        source: str
    ):
        """Log master data refresh."""
        log_entry = MasterDataRefreshLog(
            data_type=data_type,
            source=source,
            status="SUCCESS",
            records_processed=processed,
            records_added=added,
            records_updated=updated,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        session.add(log_entry)
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    async def get_fo_stocks_from_db(self) -> List[Dict[str, Any]]:
        """Get F&O stocks from database with sector info."""
        async with self.async_session() as session:
            result = await session.execute(
                select(
                    InstrumentMaster.trading_symbol,
                    EquityMaster.company_name,
                    EquityMaster.sector,
                    EquityMaster.is_index_constituent
                )
                .join(EquityMaster, InstrumentMaster.instrument_id == EquityMaster.instrument_id)
                .where(EquityMaster.is_fno == True)
                .order_by(InstrumentMaster.trading_symbol)
            )
            
            stocks = []
            for row in result:
                stocks.append({
                    "symbol": row.trading_symbol,
                    "name": row.company_name,
                    "sector": row.sector,
                    "is_index": row.is_index_constituent
                })
            
            return stocks
    
    async def get_download_status(self) -> Dict[str, Any]:
        """Get current download status and coverage."""
        async with self.async_session() as session:
            # Count instruments with candle data
            result = await session.execute(text("""
                SELECT 
                    COUNT(DISTINCT i.trading_symbol) as total_instruments,
                    COUNT(DISTINCT cd.instrument_id) as instruments_with_data,
                    MIN(cd.timestamp) as earliest_data,
                    MAX(cd.timestamp) as latest_data,
                    COUNT(*) as total_candles
                FROM instrument_master i
                LEFT JOIN equity_master e ON i.instrument_id = e.instrument_id
                LEFT JOIN candle_data cd ON i.instrument_id = cd.instrument_id
                WHERE e.is_fno = true
            """))
            
            row = result.first()
            return {
                "total_fo_instruments": row.total_instruments,
                "instruments_with_data": row.instruments_with_data,
                "earliest_data": str(row.earliest_data) if row.earliest_data else None,
                "latest_data": str(row.latest_data) if row.latest_data else None,
                "total_candles": row.total_candles
            }

    async def get_data_coverage_report(self) -> Dict[str, Any]:
        """
        Get comprehensive data coverage report.
        
        Returns a structured report with:
        - Summary totals
        - Breakdown by instrument type
        - F&O breakdown by underlying
        """
        async with self.async_session() as session:
            report = {
                "generated_at": datetime.utcnow().isoformat(),
                "summary": {},
                "by_instrument_type": [],
                "fo_by_underlying": []
            }
            
            # Summary totals
            result = await session.execute(text("""
                SELECT 
                    COUNT(*) as total_candles,
                    COUNT(DISTINCT instrument_id) as total_instruments
                FROM candle_data
            """))
            row = result.first()
            
            result2 = await session.execute(text("""
                SELECT COUNT(*) FROM instrument_master
            """))
            total_master = result2.scalar()
            
            report["summary"] = {
                "total_candles": row.total_candles,
                "instruments_with_data": row.total_instruments,
                "total_instruments_in_master": total_master
            }
            
            # Breakdown by instrument type
            result = await session.execute(text("""
                SELECT 
                    im.instrument_type,
                    COUNT(DISTINCT im.instrument_id) as instruments,
                    COALESCE(SUM(cd.candle_count), 0) as candles,
                    MIN(cd.min_ts)::date as from_date,
                    MAX(cd.max_ts)::date as to_date
                FROM instrument_master im
                LEFT JOIN (
                    SELECT 
                        instrument_id, 
                        COUNT(*) as candle_count,
                        MIN(timestamp) as min_ts,
                        MAX(timestamp) as max_ts
                    FROM candle_data 
                    GROUP BY instrument_id
                ) cd ON im.instrument_id = cd.instrument_id
                GROUP BY im.instrument_type
                ORDER BY candles DESC NULLS LAST
            """))
            
            for row in result.fetchall():
                report["by_instrument_type"].append({
                    "type": row.instrument_type or "UNKNOWN",
                    "instruments": row.instruments,
                    "candles": int(row.candles),
                    "from_date": str(row.from_date) if row.from_date else None,
                    "to_date": str(row.to_date) if row.to_date else None
                })
            
            # F&O breakdown by underlying
            result = await session.execute(text("""
                SELECT 
                    CASE 
                        WHEN im.trading_symbol LIKE 'NIFTY %%' OR im.trading_symbol LIKE 'NIFTY%%FUT%%' THEN 'NIFTY'
                        WHEN im.trading_symbol LIKE 'BANKNIFTY %%' OR im.trading_symbol LIKE 'BANKNIFTY%%FUT%%' THEN 'BANKNIFTY'
                        WHEN im.trading_symbol LIKE 'FINNIFTY %%' OR im.trading_symbol LIKE 'FINNIFTY%%FUT%%' THEN 'FINNIFTY'
                        WHEN im.trading_symbol LIKE 'MIDCPNIFTY %%' OR im.trading_symbol LIKE 'MIDCPNIFTY%%FUT%%' THEN 'MIDCPNIFTY'
                        WHEN im.trading_symbol LIKE 'SENSEX %%' OR im.trading_symbol LIKE 'SENSEX%%FUT%%' THEN 'SENSEX'
                        WHEN im.trading_symbol LIKE 'BANKEX %%' OR im.trading_symbol LIKE 'BANKEX%%FUT%%' THEN 'BANKEX'
                        ELSE 'OTHER'
                    END as underlying,
                    im.instrument_type,
                    COUNT(DISTINCT im.instrument_id) as instruments,
                    COALESCE(SUM(cd.candle_count), 0) as candles,
                    MIN(cd.min_ts)::date as from_date,
                    MAX(cd.max_ts)::date as to_date
                FROM instrument_master im
                LEFT JOIN (
                    SELECT 
                        instrument_id, 
                        COUNT(*) as candle_count,
                        MIN(timestamp) as min_ts,
                        MAX(timestamp) as max_ts
                    FROM candle_data 
                    GROUP BY instrument_id
                ) cd ON im.instrument_id = cd.instrument_id
                WHERE im.instrument_type IN ('FUT', 'FUTURES', 'CE', 'PE')
                GROUP BY 1, im.instrument_type
                ORDER BY underlying, im.instrument_type
            """))
            
            for row in result.fetchall():
                report["fo_by_underlying"].append({
                    "underlying": row.underlying,
                    "type": row.instrument_type,
                    "instruments": row.instruments,
                    "candles": int(row.candles),
                    "from_date": str(row.from_date) if row.from_date else None,
                    "to_date": str(row.to_date) if row.to_date else None
                })
            
            # Stock F&O breakdown (non-index)
            report["stock_fo"] = []
            result = await session.execute(text("""
                SELECT 
                    im.instrument_type,
                    COUNT(DISTINCT im.instrument_id) as instruments,
                    COALESCE(SUM(cd.candle_count), 0) as candles,
                    MIN(cd.min_ts)::date as from_date,
                    MAX(cd.max_ts)::date as to_date
                FROM instrument_master im
                LEFT JOIN (
                    SELECT 
                        instrument_id, 
                        COUNT(*) as candle_count,
                        MIN(timestamp) as min_ts,
                        MAX(timestamp) as max_ts
                    FROM candle_data 
                    GROUP BY instrument_id
                ) cd ON im.instrument_id = cd.instrument_id
                WHERE im.instrument_type IN ('FUT', 'FUTURES', 'CE', 'PE')
                AND im.trading_symbol NOT LIKE 'NIFTY%%'
                AND im.trading_symbol NOT LIKE 'BANKNIFTY%%'
                AND im.trading_symbol NOT LIKE 'FINNIFTY%%'
                AND im.trading_symbol NOT LIKE 'MIDCPNIFTY%%'
                AND im.trading_symbol NOT LIKE 'SENSEX%%'
                AND im.trading_symbol NOT LIKE 'BANKEX%%'
                GROUP BY im.instrument_type
                ORDER BY candles DESC
            """))
            
            for row in result.fetchall():
                report["stock_fo"].append({
                    "type": row.instrument_type,
                    "instruments": row.instruments,
                    "candles": int(row.candles),
                    "from_date": str(row.from_date) if row.from_date else None,
                    "to_date": str(row.to_date) if row.to_date else None
                })
            
            return report

    def print_data_coverage_report(self, report: Dict[str, Any]) -> None:
        """Print data coverage report in a formatted table."""
        print()
        print("=" * 90)
        print("DATA COVERAGE REPORT")
        print(f"Generated: {report['generated_at']}")
        print("=" * 90)
        
        summary = report["summary"]
        print(f"\nSUMMARY:")
        print(f"  Total Candles:          {summary['total_candles']:>15,}")
        print(f"  Instruments with Data:  {summary['instruments_with_data']:>15,}")
        print(f"  Total in Master:        {summary['total_instruments_in_master']:>15,}")
        
        print()
        print("-" * 90)
        print(f"{'Type':<15} {'Instruments':>12} {'Candles':>15} {'From Date':>14} {'To Date':>14}")
        print("-" * 90)
        
        for item in report["by_instrument_type"]:
            print(f"{item['type']:<15} {item['instruments']:>12,} {item['candles']:>15,} "
                  f"{item['from_date'] or 'N/A':>14} {item['to_date'] or 'N/A':>14}")
        
        if report["fo_by_underlying"]:
            print()
            print("-" * 90)
            print("F&O BREAKDOWN BY UNDERLYING:")
            print("-" * 90)
            print(f"{'Underlying':<12} {'Type':<10} {'Instruments':>12} {'Candles':>15} {'From':>12} {'To':>12}")
            print("-" * 90)
            
            for item in report["fo_by_underlying"]:
                print(f"{item['underlying']:<12} {item['type']:<10} {item['instruments']:>12,} "
                      f"{item['candles']:>15,} {item['from_date'] or 'N/A':>12} {item['to_date'] or 'N/A':>12}")
        
        # Stock F&O section
        if report.get("stock_fo"):
            print()
            print("-" * 90)
            print("STOCK F&O (Non-Index):")
            print("-" * 90)
            print(f"{'Type':<15} {'Instruments':>12} {'Candles':>15} {'From':>14} {'To':>14}")
            print("-" * 90)
            
            for item in report["stock_fo"]:
                print(f"{item['type']:<15} {item['instruments']:>12,} {item['candles']:>15,} "
                      f"{item['from_date'] or 'N/A':>14} {item['to_date'] or 'N/A':>14}")
            
            if not any(item['candles'] > 0 for item in report["stock_fo"]):
                print("  *** NO STOCK OPTIONS/FUTURES DATA DOWNLOADED ***")
        else:
            print()
            print("-" * 90)
            print("STOCK F&O: No data available")
        
        print("=" * 90)


# =============================================================================
# Convenience Functions
# =============================================================================

async def download_all_fo_data(
    from_date: date = date(2022, 1, 1),
    to_date: date = None,
    token_file: str = "data/upstox_token.json"
):
    """
    Convenience function to download all F&O stock data.
    
    Args:
        from_date: Start date for historical data
        to_date: End date (defaults to today)
        token_file: Path to Upstox token file
    """
    provider = create_upstox_provider(token_file)
    service = DataDownloadService(provider)
    
    try:
        await service.initialize()
        
        # First sync F&O stocks with sectors
        print("Syncing F&O stocks to database...")
        await service.sync_fo_stocks_to_db()
        
        # Then download historical data
        print("Downloading historical data...")
        results = await service.download_historical_data(
            from_date=from_date,
            to_date=to_date or date.today()
        )
        
        print(f"\nDownload Summary:")
        print(f"  Successful: {results['successful']}/{results['total_symbols']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Total Candles: {results['total_candles']}")
        
        if results['errors']:
            print(f"\nErrors:")
            for err in results['errors'][:10]:
                print(f"  {err['symbol']}: {err['error']}")
        
        # Show status
        status = await service.get_download_status()
        print(f"\nDatabase Status:")
        print(f"  F&O Instruments: {status['total_fo_instruments']}")
        print(f"  With Data: {status['instruments_with_data']}")
        print(f"  Date Range: {status['earliest_data']} to {status['latest_data']}")
        print(f"  Total Candles: {status['total_candles']}")
        
    finally:
        await service.close()


# CLI entry point
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    asyncio.run(download_all_fo_data())
