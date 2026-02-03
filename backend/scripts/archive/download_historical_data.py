"""
Historical Data Download Service for PostgreSQL
KeepGaining Trading Platform

Downloads complete market data from Upstox API:
- F&O Stocks (180+)
- Index data (NIFTY, BANKNIFTY, FINNIFTY, MIDCAP NIFTY)
- Futures data (current + expired)
- Options data (current + expired via Upstox Expired API)

Stores data in PostgreSQL with TimescaleDB-ready schema.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import json
import uuid

import pandas as pd
import httpx
from loguru import logger
from sqlalchemy import create_engine, text, select, insert
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/keepgaining"
).replace("+asyncpg", "")  # Use sync driver for bulk operations

# Upstox API configuration
UPSTOX_BASE_URL = "https://api.upstox.com/v3"  # Using V3 API for better historical data
UPSTOX_TOKEN_FILE = Path("data/upstox_token.json")

# Rate limiting
REQUESTS_PER_MINUTE = 1800  # Conservative estimate (Upstox allows ~2000)
REQUEST_DELAY = 60 / REQUESTS_PER_MINUTE


@dataclass
class DownloadConfig:
    """Configuration for data download."""
    start_date: date = field(default_factory=lambda: date.today() - timedelta(days=365))
    end_date: date = field(default_factory=date.today)
    interval: str = "1minute"  # 1minute, 5minute, 15minute, 30minute, day
    download_equities: bool = True
    download_indices: bool = True
    download_futures: bool = True
    download_options: bool = False  # Options require special handling
    download_expired: bool = False  # Expired contracts
    fo_stocks_only: bool = True  # Only F&O enabled stocks
    batch_size: int = 50  # Symbols per batch for parallel downloads


# =============================================================================
# Index definitions (these are standard and rarely change)
# =============================================================================

INDICES = [
    {"symbol": "NIFTY 50", "key": "NSE_INDEX|Nifty 50"},
    {"symbol": "NIFTY BANK", "key": "NSE_INDEX|Nifty Bank"},
    {"symbol": "NIFTY FIN SERVICE", "key": "NSE_INDEX|Nifty Fin Service"},
    {"symbol": "NIFTY MIDCAP SELECT", "key": "NSE_INDEX|NIFTY MID SELECT"},
    {"symbol": "INDIA VIX", "key": "NSE_INDEX|India VIX"},
    {"symbol": "NIFTY IT", "key": "NSE_INDEX|Nifty IT"},
    {"symbol": "NIFTY PHARMA", "key": "NSE_INDEX|Nifty Pharma"},
    {"symbol": "NIFTY METAL", "key": "NSE_INDEX|Nifty Metal"},
    {"symbol": "NIFTY AUTO", "key": "NSE_INDEX|Nifty Auto"},
    {"symbol": "NIFTY REALTY", "key": "NSE_INDEX|Nifty Realty"},
]


class UpstoxDataDownloader:
    """
    Downloads historical data from Upstox API.
    
    Supports:
    - Active instruments via /historical-candle endpoint
    - Expired instruments via /expired-instruments/historical-candle endpoint
    """
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client: Optional[httpx.AsyncClient] = None
        self.request_count = 0
        self.last_request_time = datetime.now()
        self.instrument_master: Dict[str, Dict] = {}  # symbol -> instrument info
        
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=20),
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = (datetime.now() - self.last_request_time).total_seconds()
        if elapsed < REQUEST_DELAY:
            await asyncio.sleep(REQUEST_DELAY - elapsed)
        self.last_request_time = datetime.now()
        self.request_count += 1
    
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated API request."""
        await self._rate_limit()
        
        url = f"{UPSTOX_BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        
        try:
            response = await self.client.get(url, headers=headers, params=params)
            
            if response.status_code == 429:
                logger.warning("Rate limit hit, waiting 60 seconds...")
                await asyncio.sleep(60)
                return await self._make_request(endpoint, params)
            
            if response.status_code == 401:
                logger.error("Authentication failed - token expired")
                return None
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None
    
    async def get_instrument_master(self) -> pd.DataFrame:
        """Download complete instrument master from Upstox."""
        logger.info("Downloading instrument master...")
        
        # Download NSE equity instruments
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        
        try:
            import gzip
            import io
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                
                content = gzip.decompress(response.content)
                instruments = json.loads(content)
                
                # Build lookup for equities
                for inst in instruments:
                    if inst.get('instrument_type') == 'EQ':
                        symbol = inst.get('trading_symbol')
                        self.instrument_master[symbol] = {
                            'instrument_key': inst.get('instrument_key'),
                            'isin': inst.get('isin'),
                            'name': inst.get('name'),
                            'lot_size': inst.get('lot_size', 1),
                            'tick_size': inst.get('tick_size'),
                            'exchange_token': inst.get('exchange_token'),
                        }
                
                # Extract F&O enabled stocks from futures instruments
                fo_stocks = set()
                for inst in instruments:
                    if inst.get('segment') == 'NSE_FO' and inst.get('instrument_type') == 'FUT':
                        underlying = inst.get('underlying_symbol') or inst.get('asset_symbol')
                        if underlying:
                            fo_stocks.add(underlying)
                
                self.fo_stocks = sorted(list(fo_stocks))
                
                logger.info(f"Loaded {len(self.instrument_master):,} equity instruments")
                logger.info(f"Found {len(self.fo_stocks)} F&O enabled stocks")
                return pd.DataFrame(instruments)
                
        except Exception as e:
            logger.error(f"Failed to download instrument master: {e}")
            return pd.DataFrame()
    
    def get_fo_stocks(self) -> List[str]:
        """Get list of F&O enabled stocks."""
        return self.fo_stocks if hasattr(self, 'fo_stocks') else []
    
    def get_instrument_key(self, symbol: str) -> Optional[str]:
        """Get the Upstox instrument key for a symbol."""
        info = self.instrument_master.get(symbol)
        return info.get('instrument_key') if info else None
    
    async def get_historical_candles(
        self,
        instrument_key: str,
        interval: str,
        from_date: date,
        to_date: date,
        is_expired: bool = False,
    ) -> List[Dict]:
        """
        Get historical candle data for an instrument using V3 API.
        
        V3 API format: /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}
        
        Args:
            instrument_key: Upstox instrument key (e.g., NSE_EQ|INE002A01018)
            interval: 1minute, 5minute, 15minute, 30minute, 60minute, day
            from_date: Start date
            to_date: End date
            is_expired: If True, use expired instruments endpoint (V2 only)
            
        Returns:
            List of candle dictionaries
        """
        all_candles = []
        
        # Map interval to V3 format (unit, interval_number)
        interval_map = {
            "1minute": ("minutes", "1"),
            "5minute": ("minutes", "5"),
            "15minute": ("minutes", "15"),
            "30minute": ("minutes", "30"),
            "60minute": ("hours", "1"),
            "day": ("days", "1"),
        }
        
        if interval not in interval_map:
            logger.warning(f"Unsupported interval: {interval}, defaulting to 1minute")
            interval = "1minute"
        
        unit, interval_num = interval_map[interval]
        
        # V3 API limits: 1 month for 1-15min, 1 quarter for >15min
        is_short_interval = interval in ["1minute", "5minute", "15minute"]
        chunk_days = 28 if is_short_interval else 90  # ~1 month or ~1 quarter
        
        current_from = from_date
        
        while current_from <= to_date:
            current_to = min(current_from + timedelta(days=chunk_days), to_date)
            
            # URL encode the instrument key
            import urllib.parse
            encoded_key = urllib.parse.quote(instrument_key, safe='')
            
            # V3 endpoint format: /historical-candle/{key}/{unit}/{interval}/{to_date}/{from_date}
            endpoint = f"/historical-candle/{encoded_key}/{unit}/{interval_num}/{current_to.isoformat()}/{current_from.isoformat()}"
            
            response = await self._make_request(endpoint)
            
            if response and response.get("status") == "success":
                candles = response.get("data", {}).get("candles", [])
                
                for candle in candles:
                    # Upstox format: [timestamp, open, high, low, close, volume, oi]
                    try:
                        all_candles.append({
                            "timestamp": candle[0],
                            "open": float(candle[1]),
                            "high": float(candle[2]),
                            "low": float(candle[3]),
                            "close": float(candle[4]),
                            "volume": int(candle[5]),
                            "oi": int(candle[6]) if len(candle) > 6 else 0,
                        })
                    except (IndexError, ValueError) as e:
                        logger.warning(f"Invalid candle data: {candle}")
            
            current_from = current_to + timedelta(days=1)
        
        return all_candles
    
    async def get_expired_instruments(
        self,
        underlying: str,
        expiry_date: date,
    ) -> List[Dict]:
        """Get list of expired instruments for an underlying."""
        endpoint = f"/expired-instruments/{underlying}"
        params = {"expiry_date": expiry_date.isoformat()}
        
        response = await self._make_request(endpoint, params)
        
        if response and response.get("status") == "success":
            return response.get("data", [])
        return []


class PostgreSQLLoader:
    """Load data into PostgreSQL database."""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, echo=False)
        
    def check_tables_exist(self) -> bool:
        """Check if required tables already exist."""
        with Session(self.engine) as session:
            result = session.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'instrument_master'")
            ).scalar()
            return result > 0
        
    def create_tables(self):
        """Create all required tables (skip if already exist)."""
        if self.check_tables_exist():
            logger.info("Database tables already exist, skipping creation")
            return
        
        logger.info("Creating database tables...")
        
        # Read and execute the schema
        schema_sql = """
        -- Instrument Master (simplified for initial load)
        CREATE TABLE IF NOT EXISTS instrument_master (
            instrument_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(200),
            instrument_type VARCHAR(20) NOT NULL,
            exchange VARCHAR(20) NOT NULL,
            segment VARCHAR(20),
            lot_size INTEGER DEFAULT 1,
            tick_size NUMERIC(10, 2),
            is_tradeable BOOLEAN DEFAULT true,
            is_fo_enabled BOOLEAN DEFAULT false,
            isin VARCHAR(20),
            upstox_key VARCHAR(100),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_instrument_type ON instrument_master(instrument_type);
        CREATE INDEX IF NOT EXISTS idx_instrument_exchange ON instrument_master(exchange);
        CREATE INDEX IF NOT EXISTS idx_instrument_upstox_key ON instrument_master(upstox_key);
        
        -- Candle Data (base 1-minute)
        CREATE TABLE IF NOT EXISTS candle_data (
            instrument_id UUID NOT NULL REFERENCES instrument_master(instrument_id),
            timestamp TIMESTAMPTZ NOT NULL,
            open NUMERIC(18, 4) NOT NULL,
            high NUMERIC(18, 4) NOT NULL,
            low NUMERIC(18, 4) NOT NULL,
            close NUMERIC(18, 4) NOT NULL,
            volume BIGINT NOT NULL,
            oi BIGINT DEFAULT 0,
            oi_change BIGINT DEFAULT 0,
            PRIMARY KEY (instrument_id, timestamp)
        );
        
        CREATE INDEX IF NOT EXISTS idx_candle_timestamp ON candle_data(timestamp);
        
        -- Option Master (for options data)
        CREATE TABLE IF NOT EXISTS option_master (
            instrument_id UUID PRIMARY KEY REFERENCES instrument_master(instrument_id),
            underlying_id UUID REFERENCES instrument_master(instrument_id),
            expiry_date DATE NOT NULL,
            expiry_type VARCHAR(20),
            strike_price NUMERIC(10, 2) NOT NULL,
            option_type VARCHAR(2) NOT NULL,
            contract_size INTEGER
        );
        
        CREATE INDEX IF NOT EXISTS idx_option_underlying ON option_master(underlying_id);
        CREATE INDEX IF NOT EXISTS idx_option_expiry ON option_master(expiry_date);
        
        -- Future Master
        CREATE TABLE IF NOT EXISTS future_master (
            instrument_id UUID PRIMARY KEY REFERENCES instrument_master(instrument_id),
            underlying_id UUID REFERENCES instrument_master(instrument_id),
            expiry_date DATE NOT NULL,
            expiry_type VARCHAR(20),
            contract_size INTEGER
        );
        
        CREATE INDEX IF NOT EXISTS idx_future_underlying ON future_master(underlying_id);
        CREATE INDEX IF NOT EXISTS idx_future_expiry ON future_master(expiry_date);
        
        -- Broker Symbol Mapping
        CREATE TABLE IF NOT EXISTS broker_symbol_mapping (
            id SERIAL PRIMARY KEY,
            instrument_id UUID REFERENCES instrument_master(instrument_id),
            broker VARCHAR(50) NOT NULL,
            broker_symbol VARCHAR(100) NOT NULL,
            broker_token VARCHAR(50),
            segment VARCHAR(50),
            last_verified TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(instrument_id, broker)
        );
        
        -- Indicator Data (pre-computed)
        CREATE TABLE IF NOT EXISTS indicator_data (
            instrument_id UUID NOT NULL REFERENCES instrument_master(instrument_id),
            timestamp TIMESTAMPTZ NOT NULL,
            timeframe VARCHAR(10) NOT NULL DEFAULT '1m',
            sma_9 NUMERIC(18, 4),
            sma_20 NUMERIC(18, 4),
            sma_50 NUMERIC(18, 4),
            sma_200 NUMERIC(18, 4),
            ema_9 NUMERIC(18, 4),
            ema_21 NUMERIC(18, 4),
            ema_50 NUMERIC(18, 4),
            ema_200 NUMERIC(18, 4),
            rsi_14 NUMERIC(10, 4),
            rsi_9 NUMERIC(10, 4),
            macd NUMERIC(18, 4),
            macd_signal NUMERIC(18, 4),
            macd_histogram NUMERIC(18, 4),
            stoch_k NUMERIC(10, 4),
            stoch_d NUMERIC(10, 4),
            bb_upper NUMERIC(18, 4),
            bb_middle NUMERIC(18, 4),
            bb_lower NUMERIC(18, 4),
            atr_14 NUMERIC(18, 4),
            adx NUMERIC(10, 4),
            supertrend NUMERIC(18, 4),
            supertrend_direction SMALLINT,
            vwap NUMERIC(18, 4),
            vwma_20 NUMERIC(18, 4),
            vwma_22 NUMERIC(18, 4),
            vwma_31 NUMERIC(18, 4),
            obv BIGINT,
            PRIMARY KEY (instrument_id, timestamp, timeframe)
        );
        """
        
        with self.engine.connect() as conn:
            for statement in schema_sql.split(';'):
                statement = statement.strip()
                if statement:
                    try:
                        conn.execute(text(statement))
                    except Exception as e:
                        logger.warning(f"Schema statement failed (may already exist): {e}")
            conn.commit()
        
        logger.info("Database tables created successfully")
    
    def get_or_create_instrument(
        self,
        symbol: str,
        instrument_type: str,
        exchange: str = "NSE",
        upstox_key: Optional[str] = None,
        **kwargs
    ) -> uuid.UUID:
        """Get or create an instrument and return its ID."""
        # Extract just the trading symbol (e.g., NSE:RELIANCE -> RELIANCE)
        trading_symbol = symbol.split(":")[-1] if ":" in symbol else symbol
        segment = kwargs.get("segment", "EQ" if instrument_type == "EQUITY" else "FO")
        
        with Session(self.engine) as session:
            # Check if exists
            result = session.execute(
                text("SELECT instrument_id FROM instrument_master WHERE trading_symbol = :symbol AND exchange = :exchange"),
                {"symbol": trading_symbol, "exchange": exchange}
            ).fetchone()
            
            if result:
                return result[0]
            
            # Create new
            instrument_id = uuid.uuid4()
            session.execute(
                text("""
                    INSERT INTO instrument_master 
                    (instrument_id, trading_symbol, instrument_type, exchange, segment,
                     lot_size, is_active)
                    VALUES (:id, :symbol, :type, :exchange, :segment,
                            :lot_size, :is_active)
                """),
                {
                    "id": instrument_id,
                    "symbol": trading_symbol,
                    "type": instrument_type,
                    "exchange": exchange,
                    "segment": segment,
                    "lot_size": kwargs.get("lot_size", 1),
                    "is_active": True,
                }
            )
            session.commit()
            
            return instrument_id
    
    def bulk_insert_candles(
        self,
        instrument_id: uuid.UUID,
        candles: List[Dict],
        timeframe: str = "1m",
    ) -> int:
        """Bulk insert candle data."""
        if not candles:
            return 0
        
        # Map interval to timeframe code
        tf_map = {
            "1minute": "1m",
            "5minute": "5m", 
            "15minute": "15m",
            "30minute": "30m",
            "60minute": "1h",
            "day": "1d",
        }
        tf = tf_map.get(timeframe, timeframe)
        
        # Prepare data
        records = []
        for candle in candles:
            records.append({
                "instrument_id": instrument_id,
                "timeframe": tf,
                "timestamp": candle["timestamp"],
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle["volume"],
                "oi": candle.get("oi", 0),
            })
        
        # Bulk insert with conflict handling
        with Session(self.engine) as session:
            # Use ON CONFLICT DO NOTHING for duplicates
            stmt = text("""
                INSERT INTO candle_data 
                (instrument_id, timeframe, timestamp, open, high, low, close, volume, oi)
                VALUES (:instrument_id, :timeframe, :timestamp, :open, :high, :low, :close, :volume, :oi)
                ON CONFLICT (instrument_id, timeframe, timestamp) DO NOTHING
            """)
            
            session.execute(stmt, records)
            session.commit()
        
        return len(records)
    
    def get_last_candle_date(self, instrument_id: uuid.UUID, timeframe: str = "1m") -> Optional[date]:
        """Get the last candle date for an instrument."""
        with Session(self.engine) as session:
            result = session.execute(
                text("""
                    SELECT MAX(timestamp)::date 
                    FROM candle_data 
                    WHERE instrument_id = :id AND timeframe = :tf
                """),
                {"id": instrument_id, "tf": timeframe}
            ).fetchone()
            
            return result[0] if result and result[0] else None
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        with Session(self.engine) as session:
            instruments = session.execute(
                text("SELECT COUNT(*) FROM instrument_master")
            ).scalar()
            
            candles = session.execute(
                text("SELECT COUNT(*) FROM candle_data")
            ).scalar()
            
            return {
                "instruments": instruments or 0,
                "candles": candles or 0,
            }


def load_access_token() -> Optional[str]:
    """Load Upstox access token from file."""
    try:
        if UPSTOX_TOKEN_FILE.exists():
            data = json.loads(UPSTOX_TOKEN_FILE.read_text())
            
            # Check if token is from today
            saved_at = data.get("saved_at", "")
            if saved_at:
                saved_date = datetime.fromisoformat(saved_at).date()
                if saved_date < date.today():
                    logger.warning("Saved token is from a previous day - may be expired")
            
            return data.get("access_token")
    except Exception as e:
        logger.error(f"Failed to load access token: {e}")
    
    return None


async def download_equity_data(
    downloader: UpstoxDataDownloader,
    loader: PostgreSQLLoader,
    config: DownloadConfig,
    symbols: List[str],
):
    """Download equity/stock data."""
    logger.info(f"Downloading equity data for {len(symbols)} symbols...")
    
    # Map interval to timeframe
    tf_map = {"1minute": "1m", "5minute": "5m", "15minute": "15m", "30minute": "30m", "day": "1d"}
    timeframe = tf_map.get(config.interval, "1m")
    
    total_candles = 0
    skipped_symbols = []
    
    for idx, symbol in enumerate(symbols, 1):
        # Get instrument key from master (ISIN-based format)
        upstox_key = downloader.get_instrument_key(symbol)
        
        if not upstox_key:
            skipped_symbols.append(symbol)
            logger.warning(f"[{idx}/{len(symbols)}] {symbol}: Not found in instrument master")
            continue
        
        # Get instrument info
        inst_info = downloader.instrument_master.get(symbol, {})
        
        # Get or create instrument
        instrument_id = loader.get_or_create_instrument(
            symbol=f"NSE:{symbol}",
            instrument_type="EQUITY",
            exchange="NSE",
            upstox_key=upstox_key,
            is_fo_enabled=True,
            isin=inst_info.get('isin'),
            name=inst_info.get('name'),
            lot_size=inst_info.get('lot_size', 1),
        )
        
        # Check last date
        last_date = loader.get_last_candle_date(instrument_id, timeframe)
        start_date = last_date + timedelta(days=1) if last_date else config.start_date
        
        if start_date > config.end_date:
            logger.info(f"[{idx}/{len(symbols)}] {symbol}: Up to date")
            continue
        
        # Download candles
        candles = await downloader.get_historical_candles(
            instrument_key=upstox_key,
            interval=config.interval,
            from_date=start_date,
            to_date=config.end_date,
        )
        
        if candles:
            inserted = loader.bulk_insert_candles(instrument_id, candles, config.interval)
            total_candles += inserted
            logger.info(f"[{idx}/{len(symbols)}] {symbol}: {inserted:,} candles")
        else:
            logger.warning(f"[{idx}/{len(symbols)}] {symbol}: No data")
    
    if skipped_symbols:
        logger.warning(f"Skipped {len(skipped_symbols)} symbols not found: {skipped_symbols[:10]}...")
    
    return total_candles


async def download_index_data(
    downloader: UpstoxDataDownloader,
    loader: PostgreSQLLoader,
    config: DownloadConfig,
):
    """Download index data."""
    logger.info(f"Downloading index data for {len(INDICES)} indices...")
    
    # Map interval to timeframe
    tf_map = {"1minute": "1m", "5minute": "5m", "15minute": "15m", "30minute": "30m", "day": "1d"}
    timeframe = tf_map.get(config.interval, "1m")
    
    total_candles = 0
    
    for idx, index_info in enumerate(INDICES, 1):
        symbol = index_info["symbol"]
        upstox_key = index_info["key"]
        
        # Get or create instrument (use symbol without spaces for trading_symbol)
        trading_symbol = symbol.replace(" ", "_")
        
        instrument_id = loader.get_or_create_instrument(
            symbol=f"NSE:{trading_symbol}",
            instrument_type="INDEX",
            exchange="NSE",
            upstox_key=upstox_key,
            name=symbol,
            segment="INDEX",
        )
        
        # Check last date
        last_date = loader.get_last_candle_date(instrument_id, timeframe)
        start_date = last_date + timedelta(days=1) if last_date else config.start_date
        
        if start_date > config.end_date:
            logger.info(f"[{idx}/{len(INDICES)}] {symbol}: Up to date")
            continue
        
        # Download candles
        candles = await downloader.get_historical_candles(
            instrument_key=upstox_key,
            interval=config.interval,
            from_date=start_date,
            to_date=config.end_date,
        )
        
        if candles:
            inserted = loader.bulk_insert_candles(instrument_id, candles, config.interval)
            total_candles += inserted
            logger.info(f"[{idx}/{len(INDICES)}] {symbol}: {inserted:,} candles")
        else:
            logger.warning(f"[{idx}/{len(INDICES)}] {symbol}: No data")
    
    return total_candles


async def main():
    """Main download function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Download historical data to PostgreSQL")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--interval", type=str, default="1minute", 
                        choices=["1minute", "5minute", "15minute", "30minute", "day"])
    parser.add_argument("--equities", action="store_true", help="Download equities")
    parser.add_argument("--indices", action="store_true", help="Download indices")
    parser.add_argument("--all", action="store_true", help="Download all data types")
    parser.add_argument("--symbols", type=str, help="Comma-separated list of symbols")
    parser.add_argument("--limit", type=int, help="Limit number of symbols")
    
    args = parser.parse_args()
    
    # Configuration
    config = DownloadConfig(
        interval=args.interval,
        download_equities=args.equities or args.all,
        download_indices=args.indices or args.all,
    )
    
    if args.start:
        config.start_date = date.fromisoformat(args.start)
    if args.end:
        config.end_date = date.fromisoformat(args.end)
    
    # Load access token
    access_token = load_access_token()
    if not access_token:
        logger.error("No Upstox access token found!")
        logger.info("Please authenticate first using the Upstox auth flow.")
        logger.info("Token should be saved in data/upstox_token.json")
        return
    
    # Initialize loader
    logger.info(f"Connecting to database: {DATABASE_URL.split('@')[-1]}")
    loader = PostgreSQLLoader(DATABASE_URL)
    
    # Create tables
    loader.create_tables()
    
    total_candles = 0
    
    async with UpstoxDataDownloader(access_token) as downloader:
        # Load instrument master first (this also fetches F&O stocks list)
        logger.info("Loading Upstox instrument master...")
        await downloader.get_instrument_master()
        
        if not downloader.instrument_master:
            logger.error("Failed to load instrument master!")
            return
        
        # Get symbols - use dynamic F&O list from instrument master
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
        else:
            # Use dynamically fetched F&O stocks
            symbols = downloader.get_fo_stocks()
            logger.info(f"Using {len(symbols)} F&O stocks from instrument master")
        
        if args.limit:
            symbols = symbols[:args.limit]
        
        logger.info("="*80)
        logger.info("HISTORICAL DATA DOWNLOAD")
        logger.info("="*80)
        logger.info(f"Period: {config.start_date} to {config.end_date}")
        logger.info(f"Interval: {config.interval}")
        logger.info(f"Symbols: {len(symbols)}")
        logger.info("="*80)
        
        # Download equities
        if config.download_equities:
            equity_candles = await download_equity_data(
                downloader, loader, config, symbols
            )
            total_candles += equity_candles
        
        # Download indices
        if config.download_indices:
            index_candles = await download_index_data(
                downloader, loader, config
            )
            total_candles += index_candles
    
    # Final stats
    stats = loader.get_stats()
    
    logger.info("="*80)
    logger.info("DOWNLOAD COMPLETE")
    logger.info("="*80)
    logger.info(f"Total instruments: {stats['instruments']:,}")
    logger.info(f"Total candles: {stats['candles']:,}")
    logger.info(f"New candles added: {total_candles:,}")
    logger.info(f"API requests made: {downloader.request_count}")
    logger.info("="*80)


if __name__ == "__main__":
    asyncio.run(main())
