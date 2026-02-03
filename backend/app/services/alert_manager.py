"""
Alert Management System
KeepGaining Trading Platform

Provides real-time alerts and notifications for:
- P&L thresholds (profit targets, loss limits)
- Greeks thresholds (delta, gamma, vega exposure)
- Price alerts (breakout, support, resistance)
- Risk alerts (circuit breakers, drawdown)
- System alerts (connection issues, errors)
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum
import json

from loguru import logger

from app.core.events import EventBus, EventType, get_event_bus_sync, BaseEvent
from app.db.session import get_db


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertType(str, Enum):
    """Types of alerts."""
    # P&L Alerts
    PROFIT_TARGET_HIT = "profit_target_hit"
    LOSS_LIMIT_HIT = "loss_limit_hit"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DRAWDOWN_ALERT = "drawdown_alert"
    
    # Price Alerts
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CROSS_UP = "price_cross_up"
    PRICE_CROSS_DOWN = "price_cross_down"
    
    # Greeks Alerts
    DELTA_THRESHOLD = "delta_threshold"
    GAMMA_THRESHOLD = "gamma_threshold"
    THETA_THRESHOLD = "theta_threshold"
    VEGA_THRESHOLD = "vega_threshold"
    IV_SPIKE = "iv_spike"
    
    # Position Alerts
    POSITION_SIZE_LIMIT = "position_size_limit"
    CONCENTRATION_RISK = "concentration_risk"
    
    # Risk Alerts
    CIRCUIT_BREAKER = "circuit_breaker"
    MARGIN_CALL = "margin_call"
    MAX_POSITIONS = "max_positions"
    
    # System Alerts
    BROKER_DISCONNECTED = "broker_disconnected"
    DATA_FEED_ERROR = "data_feed_error"
    ORDER_REJECTED = "order_rejected"
    EXECUTION_ERROR = "execution_error"


class AlertStatus(str, Enum):
    """Alert lifecycle status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SNOOZED = "snoozed"


@dataclass
class AlertRule:
    """Configuration for an alert rule."""
    rule_id: str
    alert_type: AlertType
    name: str
    condition: Dict[str, Any]  # Flexible condition definition
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True
    cooldown_minutes: int = 5  # Minimum time between alerts
    auto_resolve: bool = True
    notify_channels: List[str] = field(default_factory=lambda: ["ui"])
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Tracking
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0


@dataclass
class Alert:
    """An individual alert instance."""
    alert_id: str
    rule_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    status: AlertStatus = AlertStatus.ACTIVE
    triggered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "status": self.status.value,
            "triggered_at": self.triggered_at.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "data": self.data,
        }


class AlertManager:
    """
    Central alert management system.
    
    Monitors conditions and triggers alerts based on configured rules.
    Supports multiple notification channels (UI, email, webhook).
    """
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or get_event_bus_sync()
        
        # Alert rules (rule_id -> AlertRule)
        self._rules: Dict[str, AlertRule] = {}
        
        # Active alerts (alert_id -> Alert)
        self._active_alerts: Dict[str, Alert] = {}
        
        # Alert history (limited to last 1000)
        self._alert_history: List[Alert] = []
        self._max_history = 1000
        
        # Current state tracking for conditions
        self._state: Dict[str, Any] = {
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "open_positions": 0,
            "portfolio_delta": 0.0,
            "portfolio_gamma": 0.0,
            "portfolio_theta": 0.0,
            "portfolio_vega": 0.0,
        }
        
        # Price tracking for cross alerts
        self._price_cache: Dict[str, float] = {}
        
        # Notification handlers
        self._notification_handlers: Dict[str, Callable] = {}
        
        # Running state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        self._setup_default_rules()
        logger.info("AlertManager initialized")
    
    def _setup_default_rules(self) -> None:
        """Setup default alert rules."""
        default_rules = [
            AlertRule(
                rule_id="daily_loss_5pct",
                alert_type=AlertType.DAILY_LOSS_LIMIT,
                name="Daily Loss 5%",
                condition={"threshold_percent": 5.0},
                severity=AlertSeverity.WARNING,
                cooldown_minutes=30,
            ),
            AlertRule(
                rule_id="daily_loss_10pct",
                alert_type=AlertType.CIRCUIT_BREAKER,
                name="Circuit Breaker - 10% Loss",
                condition={"threshold_percent": 10.0},
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=60,
            ),
            AlertRule(
                rule_id="profit_target_2pct",
                alert_type=AlertType.PROFIT_TARGET_HIT,
                name="Profit Target 2%",
                condition={"threshold_percent": 2.0},
                severity=AlertSeverity.INFO,
                cooldown_minutes=15,
            ),
            AlertRule(
                rule_id="max_positions",
                alert_type=AlertType.MAX_POSITIONS,
                name="Max Positions Reached",
                condition={"max_positions": 5},
                severity=AlertSeverity.WARNING,
                cooldown_minutes=5,
            ),
            AlertRule(
                rule_id="delta_exposure",
                alert_type=AlertType.DELTA_THRESHOLD,
                name="Delta Exposure High",
                condition={"max_delta": 100.0, "min_delta": -100.0},
                severity=AlertSeverity.WARNING,
                cooldown_minutes=10,
            ),
            AlertRule(
                rule_id="broker_disconnect",
                alert_type=AlertType.BROKER_DISCONNECTED,
                name="Broker Disconnected",
                condition={},
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=1,
            ),
        ]
        
        for rule in default_rules:
            self._rules[rule.rule_id] = rule
    
    async def start(self) -> None:
        """Start the alert monitoring system."""
        if self._running:
            return
        
        self._running = True
        
        # Subscribe to relevant events
        await self._subscribe_to_events()
        
        # Start background monitor
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("AlertManager started")
    
    async def stop(self) -> None:
        """Stop the alert monitoring system."""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("AlertManager stopped")
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to events for alert monitoring."""
        # Subscribe to position events
        await self.event_bus.subscribe("position_update", self._on_position_update)
        await self.event_bus.subscribe("position_closed", self._on_position_closed)
        
        # Subscribe to order events
        await self.event_bus.subscribe("order_rejected", self._on_order_rejected)
        await self.event_bus.subscribe("order_filled", self._on_order_filled)
        
        # Subscribe to broker events
        await self.event_bus.subscribe("broker_disconnected", self._on_broker_disconnected)
        await self.event_bus.subscribe("broker_connected", self._on_broker_connected)
        
        # Subscribe to risk events
        await self.event_bus.subscribe("risk_limit_breached", self._on_risk_breach)
    
    async def _monitor_loop(self) -> None:
        """Background loop for periodic condition checks."""
        while self._running:
            try:
                await self._check_periodic_conditions()
                await asyncio.sleep(5)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert monitor error: {e}")
                await asyncio.sleep(10)
    
    async def _check_periodic_conditions(self) -> None:
        """Check conditions that need periodic evaluation."""
        # Check P&L based alerts
        await self._check_pnl_alerts()
        
        # Check Greeks alerts
        await self._check_greeks_alerts()
        
        # Check position limits
        await self._check_position_alerts()
    
    async def _check_pnl_alerts(self) -> None:
        """Check P&L related alerts."""
        daily_pnl = self._state.get("daily_pnl", 0.0)
        initial_capital = self._state.get("initial_capital", 100000.0)
        
        if initial_capital <= 0:
            return
        
        pnl_percent = (daily_pnl / initial_capital) * 100
        
        # Check loss alerts
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue
            
            if rule.alert_type == AlertType.DAILY_LOSS_LIMIT:
                threshold = rule.condition.get("threshold_percent", 5.0)
                if pnl_percent <= -threshold:
                    await self._trigger_alert(
                        rule,
                        f"Daily P&L down {abs(pnl_percent):.1f}%",
                        f"Current P&L: ₹{daily_pnl:,.0f} ({pnl_percent:.1f}%)",
                        {"pnl": daily_pnl, "pnl_percent": pnl_percent}
                    )
            
            elif rule.alert_type == AlertType.CIRCUIT_BREAKER:
                threshold = rule.condition.get("threshold_percent", 10.0)
                if pnl_percent <= -threshold:
                    await self._trigger_alert(
                        rule,
                        f"🚨 CIRCUIT BREAKER: {abs(pnl_percent):.1f}% Loss",
                        f"Trading halted! Loss: ₹{abs(daily_pnl):,.0f}",
                        {"pnl": daily_pnl, "pnl_percent": pnl_percent, "action": "halt_trading"}
                    )
            
            elif rule.alert_type == AlertType.PROFIT_TARGET_HIT:
                threshold = rule.condition.get("threshold_percent", 2.0)
                if pnl_percent >= threshold:
                    await self._trigger_alert(
                        rule,
                        f"✨ Profit Target Hit: {pnl_percent:.1f}%",
                        f"Congratulations! Profit: ₹{daily_pnl:,.0f}",
                        {"pnl": daily_pnl, "pnl_percent": pnl_percent}
                    )
    
    async def _check_greeks_alerts(self) -> None:
        """Check Greeks exposure alerts."""
        portfolio_delta = self._state.get("portfolio_delta", 0.0)
        
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue
            
            if rule.alert_type == AlertType.DELTA_THRESHOLD:
                max_delta = rule.condition.get("max_delta", 100.0)
                min_delta = rule.condition.get("min_delta", -100.0)
                
                if portfolio_delta > max_delta or portfolio_delta < min_delta:
                    direction = "HIGH" if portfolio_delta > 0 else "LOW"
                    await self._trigger_alert(
                        rule,
                        f"⚠️ Delta Exposure {direction}",
                        f"Portfolio delta: {portfolio_delta:.1f}. Consider hedging.",
                        {"delta": portfolio_delta}
                    )
    
    async def _check_position_alerts(self) -> None:
        """Check position-related alerts."""
        open_positions = self._state.get("open_positions", 0)
        
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue
            
            if rule.alert_type == AlertType.MAX_POSITIONS:
                max_positions = rule.condition.get("max_positions", 5)
                if open_positions >= max_positions:
                    await self._trigger_alert(
                        rule,
                        "Max Positions Reached",
                        f"You have {open_positions} open positions (limit: {max_positions})",
                        {"open_positions": open_positions, "max_positions": max_positions}
                    )
    
    async def _trigger_alert(
        self,
        rule: AlertRule,
        title: str,
        message: str,
        data: Dict[str, Any]
    ) -> Optional[Alert]:
        """Trigger an alert if cooldown allows."""
        now = datetime.now(timezone.utc)
        
        # Check cooldown
        if rule.last_triggered:
            cooldown_end = rule.last_triggered + timedelta(minutes=rule.cooldown_minutes)
            if now < cooldown_end:
                return None
        
        # Create alert
        import uuid
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            rule_id=rule.rule_id,
            alert_type=rule.alert_type,
            severity=rule.severity,
            title=title,
            message=message,
            data=data,
        )
        
        # Update rule tracking
        rule.last_triggered = now
        rule.trigger_count += 1
        
        # Store alert
        self._active_alerts[alert.alert_id] = alert
        self._alert_history.append(alert)
        
        # Trim history
        if len(self._alert_history) > self._max_history:
            self._alert_history = self._alert_history[-self._max_history:]
        
        # Notify
        await self._notify(alert)
        
        logger.info(f"Alert triggered: [{alert.severity.value}] {alert.title}")
        return alert
    
    async def _notify(self, alert: Alert) -> None:
        """Send alert notifications."""
        # Publish to event bus for UI
        try:
            await self.event_bus.publish("alert", alert.to_dict())
        except Exception as e:
            logger.warning(f"Failed to publish alert event: {e}")
        
        # Call registered notification handlers
        for channel, handler in self._notification_handlers.items():
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Notification handler {channel} failed: {e}")
    
    # Event handlers
    async def _on_position_update(self, event: BaseEvent) -> None:
        """Handle position update events."""
        data = event.metadata if hasattr(event, 'metadata') else {}
        if "unrealized_pnl" in data:
            # Update state
            pass
    
    async def _on_position_closed(self, event: BaseEvent) -> None:
        """Handle position closed events."""
        data = event.metadata if hasattr(event, 'metadata') else {}
        realized_pnl = data.get("realized_pnl", 0)
        self._state["daily_pnl"] = self._state.get("daily_pnl", 0) + realized_pnl
    
    async def _on_order_rejected(self, event: BaseEvent) -> None:
        """Handle order rejection events."""
        data = event.metadata if hasattr(event, 'metadata') else {}
        rule = self._rules.get("order_rejected")
        if rule and rule.enabled:
            await self._trigger_alert(
                rule,
                "Order Rejected",
                f"Order was rejected: {data.get('reason', 'Unknown reason')}",
                data
            )
    
    async def _on_order_filled(self, event: BaseEvent) -> None:
        """Handle order filled events."""
        self._state["open_positions"] = self._state.get("open_positions", 0) + 1
    
    async def _on_broker_disconnected(self, event: BaseEvent) -> None:
        """Handle broker disconnection."""
        rule = self._rules.get("broker_disconnect")
        if rule and rule.enabled:
            await self._trigger_alert(
                rule,
                "🔴 Broker Disconnected",
                "Connection to broker lost. Attempting to reconnect...",
                {"broker": event.metadata.get("broker_name", "Unknown")}
            )
    
    async def _on_broker_connected(self, event: BaseEvent) -> None:
        """Handle broker reconnection."""
        # Resolve any active broker disconnected alerts
        for alert_id, alert in list(self._active_alerts.items()):
            if alert.alert_type == AlertType.BROKER_DISCONNECTED:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now(timezone.utc)
                del self._active_alerts[alert_id]
    
    async def _on_risk_breach(self, event: BaseEvent) -> None:
        """Handle risk limit breach events."""
        data = event.metadata if hasattr(event, 'metadata') else {}
        
        # Create emergency alert
        alert = Alert(
            alert_id=str(uuid.uuid4()) if 'uuid' in dir() else "risk-breach",
            rule_id="risk_breach",
            alert_type=AlertType.CIRCUIT_BREAKER,
            severity=AlertSeverity.EMERGENCY,
            title="🚨 RISK LIMIT BREACHED",
            message=f"Risk limit breached: {data.get('risk_type', 'Unknown')}",
            data=data,
        )
        
        self._active_alerts[alert.alert_id] = alert
        await self._notify(alert)
    
    # Public API
    def add_rule(self, rule: AlertRule) -> None:
        """Add a new alert rule."""
        self._rules[rule.rule_id] = rule
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_rule(self, rule_id: str) -> None:
        """Remove an alert rule."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            logger.info(f"Removed alert rule: {rule_id}")
    
    def enable_rule(self, rule_id: str) -> None:
        """Enable an alert rule."""
        if rule_id in self._rules:
            self._rules[rule_id].enabled = True
    
    def disable_rule(self, rule_id: str) -> None:
        """Disable an alert rule."""
        if rule_id in self._rules:
            self._rules[rule_id].enabled = False
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        if alert_id in self._active_alerts:
            alert = self._active_alerts[alert_id]
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now(timezone.utc)
            return True
        return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve and close an alert."""
        if alert_id in self._active_alerts:
            alert = self._active_alerts[alert_id]
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now(timezone.utc)
            del self._active_alerts[alert_id]
            return True
        return False
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return list(self._active_alerts.values())
    
    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """Get alert history."""
        return self._alert_history[-limit:]
    
    def get_rules(self) -> List[AlertRule]:
        """Get all configured rules."""
        return list(self._rules.values())
    
    def update_state(self, **kwargs) -> None:
        """Update monitoring state."""
        self._state.update(kwargs)
    
    def register_notification_handler(
        self,
        channel: str,
        handler: Callable[[Alert], Any]
    ) -> None:
        """Register a notification handler for a channel."""
        self._notification_handlers[channel] = handler


# Factory function
def create_alert_manager() -> AlertManager:
    """Create and return an AlertManager instance."""
    return AlertManager()


# Singleton instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create the global AlertManager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
