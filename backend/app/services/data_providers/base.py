"""
Base Data Provider Interface

Abstract base class for all data providers (Upstox, Fyers, Zerodha, TrueData, etc.)
Ensures consistent interface across different brokers/data sources.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import pandas as pd


class Interval(Enum):
    """Supported candle intervals."""
    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    DAY = "1d"
    WEEK = "1w"
    MONTH = "1M"


class InstrumentType(Enum):
    """Types of instruments."""
    EQUITY = "EQUITY"
    INDEX = "INDEX"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class Exchange(Enum):
    """Supported exchanges."""
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"  # NSE F&O
    BFO = "BFO"  # BSE F&O
    MCX = "MCX"
    CDS = "CDS"  # Currency derivatives


@dataclass
class Instrument:
    """Unified instrument representation across all providers."""
    symbol: str
    name: str
    instrument_type: InstrumentType
    exchange: Exchange
    isin: Optional[str] = None
    lot_size: int = 1
    tick_size: float = 0.05
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_fo_enabled: bool = False
    
    # Provider-specific identifiers
    provider_token: Optional[str] = None  # Unique ID in provider's system
    provider_symbol: Optional[str] = None  # Symbol format used by provider
    
    # For derivatives
    underlying_symbol: Optional[str] = None
    expiry_date: Optional[date] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = None  # CE/PE


@dataclass
class Candle:
    """Unified candle representation."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int = 0  # Open Interest (for F&O)


@dataclass
class DataProviderConfig:
    """Configuration for data providers."""
    provider_name: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None
    token_file: Optional[str] = None
    rate_limit_per_minute: int = 1000
    max_retries: int = 3
    timeout_seconds: int = 30
    extra_config: Dict[str, Any] = field(default_factory=dict)


class BaseDataProvider(ABC):
    """
    Abstract base class for data providers.
    
    All data sources (Upstox, Fyers, Zerodha, TrueData) must implement this interface.
    This ensures consistent behavior and easy switching between providers.
    """
    
    def __init__(self, config: DataProviderConfig):
        self.config = config
        self.name = config.provider_name
        self._authenticated = False
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the data provider.
        
        Returns:
            True if authentication successful, False otherwise.
        """
        pass
    
    @abstractmethod
    async def get_instrument_master(self) -> List[Instrument]:
        """
        Download complete instrument master from provider.
        
        Returns:
            List of all available instruments.
        """
        pass
    
    @abstractmethod
    async def get_fo_stocks(self) -> List[str]:
        """
        Get list of F&O enabled stocks.
        
        Returns:
            List of F&O enabled stock symbols.
        """
        pass
    
    @abstractmethod
    async def get_historical_candles(
        self,
        instrument: Instrument,
        interval: Interval,
        from_date: date,
        to_date: date,
    ) -> List[Candle]:
        """
        Get historical candle data for an instrument.
        
        Args:
            instrument: The instrument to get data for
            interval: Candle interval
            from_date: Start date
            to_date: End date
            
        Returns:
            List of candles
        """
        pass
    
    @abstractmethod
    async def get_indices(self) -> List[Instrument]:
        """
        Get list of major indices.
        
        Returns:
            List of index instruments.
        """
        pass
    
    @abstractmethod
    def get_provider_symbol(self, symbol: str, exchange: Exchange) -> str:
        """
        Convert standard symbol to provider-specific format.
        
        Args:
            symbol: Standard symbol (e.g., "RELIANCE")
            exchange: Exchange
            
        Returns:
            Provider-specific symbol format.
        """
        pass
    
    @abstractmethod
    def get_provider_instrument_key(self, instrument: Instrument) -> str:
        """
        Get provider-specific instrument key/token.
        
        Args:
            instrument: Instrument object
            
        Returns:
            Provider-specific instrument key.
        """
        pass
    
    # Optional methods with default implementations
    
    async def get_sectors(self) -> Dict[str, List[str]]:
        """
        Get sector-wise stock mapping.
        
        Returns:
            Dict mapping sector names to list of stock symbols.
        """
        return {}
    
    async def get_index_constituents(self, index_symbol: str) -> List[str]:
        """
        Get constituents of an index.
        
        Args:
            index_symbol: Index symbol (e.g., "NIFTY 50")
            
        Returns:
            List of constituent stock symbols.
        """
        return []
    
    def get_data_availability(self, interval: Interval) -> Dict[str, Any]:
        """
        Get data availability info for an interval.
        
        Returns:
            Dict with start_date, max_days_per_request, etc.
        """
        return {
            "start_date": date(2022, 1, 1),
            "max_days_per_request": 30,
        }
    
    async def close(self):
        """Cleanup resources."""
        pass
    
    async def __aenter__(self):
        await self.authenticate()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
