"""
Tests for Live Trading Engine

Tests the actual LiveTradingEngine implementation.
"""

import pytest
from decimal import Decimal
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock

from app.execution.live_trading import (
    LiveTradingEngine,
    LiveTradingMode,
    LivePosition,
    LiveTradingConfig,
    TradeSummary,
    PositionState,
)
from app.brokers.base import BaseBroker


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_broker():
    """Create a mock broker."""
    broker = MagicMock(spec=BaseBroker)
    broker.place_order = AsyncMock(return_value={"order_id": "ORD001", "status": "placed"})
    broker.modify_order = AsyncMock(return_value={"status": "modified"})
    broker.cancel_order = AsyncMock(return_value={"status": "cancelled"})
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_quote = AsyncMock(return_value={"ltp": 100.0})
    return broker


@pytest.fixture
def config():
    """Create a trading config."""
    return LiveTradingConfig(
        trading_mode=LiveTradingMode.DRY_RUN,
        max_capital=Decimal("100000"),
        max_positions=5,
        max_daily_loss=Decimal("5000"),
    )


@pytest.fixture
def live_engine(mock_event_bus, mock_broker, config):
    """Create a live trading engine."""
    return LiveTradingEngine(
        broker=mock_broker,
        config=config,
        event_bus=mock_event_bus,
    )


class TestLiveTradingMode:
    """Tests for LiveTradingMode enum."""
    
    def test_modes_exist(self):
        """Test trading modes exist."""
        assert LiveTradingMode.NORMAL
        assert LiveTradingMode.SHADOW
        assert LiveTradingMode.DRY_RUN


class TestPositionState:
    """Tests for PositionState enum."""
    
    def test_states_exist(self):
        """Test position states exist."""
        assert PositionState.OPEN
        assert PositionState.CLOSED


class TestLiveTradingConfig:
    """Tests for LiveTradingConfig."""
    
    def test_create_config(self):
        """Test creating a config."""
        config = LiveTradingConfig(
            trading_mode=LiveTradingMode.DRY_RUN,
            max_capital=Decimal("100000"),
        )
        assert config.trading_mode == LiveTradingMode.DRY_RUN
        assert config.max_capital == Decimal("100000")


class TestLivePosition:
    """Tests for LivePosition."""
    
    def test_create_position(self):
        """Test creating a position."""
        position = LivePosition(
            position_id="POS001",
            symbol="NIFTY24JAN21000CE",
            exchange="NFO",
            side="LONG",
            quantity=50,
            average_price=Decimal("150.00"),
        )
        assert position.position_id == "POS001"
        assert position.state == PositionState.PENDING


class TestTradeSummary:
    """Tests for TradeSummary."""
    
    def test_create_summary(self):
        """Test creating a trade summary."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        summary = TradeSummary(
            trade_id="TRD001",
            symbol="TEST",
            side="LONG",
            quantity=100,
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            entry_time=now,
            exit_time=now,
            net_pnl=Decimal("1000"),
            pnl_percent=Decimal("10.0"),
            exit_reason="target",
        )
        assert summary.net_pnl == Decimal("1000")


class TestLiveTradingEngine:
    """Tests for LiveTradingEngine."""
    
    @pytest.mark.asyncio
    async def test_start_stop(self, live_engine):
        """Test starting and stopping."""
        await live_engine.start()
        await live_engine.stop()
    
    @pytest.mark.asyncio
    async def test_get_positions(self, live_engine):
        """Test getting positions."""
        await live_engine.start()
        positions = live_engine.get_positions()
        assert isinstance(positions, list)
        await live_engine.stop()
    
    @pytest.mark.asyncio
    async def test_get_stats(self, live_engine):
        """Test getting stats."""
        await live_engine.start()
        stats = live_engine.get_stats()
        assert isinstance(stats, dict)
        await live_engine.stop()
    
    @pytest.mark.asyncio
    async def test_get_trades(self, live_engine):
        """Test getting trades."""
        await live_engine.start()
        trades = live_engine.get_trades()
        assert isinstance(trades, list)
        await live_engine.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
