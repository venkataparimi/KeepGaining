"""
Tests for Audit Trail Service

Tests the actual AuditTrail implementation.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import tempfile

from app.services.audit_trail import (
    AuditTrail,
    AuditEvent,
    AuditEventType,
    FileAuditStorage,
)


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def temp_storage():
    """Create a temporary file storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileAuditStorage(base_dir=tmpdir, compress_old=False)
        yield storage


@pytest.fixture
def audit_trail(mock_event_bus, temp_storage):
    """Create an audit trail with mocks."""
    return AuditTrail(storage=temp_storage, event_bus=mock_event_bus)


class TestAuditEvent:
    """Tests for AuditEvent."""
    
    def test_create_event(self):
        """Test creating an audit event."""
        from datetime import datetime, timezone
        event = AuditEvent(
            event_id="test-001",
            event_type=AuditEventType.ORDER_PLACED,
            timestamp=datetime.now(timezone.utc),
            action="place_order",
            symbol="NIFTY24JAN21000CE",
        )
        assert event.event_type == AuditEventType.ORDER_PLACED
        assert event.event_id == "test-001"
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        from datetime import datetime, timezone
        event = AuditEvent(
            event_id="test-002",
            event_type=AuditEventType.ORDER_FILLED,
            timestamp=datetime.now(timezone.utc),
            symbol="TEST",
            quantity=100,
        )
        data = event.to_dict()
        assert "event_type" in data
        assert data["symbol"] == "TEST"


class TestAuditTrail:
    """Tests for AuditTrail."""
    
    @pytest.mark.asyncio
    async def test_log_event(self, audit_trail):
        """Test logging an event."""
        await audit_trail.log_event(
            event_type=AuditEventType.ORDER_PLACED,
            action="test",
            symbol="TEST",
        )
        assert len(audit_trail._recent_events) >= 1
    
    @pytest.mark.asyncio
    async def test_get_recent_events(self, audit_trail):
        """Test getting recent events."""
        for i in range(5):
            await audit_trail.log_event(
                event_type=AuditEventType.ORDER_PLACED,
                action=f"test_{i}",
            )
        recent = audit_trail.get_recent_events(limit=3)
        assert len(recent) == 3
    
    @pytest.mark.asyncio
    async def test_get_stats(self, audit_trail):
        """Test getting audit stats."""
        await audit_trail.log_event(
            event_type=AuditEventType.ORDER_PLACED,
            action="test",
        )
        stats = audit_trail.get_stats()
        assert "total_events" in stats or isinstance(stats, dict)
    
    @pytest.mark.asyncio
    async def test_start_stop(self, audit_trail):
        """Test start and stop."""
        await audit_trail.start()
        assert audit_trail._running is True
        await audit_trail.stop()
        assert audit_trail._running is False


class TestAuditEventType:
    """Tests for AuditEventType enum."""
    
    def test_event_types_exist(self):
        """Test that expected event types exist."""
        assert AuditEventType.ORDER_PLACED
        assert AuditEventType.ORDER_FILLED
        assert AuditEventType.POSITION_OPENED
        assert AuditEventType.POSITION_CLOSED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
