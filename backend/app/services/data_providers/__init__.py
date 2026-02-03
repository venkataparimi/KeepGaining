"""
Data Providers Module

Broker-agnostic data download architecture supporting multiple data sources:
- Upstox
- Fyers
- Zerodha (Kite)
- TrueData
- Custom CSV files

Each provider implements the BaseDataProvider interface.
"""

from .base import BaseDataProvider, DataProviderConfig
from .upstox import UpstoxDataProvider
# from .fyers import FyersDataProvider  # TODO: Implement
# from .zerodha import ZerodhaDataProvider  # TODO: Implement
# from .truedata import TrueDataProvider  # TODO: Implement

__all__ = [
    "BaseDataProvider",
    "DataProviderConfig",
    "UpstoxDataProvider",
]
