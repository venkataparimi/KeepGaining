"""
Enhanced Alert System
KeepGaining Trading Platform

Production-grade alert system with:
- Real-time P&L alerts (profit/loss thresholds)
- Greeks threshold alerts (delta, gamma, theta, vega)
- Circuit breaker implementation
- Multi-channel notifications (UI, email, webhook, push)
- Alert persistence and history
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum
import json
import uuid

from loguru import logger
import httpx

from app.core.events import EventBus, get_event_bus_sync


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
    DAILY_PROFIT_TARGET = "daily_profit_target"
    DRAWDOWN_ALERT = "drawdown_alert"
    POSITION_PNL = "position_pnl"
    
    # Greeks Alerts
    DELTA_HIGH = "delta_high"
    DELTA_LOW = "delta_low"
    GAMMA_HIGH = "gamma_high"
    THETA_DECAY = "theta_decay"
    VEGA_EXPOSURE = "vega_exposure"
    IV_SPIKE = "iv_spike"
    IV_CRUSH = "iv_crush"
    
    # Risk Alerts
    CIRCUIT_BREAKER = "circuit_breaker"
    MARGIN_CALL = "margin_call"
    MAX_POSITIONS = "max_positions"
    CONCENTRATION_RISK = "concentration_risk"
    
    # System Alerts
    BROKER_DISCONNECTED = "broker_disconnected"
    BROKER_RECONNECTED = "broker_reconnected"
    DATA_FEED_ERROR = "data_feed_error"
    ORDER_REJECTED = "order_rejected"
    EXECUTION_ERROR = "execution_error"
    SYSTEM_ERROR = "system_error"


class AlertStatus(str, Enum):
    """Alert lifecycle status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SNOOZED = "snoozed"
    EXPIRED = "expired"


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    UI = "ui"
    EMAIL = "email"
    WEBHOOK = "webhook"
    PUSH = "push"
    SMS = "sms"
    TELEGRAM = "telegram"


@dataclass
class AlertCondition:
    """
    Alert triggering condition.
    
    Supports various condition types:
    - threshold: value > threshold or value < threshold
    - range: min < value < max
    - change: value changed by X%
    - cross: value crossed above/below threshold
    """
    field: str
    operator: str  # gt, lt, gte, lte, eq, range, change_pct, cross_above, cross_below
    value: float
    value2: Optional[float] = None  # For range conditions
    
    def evaluate(self, current_value: float, previous_value: Optional[float] = None) -> bool:
        """Evaluate if condition is met."""
        if self.operator == "gt":
            return current_value > self.value
        elif self.operator == "lt":
            return current_value < self.value
        elif self.operator == "gte":
            return current_value >= self.value
        elif self.operator == "lte":
            return current_value <= self.value
        elif self.operator == "eq":
            return abs(current_value - self.value) < 0.0001
        elif self.operator == "range" and self.value2 is not None:
            return self.value < current_value < self.value2
        elif self.operator == "change_pct" and previous_value is not None:
            if previous_value == 0:
                return False
            change_pct = ((current_value - previous_value) / abs(previous_value)) * 100
            return abs(change_pct) >= self.value
        elif self.operator == "cross_above" and previous_value is not None:
            return previous_value < self.value <= current_value
        elif self.operator == "cross_below" and previous_value is not None:
            return previous_value > self.value >= current_value
        return False


@dataclass
class AlertRule:
    """Alert rule configuration."""
    rule_id: str
    alert_type: AlertType
    name: str
    description: str = ""
    condition: AlertCondition = None
    condition_dict: Dict[str, Any] = field(default_factory=dict)  # Alternative to condition object
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True
    cooldown_minutes: int = 5
    auto_resolve: bool = True
    expire_minutes: Optional[int] = None
    notify_channels: List[NotificationChannel] = field(default_factory=lambda: [NotificationChannel.UI])
    actions: List[str] = field(default_factory=list)  # Actions to take: halt_trading, close_positions, etc.
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
    expires_at: Optional[datetime] = None
    data: Dict[str, Any] = field(default_factory=dict)
    actions_taken: List[str] = field(default_factory=list)
    
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
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "data": self.data,
            "actions_taken": self.actions_taken,
        }


@dataclass
class NotificationConfig:
    """Notification channel configuration."""
    email_enabled: bool = False
    email_recipients: List[str] = field(default_factory=list)
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_secret: str = ""
    
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    push_enabled: bool = False
    push_subscription: Dict[str, Any] = field(default_factory=dict)


class CircuitBreaker:
    """
    Circuit breaker implementation for trading safety.
    
    Monitors conditions and can halt trading when thresholds are breached.
    """
    
    def __init__(
        self,
        max_daily_loss: float = 25000,
        max_daily_loss_percent: float = 5.0,
        max_drawdown_percent: float = 10.0,
        max_consecutive_losses: int = 5,
        cool_off_minutes: int = 30,
    ):
        self.max_daily_loss = max_daily_loss
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_drawdown_percent = max_drawdown_percent
        self.max_consecutive_losses = max_consecutive_losses
        self.cool_off_minutes = cool_off_minutes
        
        # State
        self._tripped = False
        self._trip_reason: Optional[str] = None
        self._trip_time: Optional[datetime] = None
        self._consecutive_losses = 0
        self._peak_capital: float = 0
        
    def check(
        self,
        daily_pnl: float,
        initial_capital: float,
        current_capital: float,
        last_trade_pnl: Optional[float] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if circuit breaker should trip.
        
        Returns:
            (tripped: bool, reason: str or None)
        """
        if self._tripped:
            # Check if cool-off period has passed
            if self._trip_time:
                elapsed = (datetime.now(timezone.utc) - self._trip_time).total_seconds() / 60
                if elapsed < self.cool_off_minutes:
                    return True, f"Circuit breaker cooling off ({self.cool_off_minutes - elapsed:.0f}m remaining)"
                else:
                    self.reset()
        
        # Update peak capital for drawdown calculation
        if current_capital > self._peak_capital:
            self._peak_capital = current_capital
        
        # Check absolute daily loss
        if daily_pnl < -self.max_daily_loss:
            return self._trip(f"Daily loss limit reached: ₹{abs(daily_pnl):,.0f}")
        
        # Check percentage daily loss
        if initial_capital > 0:
            loss_percent = (abs(daily_pnl) / initial_capital) * 100
            if daily_pnl < 0 and loss_percent >= self.max_daily_loss_percent:
                return self._trip(f"Daily loss limit reached: {loss_percent:.1f}%")
        
        # Check drawdown from peak
        if self._peak_capital > 0:
            drawdown = ((self._peak_capital - current_capital) / self._peak_capital) * 100
            if drawdown >= self.max_drawdown_percent:
                return self._trip(f"Max drawdown reached: {drawdown:.1f}%")
        
        # Check consecutive losses
        if last_trade_pnl is not None:
            if last_trade_pnl < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0
            
            if self._consecutive_losses >= self.max_consecutive_losses:
                return self._trip(f"Consecutive losses: {self._consecutive_losses}")
        
        return False, None
    
    def _trip(self, reason: str) -> tuple[bool, str]:
        """Trip the circuit breaker."""
        self._tripped = True
        self._trip_reason = reason
        self._trip_time = datetime.now(timezone.utc)
        logger.warning(f"Circuit breaker tripped: {reason}")
        return True, reason
    
    def reset(self) -> None:
        """Reset the circuit breaker."""
        self._tripped = False
        self._trip_reason = None
        self._trip_time = None
        self._consecutive_losses = 0
        logger.info("Circuit breaker reset")
    
    def force_trip(self, reason: str) -> None:
        """Manually trip the circuit breaker."""
        self._trip(reason)
    
    @property
    def is_tripped(self) -> bool:
        return self._tripped
    
    @property
    def trip_reason(self) -> Optional[str]:
        return self._trip_reason


class EnhancedAlertManager:
    """
    Enhanced alert management system.
    
    Features:
    - Real-time P&L monitoring and alerts
    - Greeks threshold monitoring
    - Circuit breaker integration
    - Multi-channel notifications
    - Alert persistence
    """
    
    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        notification_config: Optional[NotificationConfig] = None,
    ):
        self.event_bus = event_bus or get_event_bus_sync()
        self.notification_config = notification_config or NotificationConfig()
        
        # Alert rules
        self._rules: Dict[str, AlertRule] = {}
        
        # Active and historical alerts
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._max_history = 1000
        
        # State tracking
        self._state: Dict[str, Any] = {
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
            "initial_capital": 100000.0,
            "current_capital": 100000.0,
            "open_positions": 0,
            "portfolio_delta": 0.0,
            "portfolio_gamma": 0.0,
            "portfolio_theta": 0.0,
            "portfolio_vega": 0.0,
            "max_iv": 0.0,
            "avg_iv": 0.0,
        }
        self._previous_state: Dict[str, Any] = {}
        
        # Circuit breaker
        self.circuit_breaker = CircuitBreaker()
        
        # Running state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Setup default rules
        self._setup_default_rules()
        
        logger.info("EnhancedAlertManager initialized")
    
    def _setup_default_rules(self) -> None:
        """Setup default alert rules."""
        default_rules = [
            # P&L Rules
            AlertRule(
                rule_id="daily_loss_5pct",
                alert_type=AlertType.DAILY_LOSS_LIMIT,
                name="Daily Loss 5%",
                description="Alert when daily loss exceeds 5%",
                condition=AlertCondition(field="daily_pnl_pct", operator="lt", value=-5.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=60,
            ),
            AlertRule(
                rule_id="daily_loss_critical",
                alert_type=AlertType.CIRCUIT_BREAKER,
                name="Circuit Breaker - Daily Loss",
                description="Critical alert and halt trading on 10% daily loss",
                condition=AlertCondition(field="daily_pnl_pct", operator="lt", value=-10.0),
                severity=AlertSeverity.EMERGENCY,
                cooldown_minutes=120,
                actions=["halt_trading"],
            ),
            AlertRule(
                rule_id="profit_target_2pct",
                alert_type=AlertType.DAILY_PROFIT_TARGET,
                name="Profit Target 2%",
                description="Celebrate when daily profit hits 2%",
                condition=AlertCondition(field="daily_pnl_pct", operator="gt", value=2.0),
                severity=AlertSeverity.INFO,
                cooldown_minutes=30,
            ),
            AlertRule(
                rule_id="position_loss_warn",
                alert_type=AlertType.POSITION_PNL,
                name="Position Loss Warning",
                description="Warn when any position is down more than 2%",
                condition=AlertCondition(field="position_pnl_pct", operator="lt", value=-2.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=15,
            ),
            
            # Greeks Rules
            AlertRule(
                rule_id="delta_high",
                alert_type=AlertType.DELTA_HIGH,
                name="Delta Exposure High",
                description="Portfolio delta exceeds 100",
                condition=AlertCondition(field="portfolio_delta", operator="gt", value=100.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=10,
            ),
            AlertRule(
                rule_id="delta_low",
                alert_type=AlertType.DELTA_LOW,
                name="Delta Exposure Low",
                description="Portfolio delta below -100",
                condition=AlertCondition(field="portfolio_delta", operator="lt", value=-100.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=10,
            ),
            AlertRule(
                rule_id="gamma_high",
                alert_type=AlertType.GAMMA_HIGH,
                name="Gamma Exposure High",
                description="Portfolio gamma exposure is high",
                condition=AlertCondition(field="portfolio_gamma", operator="gt", value=50.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=15,
            ),
            AlertRule(
                rule_id="theta_decay",
                alert_type=AlertType.THETA_DECAY,
                name="Theta Decay Alert",
                description="High theta decay exposure",
                condition=AlertCondition(field="portfolio_theta", operator="lt", value=-500.0),
                severity=AlertSeverity.INFO,
                cooldown_minutes=60,
            ),
            AlertRule(
                rule_id="vega_exposure",
                alert_type=AlertType.VEGA_EXPOSURE,
                name="Vega Exposure Alert",
                description="High vega exposure",
                condition=AlertCondition(field="portfolio_vega", operator="gt", value=1000.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=30,
            ),
            AlertRule(
                rule_id="iv_spike",
                alert_type=AlertType.IV_SPIKE,
                name="IV Spike Alert",
                description="Implied volatility spiked significantly",
                condition=AlertCondition(field="avg_iv", operator="change_pct", value=20.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=15,
            ),
            
            # Risk Rules
            AlertRule(
                rule_id="max_positions",
                alert_type=AlertType.MAX_POSITIONS,
                name="Max Positions Reached",
                description="Maximum position limit reached",
                condition=AlertCondition(field="open_positions", operator="gte", value=5.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=5,
            ),
            AlertRule(
                rule_id="concentration_risk",
                alert_type=AlertType.CONCENTRATION_RISK,
                name="Concentration Risk",
                description="Single position exceeds 30% of portfolio",
                condition=AlertCondition(field="max_position_pct", operator="gt", value=30.0),
                severity=AlertSeverity.WARNING,
                cooldown_minutes=30,
            ),
            
            # System Rules
            AlertRule(
                rule_id="broker_disconnect",
                alert_type=AlertType.BROKER_DISCONNECTED,
                name="Broker Disconnected",
                description="Connection to broker lost",
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
        
        # Subscribe to events
        await self._subscribe_to_events()
        
        # Start monitoring loop
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("EnhancedAlertManager started")
    
    async def stop(self) -> None:
        """Stop the alert monitoring system."""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("EnhancedAlertManager stopped")
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to relevant events."""
        try:
            await self.event_bus.subscribe("position_update", self._on_position_update)
            await self.event_bus.subscribe("position_closed", self._on_position_closed)
            await self.event_bus.subscribe("order_rejected", self._on_order_rejected)
            await self.event_bus.subscribe("broker_disconnected", self._on_broker_disconnected)
            await self.event_bus.subscribe("broker_connected", self._on_broker_connected)
            await self.event_bus.subscribe("greeks_update", self._on_greeks_update)
        except Exception as e:
            logger.warning(f"Failed to subscribe to events: {e}")
    
    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                await self._evaluate_all_rules()
                await self._check_circuit_breaker()
                await self._expire_old_alerts()
                
                # Store previous state for change detection
                self._previous_state = self._state.copy()
                
                await asyncio.sleep(2)  # Check every 2 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(5)
    
    async def _evaluate_all_rules(self) -> None:
        """Evaluate all alert rules against current state."""
        # Calculate derived values
        initial_capital = self._state.get("initial_capital", 100000)
        daily_pnl = self._state.get("daily_pnl", 0)
        
        if initial_capital > 0:
            self._state["daily_pnl_pct"] = (daily_pnl / initial_capital) * 100
        
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue
            
            # Check cooldown
            if rule.last_triggered:
                cooldown_end = rule.last_triggered + timedelta(minutes=rule.cooldown_minutes)
                if datetime.now(timezone.utc) < cooldown_end:
                    continue
            
            # Evaluate condition
            triggered = False
            
            if rule.condition:
                current_value = self._state.get(rule.condition.field, 0)
                previous_value = self._previous_state.get(rule.condition.field)
                triggered = rule.condition.evaluate(current_value, previous_value)
            elif rule.condition_dict:
                triggered = self._evaluate_condition_dict(rule.condition_dict)
            
            if triggered:
                await self._trigger_rule(rule)
    
    def _evaluate_condition_dict(self, condition: Dict[str, Any]) -> bool:
        """Evaluate a dictionary-based condition."""
        field = condition.get("field", "")
        operator = condition.get("operator", "gt")
        threshold = condition.get("threshold", 0)
        
        current_value = self._state.get(field, 0)
        
        if operator == "gt":
            return current_value > threshold
        elif operator == "lt":
            return current_value < threshold
        elif operator == "gte":
            return current_value >= threshold
        elif operator == "lte":
            return current_value <= threshold
        
        return False
    
    async def _trigger_rule(self, rule: AlertRule) -> None:
        """Trigger an alert for a rule."""
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            rule_id=rule.rule_id,
            alert_type=rule.alert_type,
            severity=rule.severity,
            title=rule.name,
            message=rule.description or self._generate_alert_message(rule),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=rule.expire_minutes) if rule.expire_minutes else None,
            data={"state": self._state.copy()},
        )
        
        # Update rule tracking
        rule.last_triggered = datetime.now(timezone.utc)
        rule.trigger_count += 1
        
        # Store alert
        self._active_alerts[alert.alert_id] = alert
        self._alert_history.append(alert)
        
        # Trim history
        if len(self._alert_history) > self._max_history:
            self._alert_history = self._alert_history[-self._max_history:]
        
        # Execute actions
        for action in rule.actions:
            await self._execute_action(action, alert)
            alert.actions_taken.append(action)
        
        # Send notifications
        await self._send_notifications(alert, rule.notify_channels)
        
        logger.info(f"Alert triggered: [{alert.severity.value}] {alert.title}")
    
    def _generate_alert_message(self, rule: AlertRule) -> str:
        """Generate alert message from state."""
        if rule.condition:
            value = self._state.get(rule.condition.field, 0)
            return f"{rule.name}: {rule.condition.field} is {value}"
        return rule.name
    
    async def _execute_action(self, action: str, alert: Alert) -> None:
        """Execute an alert action."""
        if action == "halt_trading":
            self.circuit_breaker.force_trip(f"Alert triggered: {alert.title}")
            await self.event_bus.publish("trading_halted", {
                "reason": alert.title,
                "alert_id": alert.alert_id,
            })
        elif action == "close_positions":
            await self.event_bus.publish("close_all_positions", {
                "reason": alert.title,
            })
        elif action == "reduce_exposure":
            await self.event_bus.publish("reduce_exposure", {
                "target_percent": 50,
            })
        
        logger.info(f"Alert action executed: {action}")
    
    async def _send_notifications(self, alert: Alert, channels: List[NotificationChannel]) -> None:
        """Send alert notifications via configured channels."""
        for channel in channels:
            try:
                if channel == NotificationChannel.UI:
                    await self._notify_ui(alert)
                elif channel == NotificationChannel.EMAIL:
                    await self._notify_email(alert)
                elif channel == NotificationChannel.WEBHOOK:
                    await self._notify_webhook(alert)
                elif channel == NotificationChannel.TELEGRAM:
                    await self._notify_telegram(alert)
            except Exception as e:
                logger.error(f"Failed to send {channel.value} notification: {e}")
    
    async def _notify_ui(self, alert: Alert) -> None:
        """Publish alert to event bus for UI."""
        await self.event_bus.publish("alert", alert.to_dict())
    
    async def _notify_email(self, alert: Alert) -> None:
        """Send email notification."""
        if not self.notification_config.email_enabled:
            return
        
        # TODO: Implement email sending via SMTP
        logger.info(f"Email notification would be sent: {alert.title}")
    
    async def _notify_webhook(self, alert: Alert) -> None:
        """Send webhook notification."""
        if not self.notification_config.webhook_enabled:
            return
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.notification_config.webhook_url,
                    json=alert.to_dict(),
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Secret": self.notification_config.webhook_secret,
                    },
                    timeout=10,
                )
                
                if response.status_code != 200:
                    logger.warning(f"Webhook notification failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Webhook notification error: {e}")
    
    async def _notify_telegram(self, alert: Alert) -> None:
        """Send Telegram notification."""
        if not self.notification_config.telegram_enabled:
            return
        
        try:
            message = f"🚨 *{alert.severity.value.upper()}*\n\n"
            message += f"*{alert.title}*\n"
            message += f"{alert.message}\n\n"
            message += f"_Time: {alert.triggered_at.strftime('%H:%M:%S')}_"
            
            url = f"https://api.telegram.org/bot{self.notification_config.telegram_bot_token}/sendMessage"
            
            async with httpx.AsyncClient() as client:
                await client.post(url, json={
                    "chat_id": self.notification_config.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                })
        except Exception as e:
            logger.error(f"Telegram notification error: {e}")
    
    async def _check_circuit_breaker(self) -> None:
        """Check circuit breaker conditions."""
        tripped, reason = self.circuit_breaker.check(
            daily_pnl=self._state.get("daily_pnl", 0),
            initial_capital=self._state.get("initial_capital", 100000),
            current_capital=self._state.get("current_capital", 100000),
        )
        
        if tripped and reason:
            # Create circuit breaker alert if not already active
            existing = [a for a in self._active_alerts.values() 
                       if a.alert_type == AlertType.CIRCUIT_BREAKER and a.status == AlertStatus.ACTIVE]
            
            if not existing:
                alert = Alert(
                    alert_id=str(uuid.uuid4()),
                    rule_id="circuit_breaker",
                    alert_type=AlertType.CIRCUIT_BREAKER,
                    severity=AlertSeverity.EMERGENCY,
                    title="🚨 CIRCUIT BREAKER TRIGGERED",
                    message=reason,
                    data={"state": self._state.copy()},
                )
                
                self._active_alerts[alert.alert_id] = alert
                await self._send_notifications(alert, [NotificationChannel.UI, NotificationChannel.WEBHOOK])
    
    async def _expire_old_alerts(self) -> None:
        """Expire alerts that have passed their expiry time."""
        now = datetime.now(timezone.utc)
        
        for alert_id, alert in list(self._active_alerts.items()):
            if alert.expires_at and now > alert.expires_at:
                alert.status = AlertStatus.EXPIRED
                del self._active_alerts[alert_id]
    
    # Event handlers
    async def _on_position_update(self, event: Any) -> None:
        """Handle position update events."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        
        if "unrealized_pnl" in data:
            self._state["unrealized_pnl"] = data["unrealized_pnl"]
        if "position_count" in data:
            self._state["open_positions"] = data["position_count"]
    
    async def _on_position_closed(self, event: Any) -> None:
        """Handle position closed events."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        
        realized_pnl = data.get("realized_pnl", 0)
        self._state["daily_pnl"] = self._state.get("daily_pnl", 0) + realized_pnl
        
        # Update circuit breaker with last trade P&L
        self.circuit_breaker.check(
            daily_pnl=self._state["daily_pnl"],
            initial_capital=self._state.get("initial_capital", 100000),
            current_capital=self._state.get("current_capital", 100000),
            last_trade_pnl=realized_pnl,
        )
    
    async def _on_order_rejected(self, event: Any) -> None:
        """Handle order rejection events."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            rule_id="order_rejected",
            alert_type=AlertType.ORDER_REJECTED,
            severity=AlertSeverity.WARNING,
            title="Order Rejected",
            message=f"Order rejected: {data.get('reason', 'Unknown reason')}",
            data=data,
        )
        
        self._active_alerts[alert.alert_id] = alert
        await self._notify_ui(alert)
    
    async def _on_broker_disconnected(self, event: Any) -> None:
        """Handle broker disconnection."""
        rule = self._rules.get("broker_disconnect")
        if rule and rule.enabled:
            await self._trigger_rule(rule)
    
    async def _on_broker_connected(self, event: Any) -> None:
        """Handle broker reconnection."""
        # Resolve any active broker disconnected alerts
        for alert_id, alert in list(self._active_alerts.items()):
            if alert.alert_type == AlertType.BROKER_DISCONNECTED:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now(timezone.utc)
                del self._active_alerts[alert_id]
    
    async def _on_greeks_update(self, event: Any) -> None:
        """Handle Greeks update events."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        
        self._state["portfolio_delta"] = data.get("delta", 0)
        self._state["portfolio_gamma"] = data.get("gamma", 0)
        self._state["portfolio_theta"] = data.get("theta", 0)
        self._state["portfolio_vega"] = data.get("vega", 0)
        self._state["avg_iv"] = data.get("avg_iv", 0)
    
    # Public API
    def add_rule(self, rule: AlertRule) -> None:
        """Add a new alert rule."""
        self._rules[rule.rule_id] = rule
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove an alert rule."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False
    
    def enable_rule(self, rule_id: str) -> bool:
        """Enable an alert rule."""
        if rule_id in self._rules:
            self._rules[rule_id].enabled = True
            return True
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        """Disable an alert rule."""
        if rule_id in self._rules:
            self._rules[rule_id].enabled = False
            return True
        return False
    
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
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state."""
        return self._state.copy()
    
    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker."""
        self.circuit_breaker.reset()


# Singleton instance
_enhanced_alert_manager: Optional[EnhancedAlertManager] = None


def get_enhanced_alert_manager() -> EnhancedAlertManager:
    """Get or create the global EnhancedAlertManager instance."""
    global _enhanced_alert_manager
    if _enhanced_alert_manager is None:
        _enhanced_alert_manager = EnhancedAlertManager()
    return _enhanced_alert_manager
