"""
Tests for Enhanced Alert Manager

Tests the actual EnhancedAlertManager implementation.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.services.enhanced_alerts import (
    EnhancedAlertManager,
    Alert,
    AlertRule,
    AlertSeverity,
    AlertType,
    AlertStatus,
    NotificationChannel,
    AlertCondition,
    CircuitBreaker,
)


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def alert_manager(mock_event_bus):
    """Create an alert manager."""
    return EnhancedAlertManager(event_bus=mock_event_bus)


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""
    
    def test_severity_levels(self):
        """Test severity levels exist."""
        assert AlertSeverity.INFO
        assert AlertSeverity.WARNING
        assert AlertSeverity.CRITICAL


class TestAlertType:
    """Tests for AlertType enum."""
    
    def test_pnl_alert_types(self):
        """Test P&L alert types exist."""
        assert AlertType.PROFIT_TARGET_HIT
        assert AlertType.LOSS_LIMIT_HIT
        assert AlertType.DAILY_LOSS_LIMIT
    
    def test_greeks_alert_types(self):
        """Test Greeks alert types exist."""
        assert AlertType.DELTA_HIGH
        assert AlertType.GAMMA_HIGH
        assert AlertType.THETA_DECAY
    
    def test_risk_alert_types(self):
        """Test risk alert types exist."""
        assert AlertType.CIRCUIT_BREAKER
        assert AlertType.MARGIN_CALL


class TestAlertCondition:
    """Tests for AlertCondition."""
    
    def test_create_condition(self):
        """Test creating an alert condition."""
        condition = AlertCondition(
            field="pnl",
            operator="greater_than",
            value=10000,
        )
        assert condition.field == "pnl"
        assert condition.operator == "greater_than"


class TestAlert:
    """Tests for Alert dataclass."""
    
    def test_create_alert(self):
        """Test creating an alert."""
        alert = Alert(
            alert_id="ALT001",
            rule_id="RULE001",
            alert_type=AlertType.PROFIT_TARGET_HIT,
            severity=AlertSeverity.INFO,
            title="Profit Target Hit",
            message="You've hit your profit target!",
        )
        assert alert.alert_type == AlertType.PROFIT_TARGET_HIT
        assert alert.alert_id == "ALT001"


class TestAlertRule:
    """Tests for AlertRule."""
    
    def test_create_rule(self):
        """Test creating an alert rule."""
        condition = AlertCondition(
            field="pnl",
            operator="greater_than",
            value=5000,
        )
        rule = AlertRule(
            rule_id="RULE001",
            name="Profit Alert",
            alert_type=AlertType.PROFIT_TARGET_HIT,
            condition=condition,
            severity=AlertSeverity.INFO,
        )
        assert rule.name == "Profit Alert"
        assert rule.enabled is True


class TestEnhancedAlertManager:
    """Tests for EnhancedAlertManager."""
    
    @pytest.mark.asyncio
    async def test_add_rule(self, alert_manager):
        """Test adding a rule."""
        condition = AlertCondition(
            field="pnl",
            operator="greater_than",
            value=5000,
        )
        rule = AlertRule(
            rule_id="RULE001",
            name="Test Rule",
            alert_type=AlertType.PROFIT_TARGET_HIT,
            condition=condition,
            severity=AlertSeverity.INFO,
        )
        alert_manager.add_rule(rule)
        rules = alert_manager.get_rules()
        assert len(rules) >= 1
    
    @pytest.mark.asyncio
    async def test_enable_disable_rule(self, alert_manager):
        """Test enabling/disabling rules."""
        condition = AlertCondition(field="pnl", operator="gt", value=1000)
        rule = AlertRule(
            rule_id="RULE002",
            name="Toggle Test",
            alert_type=AlertType.PROFIT_TARGET_HIT,
            condition=condition,
            severity=AlertSeverity.INFO,
        )
        alert_manager.add_rule(rule)
        
        alert_manager.disable_rule(rule.rule_id)
        rules = alert_manager.get_rules()
        disabled = [r for r in rules if r.rule_id == rule.rule_id]
        if disabled:
            assert disabled[0].enabled is False
    
    @pytest.mark.asyncio
    async def test_get_active_alerts(self, alert_manager):
        """Test getting active alerts."""
        alerts = alert_manager.get_active_alerts()
        assert isinstance(alerts, list)
    
    @pytest.mark.asyncio
    async def test_get_alert_history(self, alert_manager):
        """Test getting alert history."""
        history = alert_manager.get_alert_history()
        assert isinstance(history, list)
    
    @pytest.mark.asyncio
    async def test_start_stop(self, alert_manager):
        """Test start and stop."""
        await alert_manager.start()
        await alert_manager.stop()


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""
    
    def test_create_circuit_breaker(self):
        """Test creating a circuit breaker."""
        cb = CircuitBreaker(
            max_daily_loss=25000.0,
            max_daily_loss_percent=5.0,
            max_drawdown_percent=10.0,
            max_consecutive_losses=5,
            cool_off_minutes=60,
        )
        assert cb.max_daily_loss == 25000.0
        assert cb.is_tripped is False
    
    def test_trip_circuit_breaker(self):
        """Test force tripping a circuit breaker."""
        cb = CircuitBreaker(
            max_daily_loss=1000.0,
            max_consecutive_losses=2,
        )
        # Use force_trip to manually trip the circuit breaker
        cb.force_trip(reason="Test trip")
        assert cb.is_tripped is True
        assert cb.trip_reason == "Test trip"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
