"""
Upstox Enhanced Service
KeepGaining Trading Platform

Comprehensive Upstox API service leveraging their full SDK capabilities:
- Real-time Option Greeks via API and WebSocket
- Portfolio streaming (orders, positions, holdings)
- Option chain with Greeks
- Market data streaming with multiple modes
- High-throughput batch APIs (500 instruments/call)

This service wraps the official Upstox SDK and provides:
- Clean async interface
- Event bus integration
- Automatic reconnection
- Rate limiting
- Caching for expensive operations
"""

import asyncio
import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple
from enum import Enum
import json
import threading
from functools import lru_cache

from loguru import logger

# Add upstox SDK to path
UPSTOX_SDK_PATH = Path(__file__).parent.parent.parent / "upstox-python-master"
if UPSTOX_SDK_PATH.exists():
    sys.path.insert(0, str(UPSTOX_SDK_PATH))

# Import Upstox SDK components
try:
    from upstox_client import ApiClient, Configuration
    from upstox_client.api import (
        MarketQuoteV3Api,
        OptionsApi,
        HistoryApi,
        HistoryV3Api,
        PortfolioApi,
        OrderApi,
        UserApi,
        MarketHolidaysAndTimingsApi,
    )
    from upstox_client.feeder import (
        MarketDataStreamerV3,
        PortfolioDataStreamer,
    )
    UPSTOX_SDK_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Upstox SDK not fully available: {e}")
    UPSTOX_SDK_AVAILABLE = False

from app.core.config import settings
from app.core.events import EventBus, EventType, get_event_bus


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class OptionGreeks:
    """Option Greeks data."""
    instrument_key: str
    symbol: str
    ltp: float
    iv: float  # Implied Volatility
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float = 0.0
    volume: int = 0
    oi: float = 0.0
    close_price: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_key": self.instrument_key,
            "symbol": self.symbol,
            "ltp": self.ltp,
            "iv": self.iv,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "rho": self.rho,
            "volume": self.volume,
            "oi": self.oi,
            "close_price": self.close_price,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OptionChainStrike:
    """Single strike in option chain."""
    strike_price: float
    expiry_date: date
    
    # Call option data
    ce_instrument_key: Optional[str] = None
    ce_ltp: float = 0.0
    ce_iv: float = 0.0
    ce_delta: float = 0.0
    ce_gamma: float = 0.0
    ce_theta: float = 0.0
    ce_vega: float = 0.0
    ce_oi: float = 0.0
    ce_oi_change: float = 0.0
    ce_volume: int = 0
    ce_bid: float = 0.0
    ce_ask: float = 0.0
    
    # Put option data
    pe_instrument_key: Optional[str] = None
    pe_ltp: float = 0.0
    pe_iv: float = 0.0
    pe_delta: float = 0.0
    pe_gamma: float = 0.0
    pe_theta: float = 0.0
    pe_vega: float = 0.0
    pe_oi: float = 0.0
    pe_oi_change: float = 0.0
    pe_volume: int = 0
    pe_bid: float = 0.0
    pe_ask: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strike_price": self.strike_price,
            "expiry_date": self.expiry_date.isoformat(),
            "ce": {
                "instrument_key": self.ce_instrument_key,
                "ltp": self.ce_ltp,
                "iv": self.ce_iv,
                "delta": self.ce_delta,
                "gamma": self.ce_gamma,
                "theta": self.ce_theta,
                "vega": self.ce_vega,
                "oi": self.ce_oi,
                "oi_change": self.ce_oi_change,
                "volume": self.ce_volume,
                "bid": self.ce_bid,
                "ask": self.ce_ask,
            },
            "pe": {
                "instrument_key": self.pe_instrument_key,
                "ltp": self.pe_ltp,
                "iv": self.pe_iv,
                "delta": self.pe_delta,
                "gamma": self.pe_gamma,
                "theta": self.pe_theta,
                "vega": self.pe_vega,
                "oi": self.pe_oi,
                "oi_change": self.pe_oi_change,
                "volume": self.pe_volume,
                "bid": self.pe_bid,
                "ask": self.pe_ask,
            },
        }


@dataclass
class OptionChain:
    """Full option chain for an underlying."""
    underlying_key: str
    underlying_symbol: str
    underlying_ltp: float
    expiry_date: date
    strikes: List[OptionChainStrike] = field(default_factory=list)
    atm_strike: float = 0.0
    total_ce_oi: float = 0.0
    total_pe_oi: float = 0.0
    pcr: float = 0.0  # Put-Call Ratio
    max_pain: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "underlying_key": self.underlying_key,
            "underlying_symbol": self.underlying_symbol,
            "underlying_ltp": self.underlying_ltp,
            "expiry_date": self.expiry_date.isoformat(),
            "atm_strike": self.atm_strike,
            "total_ce_oi": self.total_ce_oi,
            "total_pe_oi": self.total_pe_oi,
            "pcr": self.pcr,
            "max_pain": self.max_pain,
            "timestamp": self.timestamp.isoformat(),
            "strikes": [s.to_dict() for s in self.strikes],
        }


@dataclass
class MarketQuote:
    """Market quote with OHLC and Greeks."""
    instrument_key: str
    symbol: str
    ltp: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    oi: float = 0.0
    change: float = 0.0
    change_percent: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    # Greeks (for options)
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_key": self.instrument_key,
            "symbol": self.symbol,
            "ltp": self.ltp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "oi": self.oi,
            "change": self.change,
            "change_percent": self.change_percent,
            "bid": self.bid,
            "ask": self.ask,
            "iv": self.iv,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PortfolioUpdate:
    """Portfolio update from streaming."""
    update_type: str  # "order", "position", "holding"
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Upstox Enhanced Service
# =============================================================================

class UpstoxEnhancedService:
    """
    Enhanced Upstox service with full SDK integration.
    
    Features:
    - Option Greeks API (500 instruments/batch)
    - Full Option Chain with Greeks
    - Portfolio streaming (orders, positions, holdings)
    - Market data streaming with modes (LTPC, Full, Option Greeks)
    - Historical data with v3 API
    - Market status and holidays
    
    Usage:
        service = UpstoxEnhancedService(access_token="...")
        await service.initialize()
        
        # Get option Greeks
        greeks = await service.get_option_greeks(["NSE_FO|NIFTY24DEC24000CE"])
        
        # Get full option chain
        chain = await service.get_option_chain("NSE_INDEX|Nifty 50", "2024-12-26")
        
        # Start market data streaming
        await service.start_market_stream(
            instruments=["NSE_INDEX|Nifty 50"],
            mode="option_greeks",
            on_tick=my_callback
        )
    """
    
    BATCH_SIZE = 500  # Max instruments per API call
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        publish_to_event_bus: bool = True,
    ):
        """
        Initialize Upstox enhanced service.
        
        Args:
            access_token: Upstox API access token
            publish_to_event_bus: Whether to publish events to event bus
        """
        if not UPSTOX_SDK_AVAILABLE:
            raise ImportError("Upstox SDK not available. Check installation.")
        
        self._access_token = access_token
        self._publish_to_event_bus = publish_to_event_bus
        
        # API client
        self._api_client: Optional[ApiClient] = None
        self._config: Optional[Configuration] = None
        
        # API instances
        self._market_quote_api: Optional[MarketQuoteV3Api] = None
        self._options_api: Optional[OptionsApi] = None
        self._history_api: Optional[HistoryApi] = None
        self._history_v3_api: Optional[HistoryV3Api] = None
        self._portfolio_api: Optional[PortfolioApi] = None
        self._order_api: Optional[OrderApi] = None
        self._user_api: Optional[UserApi] = None
        self._market_api: Optional[MarketHolidaysAndTimingsApi] = None
        
        # Streamers
        self._market_streamer: Optional[MarketDataStreamerV3] = None
        self._portfolio_streamer: Optional[PortfolioDataStreamer] = None
        
        # Event bus
        self._event_bus: Optional[EventBus] = None
        
        # Callbacks
        self._on_tick: Optional[Callable] = None
        self._on_portfolio_update: Optional[Callable] = None
        
        # State
        self._initialized = False
        self._market_stream_active = False
        self._portfolio_stream_active = False
        
        # Cache
        self._expiry_cache: Dict[str, List[date]] = {}
        self._cache_timestamp: Dict[str, datetime] = {}
        
        # Stats
        self._api_call_count = 0
        self._error_count = 0
    
    async def initialize(self) -> bool:
        """
        Initialize the service with API clients.
        
        Returns:
            True if initialization successful.
        """
        if not self._access_token:
            logger.error("Access token required for initialization")
            return False
        
        try:
            # Configure API client
            self._config = Configuration()
            self._config.access_token = self._access_token
            self._api_client = ApiClient(self._config)
            
            # Initialize API instances
            self._market_quote_api = MarketQuoteV3Api(self._api_client)
            self._options_api = OptionsApi(self._api_client)
            self._history_api = HistoryApi(self._api_client)
            self._history_v3_api = HistoryV3Api(self._api_client)
            self._portfolio_api = PortfolioApi(self._api_client)
            self._order_api = OrderApi(self._api_client)
            self._user_api = UserApi(self._api_client)
            self._market_api = MarketHolidaysAndTimingsApi(self._api_client)
            
            # Get event bus
            if self._publish_to_event_bus:
                try:
                    self._event_bus = await get_event_bus()
                except Exception as e:
                    logger.warning(f"Event bus not available: {e}")
            
            self._initialized = True
            logger.info("✓ Upstox Enhanced Service initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Upstox service: {e}")
            return False
    
    def set_access_token(self, token: str) -> None:
        """Update the access token."""
        self._access_token = token
        if self._config:
            self._config.access_token = token
    
    # =========================================================================
    # Option Greeks APIs
    # =========================================================================
    
    async def get_option_greeks(
        self,
        instrument_keys: List[str],
    ) -> Dict[str, OptionGreeks]:
        """
        Get real-time option Greeks for multiple instruments.
        
        Uses the v3 Option Greeks API which returns:
        - IV (Implied Volatility)
        - Delta, Gamma, Theta, Vega
        - LTP, Volume, OI
        
        Args:
            instrument_keys: List of option instrument keys
                (e.g., ["NSE_FO|NIFTY24DEC24000CE", "NSE_FO|NIFTY24DEC24000PE"])
            
        Returns:
            Dictionary mapping instrument key to OptionGreeks.
        """
        if not self._initialized:
            logger.error("Service not initialized")
            return {}
        
        results: Dict[str, OptionGreeks] = {}
        
        # Process in batches
        for i in range(0, len(instrument_keys), self.BATCH_SIZE):
            batch = instrument_keys[i:i + self.BATCH_SIZE]
            
            try:
                self._api_call_count += 1
                response = self._market_quote_api.get_market_quote_option_greek(
                    instrument_key=",".join(batch)
                )
                
                if not response or response.status != "success":
                    continue
                
                data = response.data or {}
                
                for key, greek_data in data.items():
                    try:
                        results[key] = OptionGreeks(
                            instrument_key=key,
                            symbol=key.split("|")[-1] if "|" in key else key,
                            ltp=float(greek_data.last_price or 0),
                            iv=float(greek_data.iv or 0),
                            delta=float(greek_data.delta or 0),
                            gamma=float(greek_data.gamma or 0),
                            theta=float(greek_data.theta or 0),
                            vega=float(greek_data.vega or 0),
                            volume=int(greek_data.volume or 0),
                            oi=float(greek_data.oi or 0),
                            close_price=float(greek_data.cp or 0),
                        )
                    except Exception as e:
                        logger.error(f"Error parsing Greeks for {key}: {e}")
                
            except Exception as e:
                logger.error(f"Error fetching Greeks batch: {e}")
                self._error_count += 1
        
        return results
    
    async def get_option_chain(
        self,
        underlying_key: str,
        expiry_date: str,
    ) -> Optional[OptionChain]:
        """
        Get full option chain with Greeks for an underlying.
        
        Args:
            underlying_key: Underlying instrument key
                (e.g., "NSE_INDEX|Nifty 50", "NSE_EQ|INE002A01018")
            expiry_date: Expiry date in YYYY-MM-DD format
            
        Returns:
            OptionChain with all strikes and Greeks.
        """
        if not self._initialized:
            logger.error("Service not initialized")
            return None
        
        try:
            self._api_call_count += 1
            response = self._options_api.get_put_call_option_chain(
                instrument_key=underlying_key,
                expiry_date=expiry_date,
            )
            
            if not response or response.status != "success":
                logger.error(f"Option chain failed: {response}")
                return None
            
            chain_data = response.data or []
            
            # Parse strikes
            strikes: List[OptionChainStrike] = []
            total_ce_oi = 0.0
            total_pe_oi = 0.0
            
            for item in chain_data:
                strike = OptionChainStrike(
                    strike_price=float(item.strike_price or 0),
                    expiry_date=date.fromisoformat(expiry_date),
                )
                
                # Call option
                if item.call_options:
                    call = item.call_options
                    market = call.market_data or {}
                    greeks = call.option_greeks or {}
                    
                    strike.ce_instrument_key = call.instrument_key
                    strike.ce_ltp = float(market.ltp or 0)
                    strike.ce_oi = float(market.oi or 0)
                    strike.ce_volume = int(market.volume or 0)
                    strike.ce_bid = float(market.bid_price or 0)
                    strike.ce_ask = float(market.ask_price or 0)
                    
                    strike.ce_iv = float(greeks.iv or 0)
                    strike.ce_delta = float(greeks.delta or 0)
                    strike.ce_gamma = float(greeks.gamma or 0)
                    strike.ce_theta = float(greeks.theta or 0)
                    strike.ce_vega = float(greeks.vega or 0)
                    
                    total_ce_oi += strike.ce_oi
                
                # Put option
                if item.put_options:
                    put = item.put_options
                    market = put.market_data or {}
                    greeks = put.option_greeks or {}
                    
                    strike.pe_instrument_key = put.instrument_key
                    strike.pe_ltp = float(market.ltp or 0)
                    strike.pe_oi = float(market.oi or 0)
                    strike.pe_volume = int(market.volume or 0)
                    strike.pe_bid = float(market.bid_price or 0)
                    strike.pe_ask = float(market.ask_price or 0)
                    
                    strike.pe_iv = float(greeks.iv or 0)
                    strike.pe_delta = float(greeks.delta or 0)
                    strike.pe_gamma = float(greeks.gamma or 0)
                    strike.pe_theta = float(greeks.theta or 0)
                    strike.pe_vega = float(greeks.vega or 0)
                    
                    total_pe_oi += strike.pe_oi
                
                strikes.append(strike)
            
            # Sort by strike price
            strikes.sort(key=lambda x: x.strike_price)
            
            # Get underlying LTP
            underlying_ltp = await self._get_underlying_ltp(underlying_key)
            
            # Find ATM strike
            atm_strike = min(strikes, key=lambda x: abs(x.strike_price - underlying_ltp)).strike_price if strikes else 0
            
            # Calculate PCR
            pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
            
            # Calculate max pain (simplified)
            max_pain = self._calculate_max_pain(strikes, underlying_ltp)
            
            return OptionChain(
                underlying_key=underlying_key,
                underlying_symbol=underlying_key.split("|")[-1] if "|" in underlying_key else underlying_key,
                underlying_ltp=underlying_ltp,
                expiry_date=date.fromisoformat(expiry_date),
                strikes=strikes,
                atm_strike=atm_strike,
                total_ce_oi=total_ce_oi,
                total_pe_oi=total_pe_oi,
                pcr=pcr,
                max_pain=max_pain,
            )
            
        except Exception as e:
            logger.error(f"Error fetching option chain: {e}")
            self._error_count += 1
            return None
    
    def _calculate_max_pain(
        self,
        strikes: List[OptionChainStrike],
        spot: float,
    ) -> float:
        """Calculate max pain strike."""
        if not strikes:
            return 0.0
        
        min_pain = float('inf')
        max_pain_strike = strikes[len(strikes) // 2].strike_price
        
        for test_strike in strikes:
            pain = 0.0
            strike_price = test_strike.strike_price
            
            for s in strikes:
                # CE writers pain
                if s.strike_price < strike_price:
                    pain += s.ce_oi * (strike_price - s.strike_price)
                # PE writers pain
                if s.strike_price > strike_price:
                    pain += s.pe_oi * (s.strike_price - strike_price)
            
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = strike_price
        
        return max_pain_strike
    
    async def get_option_expiries(
        self,
        underlying_key: str,
    ) -> List[date]:
        """
        Get available expiry dates for an underlying.
        
        Args:
            underlying_key: Underlying instrument key
            
        Returns:
            List of available expiry dates.
        """
        if not self._initialized:
            return []
        
        # Check cache
        cache_key = f"expiries_{underlying_key}"
        if cache_key in self._expiry_cache:
            cache_time = self._cache_timestamp.get(cache_key)
            if cache_time and (datetime.now(timezone.utc) - cache_time).seconds < 3600:
                return self._expiry_cache[cache_key]
        
        try:
            self._api_call_count += 1
            response = self._options_api.get_option_contracts(
                instrument_key=underlying_key
            )
            
            if not response or response.status != "success":
                return []
            
            contracts = response.data or []
            
            # Extract unique expiries
            expiries: Set[date] = set()
            for contract in contracts:
                if contract.expiry:
                    try:
                        exp_date = date.fromisoformat(contract.expiry)
                        expiries.add(exp_date)
                    except Exception:
                        pass
            
            result = sorted(list(expiries))
            
            # Update cache
            self._expiry_cache[cache_key] = result
            self._cache_timestamp[cache_key] = datetime.now(timezone.utc)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching expiries: {e}")
            return []
    
    async def _get_underlying_ltp(self, instrument_key: str) -> float:
        """Get LTP for underlying instrument."""
        try:
            response = self._market_quote_api.get_ltp(
                instrument_key=instrument_key
            )
            
            if response and response.status == "success" and response.data:
                quote = response.data.get(instrument_key, {})
                return float(quote.last_price or 0)
        except Exception as e:
            logger.error(f"Error getting LTP for {instrument_key}: {e}")
        
        return 0.0
    
    # =========================================================================
    # Market Quote APIs
    # =========================================================================
    
    async def get_market_quotes(
        self,
        instrument_keys: List[str],
        include_greeks: bool = False,
    ) -> Dict[str, MarketQuote]:
        """
        Get market quotes for multiple instruments.
        
        Args:
            instrument_keys: List of instrument keys
            include_greeks: Whether to include option Greeks (for options)
            
        Returns:
            Dictionary mapping instrument key to MarketQuote.
        """
        if not self._initialized:
            return {}
        
        results: Dict[str, MarketQuote] = {}
        
        # Fetch OHLC quotes
        for i in range(0, len(instrument_keys), self.BATCH_SIZE):
            batch = instrument_keys[i:i + self.BATCH_SIZE]
            
            try:
                self._api_call_count += 1
                response = self._market_quote_api.get_market_quote_ohlc(
                    interval="1d",
                    instrument_key=",".join(batch)
                )
                
                if not response or response.status != "success":
                    continue
                
                data = response.data or {}
                
                for key, quote_data in data.items():
                    try:
                        ohlc = quote_data.ohlc or {}
                        
                        results[key] = MarketQuote(
                            instrument_key=key,
                            symbol=key.split("|")[-1] if "|" in key else key,
                            ltp=float(quote_data.last_price or 0),
                            open=float(ohlc.open or 0),
                            high=float(ohlc.high or 0),
                            low=float(ohlc.low or 0),
                            close=float(ohlc.close or 0),
                            volume=int(quote_data.volume or 0),
                        )
                    except Exception as e:
                        logger.error(f"Error parsing quote for {key}: {e}")
                
            except Exception as e:
                logger.error(f"Error fetching quotes batch: {e}")
                self._error_count += 1
        
        # Fetch Greeks if requested
        if include_greeks:
            option_keys = [k for k in instrument_keys if "FO|" in k]
            if option_keys:
                greeks = await self.get_option_greeks(option_keys)
                for key, greek in greeks.items():
                    if key in results:
                        results[key].iv = greek.iv
                        results[key].delta = greek.delta
                        results[key].gamma = greek.gamma
                        results[key].theta = greek.theta
                        results[key].vega = greek.vega
                        results[key].oi = greek.oi
        
        return results
    
    # =========================================================================
    # Market Data Streaming
    # =========================================================================
    
    async def start_market_stream(
        self,
        instruments: List[str],
        mode: str = "full",
        on_tick: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
    ) -> bool:
        """
        Start real-time market data streaming.
        
        Modes:
        - "ltpc": Last Traded Price & Change (lightest)
        - "full": Full market data with depth
        - "option_greeks": Option Greeks with LTPC
        - "full_d30": Full data with 30-level depth
        
        Args:
            instruments: List of instrument keys to subscribe
            mode: Data mode (ltpc, full, option_greeks, full_d30)
            on_tick: Callback for tick data
            
        Returns:
            True if stream started successfully.
        """
        if not self._initialized:
            return False
        
        self._on_tick = on_tick
        
        try:
            # Create streamer
            self._market_streamer = MarketDataStreamerV3(
                api_client=self._api_client,
                instrumentKeys=instruments,
                mode=mode,
            )
            
            # Set up event handlers
            self._market_streamer.on("open", self._on_market_stream_open)
            self._market_streamer.on("message", self._on_market_stream_message)
            self._market_streamer.on("error", self._on_market_stream_error)
            self._market_streamer.on("close", self._on_market_stream_close)
            
            # Connect
            self._market_streamer.connect()
            self._market_stream_active = True
            
            logger.info(f"✓ Market stream started: {len(instruments)} instruments, mode={mode}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start market stream: {e}")
            return False
    
    async def stop_market_stream(self) -> None:
        """Stop market data streaming."""
        if self._market_streamer:
            try:
                self._market_streamer.disconnect()
            except Exception as e:
                logger.error(f"Error stopping market stream: {e}")
            finally:
                self._market_streamer = None
                self._market_stream_active = False
                logger.info("Market stream stopped")
    
    def _on_market_stream_open(self) -> None:
        """Handle market stream connection open."""
        logger.info("Market data stream connected")
    
    def _on_market_stream_message(self, data: Dict[str, Any]) -> None:
        """Handle market stream message."""
        try:
            # Process feeds
            feeds = data.get("feeds", {})
            for instrument_key, feed_data in feeds.items():
                if self._on_tick:
                    asyncio.create_task(self._on_tick({
                        "instrument_key": instrument_key,
                        **feed_data,
                    }))
                
                # Publish to event bus
                if self._event_bus:
                    asyncio.create_task(self._publish_tick_event(instrument_key, feed_data))
                    
        except Exception as e:
            logger.error(f"Error processing market stream message: {e}")
    
    async def _publish_tick_event(self, instrument_key: str, feed_data: Dict[str, Any]) -> None:
        """Publish tick event to event bus."""
        try:
            from app.core.events import TickEvent
            
            # Extract LTP from various feed formats
            ltp = 0.0
            if "ltpc" in feed_data:
                ltp = float(feed_data["ltpc"].get("ltp", 0))
            elif "fullFeed" in feed_data:
                full = feed_data["fullFeed"]
                if "marketFF" in full and "ltpc" in full["marketFF"]:
                    ltp = float(full["marketFF"]["ltpc"].get("ltp", 0))
            
            event = TickEvent(
                event_type=EventType.TICK_RECEIVED,
                instrument_id=instrument_key,
                symbol=instrument_key.split("|")[-1] if "|" in instrument_key else instrument_key,
                ltp=ltp,
                source="upstox_enhanced",
            )
            await self._event_bus.publish(event)
        except Exception as e:
            logger.error(f"Error publishing tick event: {e}")
    
    def _on_market_stream_error(self, error: Any) -> None:
        """Handle market stream error."""
        logger.error(f"Market stream error: {error}")
        self._error_count += 1
    
    def _on_market_stream_close(self) -> None:
        """Handle market stream close."""
        logger.warning("Market data stream closed")
        self._market_stream_active = False
    
    def subscribe_instruments(self, instruments: List[str], mode: str = "full") -> bool:
        """
        Subscribe to additional instruments on active stream.
        
        Args:
            instruments: Instrument keys to subscribe
            mode: Data mode for new subscriptions
            
        Returns:
            True if successful.
        """
        if not self._market_streamer:
            logger.error("Market stream not active")
            return False
        
        try:
            self._market_streamer.subscribe(instruments, mode)
            logger.info(f"Subscribed to {len(instruments)} instruments")
            return True
        except Exception as e:
            logger.error(f"Subscribe error: {e}")
            return False
    
    def unsubscribe_instruments(self, instruments: List[str]) -> bool:
        """Unsubscribe from instruments."""
        if not self._market_streamer:
            return False
        
        try:
            self._market_streamer.unsubscribe(instruments)
            return True
        except Exception as e:
            logger.error(f"Unsubscribe error: {e}")
            return False
    
    # =========================================================================
    # Portfolio Streaming
    # =========================================================================
    
    async def start_portfolio_stream(
        self,
        order_update: bool = True,
        position_update: bool = True,
        holding_update: bool = False,
        on_update: Optional[Callable[[PortfolioUpdate], Coroutine]] = None,
    ) -> bool:
        """
        Start real-time portfolio streaming.
        
        Provides real-time updates for:
        - Orders: New orders, status changes, fills
        - Positions: Position changes, P&L updates
        - Holdings: Holding quantity changes
        
        Args:
            order_update: Subscribe to order updates
            position_update: Subscribe to position updates
            holding_update: Subscribe to holding updates
            on_update: Callback for portfolio updates
            
        Returns:
            True if stream started successfully.
        """
        if not self._initialized:
            return False
        
        self._on_portfolio_update = on_update
        
        try:
            self._portfolio_streamer = PortfolioDataStreamer(
                api_client=self._api_client,
                order_update=order_update,
                position_update=position_update,
                holding_update=holding_update,
            )
            
            # Set up handlers
            self._portfolio_streamer.on("open", self._on_portfolio_stream_open)
            self._portfolio_streamer.on("message", self._on_portfolio_stream_message)
            self._portfolio_streamer.on("error", self._on_portfolio_stream_error)
            self._portfolio_streamer.on("close", self._on_portfolio_stream_close)
            
            # Connect
            self._portfolio_streamer.connect()
            self._portfolio_stream_active = True
            
            logger.info("✓ Portfolio stream started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start portfolio stream: {e}")
            return False
    
    async def stop_portfolio_stream(self) -> None:
        """Stop portfolio streaming."""
        if self._portfolio_streamer:
            try:
                self._portfolio_streamer.disconnect()
            except Exception:
                pass
            finally:
                self._portfolio_streamer = None
                self._portfolio_stream_active = False
                logger.info("Portfolio stream stopped")
    
    def _on_portfolio_stream_open(self) -> None:
        logger.info("Portfolio stream connected")
    
    def _on_portfolio_stream_message(self, message: str) -> None:
        """Handle portfolio stream message."""
        try:
            data = json.loads(message) if isinstance(message, str) else message
            
            # Determine update type
            update_type = "unknown"
            if "order_id" in data:
                update_type = "order"
            elif "quantity" in data and "average_price" in data:
                update_type = "position"
            elif "isin" in data:
                update_type = "holding"
            
            update = PortfolioUpdate(
                update_type=update_type,
                data=data,
            )
            
            if self._on_portfolio_update:
                asyncio.create_task(self._on_portfolio_update(update))
            
            # Publish to event bus
            if self._event_bus:
                asyncio.create_task(self._publish_portfolio_event(update))
                
        except Exception as e:
            logger.error(f"Error processing portfolio message: {e}")
    
    async def _publish_portfolio_event(self, update: PortfolioUpdate) -> None:
        """Publish portfolio event to event bus."""
        try:
            # Map to appropriate event type
            event_type = EventType.POSITION_UPDATED
            if update.update_type == "order":
                event_type = EventType.ORDER_UPDATED
            
            # Create and publish event (simplified)
            await self._event_bus.publish_raw(
                event_type.value,
                {
                    "type": update.update_type,
                    "data": update.data,
                    "timestamp": update.timestamp.isoformat(),
                    "source": "upstox_portfolio_stream",
                }
            )
        except Exception as e:
            logger.error(f"Error publishing portfolio event: {e}")
    
    def _on_portfolio_stream_error(self, error: Any) -> None:
        logger.error(f"Portfolio stream error: {error}")
    
    def _on_portfolio_stream_close(self) -> None:
        logger.warning("Portfolio stream closed")
        self._portfolio_stream_active = False
    
    # =========================================================================
    # Market Info APIs
    # =========================================================================
    
    async def get_market_status(self) -> Dict[str, Any]:
        """Get current market status."""
        if not self._initialized:
            return {}
        
        try:
            response = self._market_api.get_market_status(exchange="NSE")
            if response and response.status == "success":
                return response.data if hasattr(response, 'data') else {}
        except Exception as e:
            logger.error(f"Error getting market status: {e}")
        
        return {}
    
    async def get_holidays(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get market holidays."""
        if not self._initialized:
            return []
        
        try:
            response = self._market_api.get_holiday()
            if response and response.status == "success":
                holidays = response.data or []
                if year:
                    holidays = [h for h in holidays if h.get('date', '').startswith(str(year))]
                return holidays
        except Exception as e:
            logger.error(f"Error getting holidays: {e}")
        
        return []
    
    async def get_exchange_timings(self) -> Dict[str, Any]:
        """Get exchange timings."""
        if not self._initialized:
            return {}
        
        try:
            today = date.today().isoformat()
            response = self._market_api.get_exchange_timing(today)
            if response and response.status == "success":
                return response.data if hasattr(response, 'data') else {}
        except Exception as e:
            logger.error(f"Error getting exchange timings: {e}")
        
        return {}
    
    # =========================================================================
    # Portfolio APIs
    # =========================================================================
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions from broker."""
        if not self._initialized:
            return []
        
        try:
            response = self._portfolio_api.get_positions()
            if response and response.status == "success":
                return [p.to_dict() if hasattr(p, 'to_dict') else p for p in (response.data or [])]
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
        
        return []
    
    async def get_holdings(self) -> List[Dict[str, Any]]:
        """Get current holdings from broker."""
        if not self._initialized:
            return []
        
        try:
            response = self._portfolio_api.get_holdings()
            if response and response.status == "success":
                return [h.to_dict() if hasattr(h, 'to_dict') else h for h in (response.data or [])]
        except Exception as e:
            logger.error(f"Error getting holdings: {e}")
        
        return []
    
    # =========================================================================
    # Status & Stats
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "initialized": self._initialized,
            "market_stream_active": self._market_stream_active,
            "portfolio_stream_active": self._portfolio_stream_active,
            "api_call_count": self._api_call_count,
            "error_count": self._error_count,
            "batch_size": self.BATCH_SIZE,
        }


# =============================================================================
# Factory Function
# =============================================================================

async def create_upstox_enhanced_service(
    access_token: str,
) -> UpstoxEnhancedService:
    """
    Factory function to create and initialize Upstox enhanced service.
    
    Args:
        access_token: Upstox API access token
        
    Returns:
        Initialized UpstoxEnhancedService instance.
    """
    service = UpstoxEnhancedService(access_token=access_token)
    await service.initialize()
    return service


__all__ = [
    "OptionGreeks",
    "OptionChainStrike",
    "OptionChain",
    "MarketQuote",
    "PortfolioUpdate",
    "UpstoxEnhancedService",
    "create_upstox_enhanced_service",
]
