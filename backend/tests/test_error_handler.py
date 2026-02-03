"""
Tests for Error Handler Service

Tests the actual ErrorHandler implementation.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.services.error_handler import (
    ErrorHandler,
    ErrorCategory,
    ErrorSeverity,
    ErrorRecord,
    RecoveryAction,
    ServiceHealth,
)


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def error_handler(mock_event_bus):
    """Create an error handler."""
    return ErrorHandler(event_bus=mock_event_bus)


class TestErrorSeverity:
    """Tests for ErrorSeverity enum."""
    
    def test_severity_levels(self):
        """Test severity levels exist."""
        assert ErrorSeverity.LOW
        assert ErrorSeverity.MEDIUM
        assert ErrorSeverity.HIGH
        assert ErrorSeverity.CRITICAL


class TestErrorCategory:
    """Tests for ErrorCategory enum."""
    
    def test_categories_exist(self):
        """Test error categories exist."""
        assert ErrorCategory.NETWORK
        assert ErrorCategory.BROKER
        assert ErrorCategory.VALIDATION
        assert ErrorCategory.SYSTEM


class TestRecoveryAction:
    """Tests for RecoveryAction enum."""
    
    def test_actions_exist(self):
        """Test recovery actions exist."""
        assert RecoveryAction.RETRY
        assert RecoveryAction.ALERT
        assert RecoveryAction.RECONNECT


class TestErrorRecord:
    """Tests for ErrorRecord."""
    
    def test_create_record(self):
        """Test creating an error record."""
        record = ErrorRecord(
            error_id="ERR001",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            message="Connection failed",
            exception_type="ConnectionError",
            stack_trace="",
        )
        assert record.error_id == "ERR001"
        assert record.category == ErrorCategory.NETWORK


class TestServiceHealth:
    """Tests for ServiceHealth."""
    
    def test_create_health(self):
        """Test creating service health."""
        health = ServiceHealth(
            service_name="broker",
            healthy=True,
        )
        assert health.service_name == "broker"
        assert health.healthy is True


class TestErrorHandler:
    """Tests for ErrorHandler."""
    
    @pytest.mark.asyncio
    async def test_handle_error(self, error_handler):
        """Test handling an error."""
        result = await error_handler.handle_error(
            exception=Exception("Test error"),
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.MEDIUM,
        )
        # Should return an ErrorRecord
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_get_error_stats(self, error_handler):
        """Test getting error statistics."""
        await error_handler.handle_error(
            exception=Exception("Test"),
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.LOW,
        )
        stats = error_handler.get_error_stats()
        assert isinstance(stats, dict)
    
    @pytest.mark.asyncio
    async def test_get_errors(self, error_handler):
        """Test getting recent errors."""
        await error_handler.handle_error(
            exception=Exception("Test error"),
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
        )
        errors = error_handler.get_errors()
        assert isinstance(errors, list)
    
    @pytest.mark.asyncio
    async def test_update_service_health(self, error_handler):
        """Test updating service health."""
        error_handler.update_service_health(
            service_name="test_service",
            healthy=True,
        )
        health = error_handler.get_service_health("test_service")
        assert health is not None
    
    @pytest.mark.asyncio
    async def test_get_all_health(self, error_handler):
        """Test getting all service health."""
        error_handler.update_service_health("service1", True)
        error_handler.update_service_health("service2", False)
        all_health = error_handler.get_all_health()
        assert isinstance(all_health, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
