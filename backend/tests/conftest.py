"""
Test configuration and shared fixtures for KeepGaining backend tests.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo


# =============================================================================
# Event Bus Mock
# =============================================================================

@pytest.fixture
def mock_event_bus():
    """Create a mock event bus for testing."""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.stream_name = MagicMock(return_value="kg:events:test")
    return bus


# =============================================================================
# Broker Mocks
# =============================================================================

@pytest.fixture
def mock_broker():
    """Create a mock broker for testing."""
    broker = AsyncMock()
    broker.name = "test_broker"
    
    # Order methods
    broker.place_order = AsyncMock(return_value={
        "order_id": "TEST001",
        "status": "placed",
    })
    broker.modify_order = AsyncMock(return_value={
        "order_id": "TEST001",
        "status": "modified",
    })
    broker.cancel_order = AsyncMock(return_value={
        "order_id": "TEST001",
        "status": "cancelled",
    })
    
    # Position methods
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_holdings = AsyncMock(return_value=[])
    
    # Account methods
    broker.get_funds = AsyncMock(return_value={
        "available": Decimal("1000000"),
        "used": Decimal("100000"),
    })
    broker.get_margins = AsyncMock(return_value={
        "available": Decimal("500000"),
        "used": Decimal("100000"),
    })
    
    # Market data methods
    broker.get_quote = AsyncMock(return_value={
        "ltp": Decimal("100.00"),
        "bid": Decimal("99.95"),
        "ask": Decimal("100.05"),
    })
    broker.get_historical_data = AsyncMock(return_value=[])
    
    return broker


@pytest.fixture
def mock_fyers_broker(mock_broker):
    """Create a mock Fyers broker."""
    mock_broker.name = "fyers"
    mock_broker.broker_type = "fyers"
    return mock_broker


@pytest.fixture
def mock_upstox_broker(mock_broker):
    """Create a mock Upstox broker."""
    mock_broker.name = "upstox"
    mock_broker.broker_type = "upstox"
    return mock_broker


# =============================================================================
# Database Mocks
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.query = MagicMock()
    session.execute = AsyncMock()
    return session


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_order():
    """Create a sample order."""
    return {
        "order_id": "TEST001",
        "symbol": "NIFTY24JAN21000CE",
        "exchange": "NFO",
        "side": "BUY",
        "quantity": 50,
        "price": Decimal("150.00"),
        "order_type": "LIMIT",
        "product_type": "INTRADAY",
        "status": "placed",
        "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")),
    }


@pytest.fixture
def sample_position():
    """Create a sample position."""
    return {
        "symbol": "NIFTY24JAN21000CE",
        "exchange": "NFO",
        "side": "LONG",
        "quantity": 50,
        "entry_price": Decimal("150.00"),
        "current_price": Decimal("155.00"),
        "pnl": Decimal("250.00"),
        "pnl_percent": Decimal("3.33"),
    }


@pytest.fixture
def sample_strategy_config():
    """Create a sample strategy configuration."""
    return {
        "name": "test_strategy",
        "enabled": True,
        "capital_allocation": Decimal("100000"),
        "max_positions": 5,
        "risk_per_trade": Decimal("2.0"),
        "target_percent": Decimal("3.0"),
        "stop_loss_percent": Decimal("1.5"),
    }


# =============================================================================
# Time Fixtures
# =============================================================================

@pytest.fixture
def ist_timezone():
    """Get IST timezone."""
    return ZoneInfo("Asia/Kolkata")


@pytest.fixture
def market_open_time(ist_timezone):
    """Get market open time."""
    now = datetime.now(ist_timezone)
    return now.replace(hour=9, minute=15, second=0, microsecond=0)


@pytest.fixture
def market_close_time(ist_timezone):
    """Get market close time."""
    now = datetime.now(ist_timezone)
    return now.replace(hour=15, minute=30, second=0, microsecond=0)


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset any singleton instances between tests."""
    yield
    # Clean up after each test if needed


# =============================================================================
# Async Event Loop Configuration
# =============================================================================

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
