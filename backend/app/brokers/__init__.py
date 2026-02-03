"""
Broker Integrations
KeepGaining Trading Platform

Multi-broker support with unified interfaces:

Trading Brokers:
    - Fyers: Primary broker for order execution and real-time WebSocket data
    - Zerodha: Alternative broker (placeholder)

Data Services:
    - UpstoxDataService: High-throughput batch data fetching for universe scanning
    - FyersWebSocketAdapter: Real-time tick streaming for active symbols

WebSocket Flow:
    FyersWebSocket → TickEvent → CandleBuilder → Indicators → Strategy

Batch Data Flow:
    UpstoxBatch (1000+ symbols/min) → CandleEvent → Indicators → Strategy
"""

from app.brokers.base import BaseBroker
from app.brokers.fyers import FyersBroker
from app.brokers.fyers_websocket import FyersWebSocketAdapter, create_fyers_websocket
from app.brokers.upstox_data import UpstoxDataService, create_upstox_service
from app.brokers.paper import PaperBroker
from app.brokers.mock import MockBroker


__all__ = [
    # Base
    "BaseBroker",
    
    # Fyers
    "FyersBroker",
    "FyersWebSocketAdapter",
    "create_fyers_websocket",
    
    # Upstox (data only)
    "UpstoxDataService",
    "create_upstox_service",
    
    # Paper/Mock
    "PaperBroker",
    "MockBroker",
]
