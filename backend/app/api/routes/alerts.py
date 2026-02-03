"""
Alert Management API Routes
KeepGaining Trading Platform
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.alert_manager import (
    get_alert_manager, AlertRule, Alert, AlertType, AlertSeverity, AlertStatus
)

router = APIRouter()


# ============ Schemas ============

class AlertRuleCreate(BaseModel):
    rule_id: str
    alert_type: str
    name: str
    condition: Dict[str, Any]
    severity: str = "warning"
    enabled: bool = True
    cooldown_minutes: int = 5


class AlertRuleResponse(BaseModel):
    rule_id: str
    alert_type: str
    name: str
    condition: Dict[str, Any]
    severity: str
    enabled: bool
    cooldown_minutes: int
    last_triggered: Optional[str] = None
    trigger_count: int = 0


class AlertResponse(BaseModel):
    alert_id: str
    rule_id: str
    alert_type: str
    severity: str
    title: str
    message: str
    status: str
    triggered_at: str
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None
    data: Dict[str, Any] = {}


class AlertStateUpdate(BaseModel):
    daily_pnl: Optional[float] = None
    total_pnl: Optional[float] = None
    initial_capital: Optional[float] = None
    open_positions: Optional[int] = None
    portfolio_delta: Optional[float] = None
    portfolio_gamma: Optional[float] = None
    portfolio_theta: Optional[float] = None
    portfolio_vega: Optional[float] = None


# ============ Alert Endpoints ============

@router.get("/active")
async def get_active_alerts() -> List[AlertResponse]:
    """Get all active alerts."""
    manager = get_alert_manager()
    alerts = manager.get_active_alerts()
    
    return [
        AlertResponse(
            alert_id=a.alert_id,
            rule_id=a.rule_id,
            alert_type=a.alert_type.value,
            severity=a.severity.value,
            title=a.title,
            message=a.message,
            status=a.status.value,
            triggered_at=a.triggered_at.isoformat(),
            acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
            data=a.data,
        )
        for a in alerts
    ]


@router.get("/stats")
async def get_alert_stats():
    """Get alert statistics."""
    manager = get_alert_manager()
    active = manager.get_active_alerts()
    history = manager.get_alert_history(limit=1000)
    
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone.utc).date()
    
    today_alerts = [a for a in history if a.triggered_at.date() == today]
    
    return {
        "total_alerts_today": len(today_alerts),
        "critical_count": len([a for a in active if a.severity.value == "critical"]),
        "warning_count": len([a for a in active if a.severity.value == "warning"]),
        "info_count": len([a for a in active if a.severity.value == "info"]),
        "acknowledged_count": len([a for a in active if a.status.value == "acknowledged"]),
        "snoozed_count": len([a for a in active if a.status.value == "snoozed"]),
    }


@router.get("/settings")
async def get_alert_settings():
    """Get alert settings."""
    # Return default settings - can be expanded to load from config/DB
    return {
        "greeks_thresholds": {
            "delta_limit": 1.0,
            "gamma_limit": 0.1,
            "theta_limit": -5000,
            "vega_limit": 10000,
        },
        "pnl_thresholds": {
            "profit_target": 50000,
            "loss_limit": 25000,
            "daily_loss_limit": 50000,
            "drawdown_limit": 10,
        },
        "notification_channels": {
            "email": False,
            "push": True,
            "sound": True,
            "webhook": False,
        },
    }


@router.post("/settings")
async def update_alert_settings(settings: Dict[str, Any]):
    """Update alert settings."""
    # TODO: Persist settings to config/DB
    return {"message": "Settings updated", "settings": settings}


@router.get("/history")
async def get_alert_history(limit: int = 100) -> List[AlertResponse]:
    """Get alert history."""
    manager = get_alert_manager()
    alerts = manager.get_alert_history(limit)
    
    return [
        AlertResponse(
            alert_id=a.alert_id,
            rule_id=a.rule_id,
            alert_type=a.alert_type.value,
            severity=a.severity.value,
            title=a.title,
            message=a.message,
            status=a.status.value,
            triggered_at=a.triggered_at.isoformat(),
            acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
            data=a.data,
        )
        for a in alerts
    ]


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    manager = get_alert_manager()
    success = manager.acknowledge_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"message": "Alert acknowledged", "alert_id": alert_id}


@router.post("/{alert_id}/snooze")
async def snooze_alert(alert_id: str, minutes: int = 30):
    """Snooze an alert for specified minutes."""
    manager = get_alert_manager()
    # Snooze by acknowledging - full snooze logic can be added later
    success = manager.acknowledge_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"message": f"Alert snoozed for {minutes} minutes", "alert_id": alert_id}


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Resolve and close an alert."""
    manager = get_alert_manager()
    success = manager.resolve_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"message": "Alert resolved", "alert_id": alert_id}


# ============ Rule Endpoints ============

@router.get("/rules")
async def get_alert_rules() -> List[AlertRuleResponse]:
    """Get all configured alert rules."""
    manager = get_alert_manager()
    rules = manager.get_rules()
    
    return [
        AlertRuleResponse(
            rule_id=r.rule_id,
            alert_type=r.alert_type.value,
            name=r.name,
            condition=r.condition,
            severity=r.severity.value,
            enabled=r.enabled,
            cooldown_minutes=r.cooldown_minutes,
            last_triggered=r.last_triggered.isoformat() if r.last_triggered else None,
            trigger_count=r.trigger_count,
        )
        for r in rules
    ]


@router.post("/rules")
async def create_alert_rule(rule: AlertRuleCreate) -> AlertRuleResponse:
    """Create a new alert rule."""
    manager = get_alert_manager()
    
    # Map string to enum
    try:
        alert_type = AlertType(rule.alert_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid alert type: {rule.alert_type}")
    
    try:
        severity = AlertSeverity(rule.severity)
    except ValueError:
        severity = AlertSeverity.WARNING
    
    new_rule = AlertRule(
        rule_id=rule.rule_id,
        alert_type=alert_type,
        name=rule.name,
        condition=rule.condition,
        severity=severity,
        enabled=rule.enabled,
        cooldown_minutes=rule.cooldown_minutes,
    )
    
    manager.add_rule(new_rule)
    
    return AlertRuleResponse(
        rule_id=new_rule.rule_id,
        alert_type=new_rule.alert_type.value,
        name=new_rule.name,
        condition=new_rule.condition,
        severity=new_rule.severity.value,
        enabled=new_rule.enabled,
        cooldown_minutes=new_rule.cooldown_minutes,
        trigger_count=0,
    )


@router.put("/rules/{rule_id}/enable")
async def enable_alert_rule(rule_id: str):
    """Enable an alert rule."""
    manager = get_alert_manager()
    manager.enable_rule(rule_id)
    return {"message": f"Rule {rule_id} enabled"}


@router.put("/rules/{rule_id}/disable")
async def disable_alert_rule(rule_id: str):
    """Disable an alert rule."""
    manager = get_alert_manager()
    manager.disable_rule(rule_id)
    return {"message": f"Rule {rule_id} disabled"}


@router.patch("/rules/{rule_id}")
async def update_alert_rule(rule_id: str, updates: Dict[str, Any]):
    """Update an alert rule (enable/disable)."""
    manager = get_alert_manager()
    if updates.get("enabled") is True:
        manager.enable_rule(rule_id)
    elif updates.get("enabled") is False:
        manager.disable_rule(rule_id)
    return {"message": f"Rule {rule_id} updated"}


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete an alert rule."""
    manager = get_alert_manager()
    manager.remove_rule(rule_id)
    return {"message": f"Rule {rule_id} deleted"}


# ============ State Update Endpoint ============

@router.post("/state")
async def update_alert_state(state: AlertStateUpdate):
    """Update the alert monitoring state."""
    manager = get_alert_manager()
    
    update_dict = state.model_dump(exclude_none=True)
    manager.update_state(**update_dict)
    
    return {"message": "State updated", "updated_fields": list(update_dict.keys())}


# ============ Test Endpoints ============

@router.post("/test")
async def trigger_test_alert(
    title: str = "Test Alert",
    message: str = "This is a test alert",
    severity: str = "warning"
):
    """Trigger a test alert for verification."""
    manager = get_alert_manager()
    
    # Create a temporary test rule
    test_rule = AlertRule(
        rule_id="test_alert",
        alert_type=AlertType.PROFIT_TARGET_HIT,
        name="Test Alert",
        condition={},
        severity=AlertSeverity(severity) if severity in [s.value for s in AlertSeverity] else AlertSeverity.WARNING,
        cooldown_minutes=0,  # No cooldown for test
    )
    
    alert = await manager._trigger_alert(
        test_rule,
        title,
        message,
        {"test": True}
    )
    
    if alert:
        return {
            "message": "Test alert triggered",
            "alert_id": alert.alert_id,
            "severity": alert.severity.value,
        }
    
    return {"message": "Alert was suppressed (cooldown)"}
