"""
Upstox Data Provider Implementation

Implements BaseDataProvider interface for Upstox API V3.
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp
import pandas as pd

from .base import (
    BaseDataProvider,
    Candle,
    DataProviderConfig,
    Exchange,
    Instrument,
    InstrumentType,
    Interval,
)

logger = logging.getLogger(__name__)


class UpstoxDataProvider(BaseDataProvider):
    """
    Upstox API V3 data provider implementation.
    
    Features:
    - Historical data from Jan 2022 (1-minute candles)
    - Complete instrument master
    - F&O stocks list from futures instruments
    - Rate limiting support with parallel downloads
    """
    
    BASE_URL = "https://api.upstox.com"
    INSTRUMENT_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange"
    
    # API version endpoints
    V2_ENDPOINT = "/v2"
    V3_ENDPOINT = "/v3"
    
    # Rate limiting: 1000 requests/minute = ~16/sec
    # Use 10 concurrent requests with 100ms spacing = ~10/sec (safe margin)
    MAX_CONCURRENT_REQUESTS = 10
    REQUEST_SPACING_MS = 100  # ms between request starts
    
    # Data availability limits per interval (V3 API)
    DATA_LIMITS = {
        Interval.MINUTE_1: {"max_days": 30, "start_date": date(2022, 1, 1)},
        Interval.MINUTE_3: {"max_days": 30, "start_date": date(2022, 1, 1)},
        Interval.MINUTE_5: {"max_days": 30, "start_date": date(2022, 1, 1)},
        Interval.MINUTE_15: {"max_days": 30, "start_date": date(2022, 1, 1)},
        Interval.MINUTE_30: {"max_days": 90, "start_date": date(2018, 1, 1)},
        Interval.HOUR_1: {"max_days": 90, "start_date": date(2018, 1, 1)},
        Interval.DAY: {"max_days": 365, "start_date": date(2000, 1, 1)},
        Interval.WEEK: {"max_days": 365, "start_date": date(2000, 1, 1)},
        Interval.MONTH: {"max_days": 365 * 5, "start_date": date(2000, 1, 1)},
    }
    
    # Interval mapping to Upstox V3 format (unit, interval_value)
    INTERVAL_MAP = {
        Interval.MINUTE_1: ("minutes", 1),
        Interval.MINUTE_3: ("minutes", 3),
        Interval.MINUTE_5: ("minutes", 5),
        Interval.MINUTE_15: ("minutes", 15),
        Interval.MINUTE_30: ("minutes", 30),
        Interval.HOUR_1: ("hours", 1),
        Interval.DAY: ("days", 1),
        Interval.WEEK: ("weeks", 1),
        Interval.MONTH: ("months", 1),
    }
    
    def __init__(self, config: DataProviderConfig):
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None
        self._instrument_cache: Dict[str, Instrument] = {}
        self._fo_stocks_cache: Optional[List[str]] = None
        # Rate limiting semaphore for concurrent requests
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)
        self._last_request_time = 0.0
        self._request_lock = asyncio.Lock()
        
    async def _rate_limited_request(self):
        """Acquire rate limit slot and ensure minimum spacing between requests."""
        async with self._semaphore:
            async with self._request_lock:
                now = asyncio.get_event_loop().time() * 1000  # ms
                elapsed = now - self._last_request_time
                if elapsed < self.REQUEST_SPACING_MS:
                    await asyncio.sleep((self.REQUEST_SPACING_MS - elapsed) / 1000)
                self._last_request_time = asyncio.get_event_loop().time() * 1000
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            )
        return self._session
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API headers."""
        headers = {"Accept": "application/json"}
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"
        return headers
    
    async def authenticate(self) -> bool:
        """
        Load access token from file and verify it.
        
        Note: Upstox uses OAuth2. Token generation is done via web flow.
        This method loads an existing token from file.
        """
        try:
            # Try loading from token file
            if self.config.token_file:
                token_path = Path(self.config.token_file)
                if token_path.exists():
                    with open(token_path, 'r') as f:
                        token_data = json.load(f)
                    self.config.access_token = token_data.get("access_token")
            
            if not self.config.access_token:
                logger.error("No access token available")
                return False
            
            # Verify token by making a test API call
            session = await self._get_session()
            async with session.get(
                f"{self.BASE_URL}/v2/user/profile",
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    user_id = data.get("data", {}).get("user_id", "unknown")
                    logger.info(f"Authenticated as user: {user_id}")
                    self._authenticated = True
                    return True
                else:
                    logger.error(f"Authentication failed: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def get_instrument_master(self) -> List[Instrument]:
        """
        Download complete instrument master from Upstox.
        
        Downloads from:
        - NSE Equity
        - BSE Equity
        - NSE F&O (NFO)
        """
        instruments = []
        exchanges = ["NSE", "BSE", "NFO"]
        
        session = await self._get_session()
        
        for exchange in exchanges:
            try:
                url = f"{self.INSTRUMENT_MASTER_URL}/{exchange}.json.gz"
                logger.info(f"Downloading {exchange} instruments from {url}")
                
                async with session.get(url) as response:
                    if response.status == 200:
                        import gzip
                        import io
                        
                        content = await response.read()
                        
                        # Decompress gzip
                        with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                            data = json.loads(f.read().decode('utf-8'))
                        
                        for item in data:
                            instrument = self._parse_instrument(item, exchange)
                            if instrument:
                                instruments.append(instrument)
                                self._instrument_cache[instrument.provider_token] = instrument
                        
                        logger.info(f"Loaded {len(data)} instruments from {exchange}")
                    else:
                        logger.error(f"Failed to download {exchange} instruments: {response.status}")
                        
            except Exception as e:
                logger.error(f"Error downloading {exchange} instruments: {e}")
        
        return instruments
    
    def _parse_instrument(self, data: Dict[str, Any], exchange_str: str) -> Optional[Instrument]:
        """Parse Upstox instrument data to Instrument object."""
        try:
            # Determine instrument type
            segment = data.get("segment", "")
            instrument_type = InstrumentType.EQUITY
            
            if "FUT" in data.get("instrument_type", ""):
                instrument_type = InstrumentType.FUTURES
            elif "OPT" in data.get("instrument_type", "") or "CE" in data.get("instrument_type", "") or "PE" in data.get("instrument_type", ""):
                instrument_type = InstrumentType.OPTIONS
            elif data.get("instrument_type") == "INDEX":
                instrument_type = InstrumentType.INDEX
            
            # Determine exchange
            exchange_map = {
                "NSE": Exchange.NSE,
                "BSE": Exchange.BSE,
                "NFO": Exchange.NFO,
                "MCX": Exchange.MCX,
            }
            exchange = exchange_map.get(exchange_str, Exchange.NSE)
            
            # Parse expiry for derivatives
            expiry_date = None
            if data.get("expiry"):
                try:
                    expiry_date = datetime.fromtimestamp(data["expiry"] / 1000).date()
                except:
                    pass
            
            return Instrument(
                symbol=data.get("trading_symbol", ""),
                name=data.get("name", data.get("trading_symbol", "")),
                instrument_type=instrument_type,
                exchange=exchange,
                isin=data.get("isin"),
                lot_size=data.get("lot_size", 1),
                tick_size=data.get("tick_size", 0.05),
                provider_token=data.get("instrument_key", ""),
                provider_symbol=data.get("trading_symbol", ""),
                underlying_symbol=data.get("underlying_symbol"),
                expiry_date=expiry_date,
                strike_price=data.get("strike_price"),
                option_type=data.get("option_type"),
            )
        except Exception as e:
            logger.debug(f"Error parsing instrument: {e}")
            return None
    
    async def get_fo_stocks(self) -> List[str]:
        """
        Get list of F&O enabled stocks.
        
        Extracts from NFO futures instruments' underlying symbols.
        """
        if self._fo_stocks_cache:
            return self._fo_stocks_cache
        
        session = await self._get_session()
        fo_stocks = set()
        
        try:
            url = f"{self.INSTRUMENT_MASTER_URL}/NSE_FO.json.gz"
            
            async with session.get(url) as response:
                if response.status == 200:
                    import gzip
                    import io
                    
                    content = await response.read()
                    
                    with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                        data = json.loads(f.read().decode('utf-8'))
                    
                    # Extract unique underlying symbols from futures
                    for item in data:
                        if item.get("instrument_type") == "FUT":
                            underlying = item.get("underlying_symbol", "")
                            # Filter out index futures (like NIFTY, BANKNIFTY)
                            if underlying and underlying not in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]:
                                fo_stocks.add(underlying)
                    
                    self._fo_stocks_cache = sorted(list(fo_stocks))
                    logger.info(f"Found {len(self._fo_stocks_cache)} F&O enabled stocks")
                    return self._fo_stocks_cache
                else:
                    logger.error(f"Failed to get F&O stocks: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting F&O stocks: {e}")
            return []
    
    async def get_historical_candles(
        self,
        instrument: Instrument,
        interval: Interval,
        from_date: date,
        to_date: date,
    ) -> List[Candle]:
        """
        Get historical candle data using V3 API.
        
        V3 API endpoint format:
        /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}
        """
        import calendar
        
        session = await self._get_session()
        all_candles = []
        
        # Get interval parameters (fallback uses plural "minutes" for V3 API)
        unit, interval_value = self.INTERVAL_MAP.get(interval, ("minutes", 1))
        
        # URL encode the instrument key
        instrument_key = quote(instrument.provider_token, safe='')
        
        # Use calendar month chunks to avoid February issues
        current_from = from_date
        while current_from < to_date:
            # Get last day of current month
            _, last_day = calendar.monthrange(current_from.year, current_from.month)
            month_end = date(current_from.year, current_from.month, last_day)
            current_to = min(month_end, to_date)
            
            # V3 API endpoint
            url = (
                f"{self.BASE_URL}/v3/historical-candle/"
                f"{instrument_key}/{unit}/{interval_value}/"
                f"{current_to.strftime('%Y-%m-%d')}/{current_from.strftime('%Y-%m-%d')}"
            )
            
            logger.debug(f"Fetching: {current_from} to {current_to}")
            
            try:
                async with session.get(url, headers=self._get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        candle_data = data.get("data", {}).get("candles", [])
                        
                        for candle_row in candle_data:
                            # Upstox format: [timestamp, open, high, low, close, volume, oi]
                            try:
                                timestamp = datetime.fromisoformat(candle_row[0].replace('Z', '+00:00'))
                                all_candles.append(Candle(
                                    timestamp=timestamp,
                                    open=float(candle_row[1]),
                                    high=float(candle_row[2]),
                                    low=float(candle_row[3]),
                                    close=float(candle_row[4]),
                                    volume=int(candle_row[5]),
                                    oi=int(candle_row[6]) if len(candle_row) > 6 else 0,
                                ))
                            except Exception as e:
                                logger.debug(f"Error parsing candle: {e}")
                                continue
                        
                        logger.debug(f"Got {len(candle_data)} candles for {current_from} to {current_to}")
                    else:
                        error_text = await response.text()
                        logger.warning(f"API error {response.status} for {current_from} to {current_to}: {error_text[:100]}")
                        
            except Exception as e:
                logger.error(f"Error fetching candles: {e}")
            
            # Move to next chunk
            current_from = current_to + timedelta(days=1)
            
            # Rate limiting (100ms = 10/sec, limit is 1000/min)
            await asyncio.sleep(0.1)
        
        # Sort by timestamp
        all_candles.sort(key=lambda c: c.timestamp)
        return all_candles
    
    async def get_indices(self) -> List[Instrument]:
        """Get list of major indices."""
        # Major NSE indices
        indices = [
            Instrument(
                symbol="NIFTY 50",
                name="Nifty 50",
                instrument_type=InstrumentType.INDEX,
                exchange=Exchange.NSE,
                provider_token="NSE_INDEX|Nifty 50",
            ),
            Instrument(
                symbol="NIFTY BANK",
                name="Nifty Bank",
                instrument_type=InstrumentType.INDEX,
                exchange=Exchange.NSE,
                provider_token="NSE_INDEX|Nifty Bank",
            ),
            Instrument(
                symbol="NIFTY FIN SERVICE",
                name="Nifty Financial Services",
                instrument_type=InstrumentType.INDEX,
                exchange=Exchange.NSE,
                provider_token="NSE_INDEX|Nifty Fin Service",
            ),
            Instrument(
                symbol="NIFTY IT",
                name="Nifty IT",
                instrument_type=InstrumentType.INDEX,
                exchange=Exchange.NSE,
                provider_token="NSE_INDEX|Nifty IT",
            ),
            Instrument(
                symbol="NIFTY MIDCAP 50",
                name="Nifty Midcap 50",
                instrument_type=InstrumentType.INDEX,
                exchange=Exchange.NSE,
                provider_token="NSE_INDEX|Nifty Midcap 50",
            ),
        ]
        return indices
    
    def get_provider_symbol(self, symbol: str, exchange: Exchange) -> str:
        """Convert standard symbol to Upstox format."""
        exchange_prefix = {
            Exchange.NSE: "NSE_EQ",
            Exchange.BSE: "BSE_EQ",
            Exchange.NFO: "NSE_FO",
        }
        prefix = exchange_prefix.get(exchange, "NSE_EQ")
        return f"{prefix}|{symbol}"
    
    def get_provider_instrument_key(self, instrument: Instrument) -> str:
        """Get Upstox instrument key."""
        return instrument.provider_token or self.get_provider_symbol(
            instrument.symbol, instrument.exchange
        )
    
    def get_data_availability(self, interval: Interval) -> Dict[str, Any]:
        """Get data availability info for an interval."""
        return self.DATA_LIMITS.get(interval, {
            "max_days": 30,
            "start_date": date(2022, 1, 1)
        })
    
    # =========================================================================
    # Expired Instruments APIs (for historical F&O data)
    # =========================================================================
    
    async def get_expiries(self, instrument_key: str) -> List[str]:
        """
        Get all available expiry dates for an instrument.
        Returns up to 6 months of historical expiries.
        
        Args:
            instrument_key: e.g., 'NSE_INDEX|Nifty 50', 'NSE_EQ|RELIANCE'
        """
        session = await self._get_session()
        encoded_key = quote(instrument_key, safe='')
        url = f"{self.BASE_URL}/v2/expired-instruments/expiries?instrument_key={encoded_key}"
        
        for attempt in range(5):
            async with session.get(url, headers=self._get_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    expiries = data.get("data", [])
                    logger.info(f"Found {len(expiries)} expiries for {instrument_key}")
                    return expiries
                elif response.status == 429:
                    wait_time = 1 * (2 ** attempt)  # 1s, 2s, 4s, 8s, 16s
                    logger.warning(f"Rate limited on expiries, waiting {wait_time}s (attempt {attempt+1}/5)")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    error = await response.text()
                    logger.error(f"Failed to get expiries: {response.status} - {error}")
                    return []
        await asyncio.sleep(5)  # Short cooldown after max retries
        return []
    
    async def get_expired_option_contracts(
        self, instrument_key: str, expiry_date: str, max_retries: int = 5
    ) -> List[Dict]:
        """
        Get expired option contracts for an underlying on a specific expiry date.
        
        Args:
            instrument_key: e.g., 'NSE_INDEX|Nifty 50'
            expiry_date: Format 'YYYY-MM-DD'
            max_retries: Maximum retry attempts for rate limiting
        """
        session = await self._get_session()
        encoded_key = quote(instrument_key, safe='')
        url = f"{self.BASE_URL}/v2/expired-instruments/option/contract?instrument_key={encoded_key}&expiry_date={expiry_date}"
        
        for attempt in range(max_retries):
            async with session.get(url, headers=self._get_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    contracts = data.get("data", [])
                    logger.debug(f"Found {len(contracts)} option contracts for {instrument_key} expiry {expiry_date}")
                    return contracts
                elif response.status == 429:
                    wait_time = 1 * (2 ** attempt)  # 1s, 2s, 4s, 8s, 16s
                    logger.warning(f"Rate limited on option contracts, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    error = await response.text()
                    logger.error(f"Failed to get option contracts: {response.status} - {error}")
                    return []
        
        logger.error(f"Max retries exceeded for option contracts {instrument_key}")
        await asyncio.sleep(5)  # Short cooldown after max retries
        return []
    
    async def get_expired_future_contracts(
        self, instrument_key: str, expiry_date: str, max_retries: int = 5
    ) -> List[Dict]:
        """
        Get expired future contracts for an underlying on a specific expiry date.
        
        Args:
            instrument_key: e.g., 'NSE_INDEX|Nifty 50'
            expiry_date: Format 'YYYY-MM-DD'
            max_retries: Maximum retry attempts for rate limiting
        """
        session = await self._get_session()
        encoded_key = quote(instrument_key, safe='')
        url = f"{self.BASE_URL}/v2/expired-instruments/future/contract?instrument_key={encoded_key}&expiry_date={expiry_date}"
        
        for attempt in range(max_retries):
            async with session.get(url, headers=self._get_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    contracts = data.get("data", [])
                    logger.debug(f"Found {len(contracts)} future contracts for {instrument_key} expiry {expiry_date}")
                    return contracts
                elif response.status == 429:
                    # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                    wait_time = 1 * (2 ** attempt)
                    logger.warning(f"Rate limited on future contracts, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    error = await response.text()
                    logger.error(f"Failed to get future contracts: {response.status} - {error}")
                    return []
        
        logger.error(f"Max retries exceeded for future contracts {instrument_key}")
        await asyncio.sleep(5)  # Short cooldown after max retries
        return []
    
    async def get_expired_historical_candles(
        self,
        expired_instrument_key: str,
        interval: Interval,
        from_date: date,
        to_date: date,
        max_retries: int = 5,
    ) -> List[Candle]:
        """
        Get historical candle data for expired F&O contracts.
        
        Args:
            expired_instrument_key: e.g., 'NSE_FO|73507|24-04-2025' (includes expiry date)
            interval: Candle interval
            from_date: Start date
            to_date: End date
            max_retries: Maximum retry attempts for rate limiting
        """
        session = await self._get_session()
        
        # Map interval to API format
        interval_map = {
            Interval.MINUTE_1: "1minute",
            Interval.MINUTE_3: "3minute",
            Interval.MINUTE_5: "5minute",
            Interval.MINUTE_15: "15minute",
            Interval.MINUTE_30: "30minute",
            Interval.DAY: "day",
        }
        interval_str = interval_map.get(interval, "1minute")
        
        # Validate key format before making request
        if not expired_instrument_key or '|' not in expired_instrument_key:
            logger.error(f"Invalid instrument key format: {expired_instrument_key}")
            return []
        
        # Double-check key doesn't have empty segments
        parts = expired_instrument_key.split('|')
        if any(not p.strip() for p in parts):
            logger.error(f"Instrument key has empty segment: {expired_instrument_key}")
            return []
        
        encoded_key = quote(expired_instrument_key, safe='')
        url = (
            f"{self.BASE_URL}/v2/expired-instruments/historical-candle/"
            f"{encoded_key}/{interval_str}/"
            f"{to_date.strftime('%Y-%m-%d')}/{from_date.strftime('%Y-%m-%d')}"
        )
        
        all_candles = []
        
        for attempt in range(max_retries):
            async with session.get(url, headers=self._get_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    candle_data = data.get("data", {}).get("candles", [])
                    
                    for candle_row in candle_data:
                        try:
                            timestamp = datetime.fromisoformat(candle_row[0].replace('Z', '+00:00'))
                            all_candles.append(Candle(
                                timestamp=timestamp,
                                open=float(candle_row[1]),
                                high=float(candle_row[2]),
                                low=float(candle_row[3]),
                                close=float(candle_row[4]),
                                volume=int(candle_row[5]) if len(candle_row) > 5 else 0,
                                oi=int(candle_row[6]) if len(candle_row) > 6 else 0,
                            ))
                        except (IndexError, ValueError) as e:
                            logger.warning(f"Skipping malformed candle: {e}")
                            continue
                    return all_candles
                elif response.status == 429:
                    # Rate limited - exponential backoff: 1s, 2s, 4s, 8s, 16s
                    wait_time = 1 * (2 ** attempt)
                    logger.warning(f"Rate limited on candles, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                elif response.status == 400:
                    # Bad request - likely malformed key, don't retry
                    error = await response.text()
                    logger.error(f"Bad request for key {expired_instrument_key}: {error[:100]}")
                    return []
                else:
                    error = await response.text()
                    logger.error(f"Failed to get expired candles: {response.status} - {error}")
                    return []
        
        logger.error(f"Max retries exceeded for {expired_instrument_key}")
        await asyncio.sleep(5)  # Short cooldown after max retries
        return all_candles
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


# Convenience function to create provider
def create_upstox_provider(token_file: str = "data/upstox_token.json") -> UpstoxDataProvider:
    """Create an Upstox data provider with default config."""
    config = DataProviderConfig(
        provider_name="upstox",
        token_file=token_file,
        rate_limit_per_minute=1000,
        max_retries=3,
        timeout_seconds=30,
    )
    return UpstoxDataProvider(config)
