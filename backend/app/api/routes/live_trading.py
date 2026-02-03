"""
Live Trading API Routes
KeepGaining Trading Platform

Endpoints for live trading operations:
- Start/stop live trading
- Order management
- Position management
- Order stream status
- Audit trail access
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.execution.live_trading import (
    LiveTradingEngine,
    LiveTradingConfig,
    LiveTradingMode,
    create_live_trading_engine,
)
from app.services.order_stream import (
    UnifiedOrderStream,
    get_order_stream,
)
from app.services.enhanced_alerts import (
    EnhancedAlertManager,
    get_enhanced_alert_manager,
    AlertRule,
    AlertType,
    AlertSeverity,
)
from app.services.error_handler import (
    ErrorHandler,
    get_error_handler,
)
from app.services.audit_trail import (
    AuditTrail,
    AuditEventType,
    get_audit_trail,
)
from app.brokers.fyers import FyersBroker
from app.brokers.upstox_live import UpstoxLiveBroker
from app.db.models import OrderSide

router = APIRouter(prefix="/live", tags=["Live Trading"])


# ============ Request/Response Models ============

class StartLiveTradingRequest(BaseModel):
    """Request to start live trading."""
    broker: str = Field(..., description="Broker to use: fyers or upstox")
    mode: str = Field(default="normal", description="Trading mode: normal, shadow, or dry_run")
    max_capital: Optional[float] = Field(default=None, description="Maximum capital limit")
    max_daily_loss: Optional[float] = Field(default=None, description="Maximum daily loss limit")
    max_positions: Optional[int] = Field(default=None, description="Maximum open positions")
    
    class Config:
        json_schema_extra = {
            "example": {
                "broker": "upstox",
                "mode": "dry_run",
                "max_capital": 500000,
                "max_daily_loss": 25000,
                "max_positions": 5
            }
        }


class PlaceOrderRequest(BaseModel):
    """Request to place a live order."""
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Order side: BUY or SELL")
    quantity: int = Field(..., gt=0, description="Order quantity")
    price: Optional[float] = Field(default=None, description="Limit price (None for market)")
    stop_loss: Optional[float] = Field(default=None, description="Stop loss price")
    target: Optional[float] = Field(default=None, description="Target price")
    order_type: str = Field(default="MARKET", description="Order type: MARKET, LIMIT, SL, SL-M")
    product_type: str = Field(default="MIS", description="Product type: MIS or CNC")
    strategy_id: Optional[str] = Field(default=None, description="Strategy ID")
    trailing_sl: bool = Field(default=False, description="Enable trailing stop loss")
    trailing_sl_points: Optional[float] = Field(default=None, description="Trailing SL points")


class ModifyPositionRequest(BaseModel):
    """Request to modify a position."""
    symbol: str = Field(..., description="Symbol to modify")
    stop_loss: Optional[float] = Field(default=None, description="New stop loss")
    target: Optional[float] = Field(default=None, description="New target")


class ClosePositionRequest(BaseModel):
    """Request to close a position."""
    symbol: str = Field(..., description="Symbol to close")
    reason: str = Field(default="MANUAL", description="Reason for closing")
    price: Optional[float] = Field(default=None, description="Limit price (None for market)")


class AlertRuleRequest(BaseModel):
    """Request to create/update an alert rule."""
    rule_id: str
    alert_type: str
    name: str
    description: str = ""
    condition: Dict[str, Any] = {}
    severity: str = "warning"
    enabled: bool = True
    cooldown_minutes: int = 5
    notify_channels: List[str] = ["ui"]


# ============ Global Engine Instance ============

_live_engine: Optional[LiveTradingEngine] = None


def get_live_engine() -> Optional[LiveTradingEngine]:
    """Get the live trading engine instance."""
    return _live_engine


# ============ Live Trading Endpoints ============

@router.post("/start")
async def start_live_trading(request: StartLiveTradingRequest):
    """
    Start live trading with specified broker.
    
    WARNING: This connects to real broker APIs and can execute real trades!
    Use mode="dry_run" for testing.
    """
    global _live_engine
    
    if _live_engine and _live_engine._running:
        raise HTTPException(status_code=400, detail="Live trading already running")
    
    try:
        # Create broker instance
        if request.broker.lower() == "fyers":
            broker = FyersBroker()
        elif request.broker.lower() == "upstox":
            broker = UpstoxLiveBroker(sandbox_mode=request.mode == "dry_run")
        else:
            raise HTTPException(status_code=400, detail=f"Unknown broker: {request.broker}")
        
        # Parse trading mode
        mode_map = {
            "normal": LiveTradingMode.NORMAL,
            "shadow": LiveTradingMode.SHADOW,
            "dry_run": LiveTradingMode.DRY_RUN,
        }
        trading_mode = mode_map.get(request.mode, LiveTradingMode.DRY_RUN)
        
        # Create config
        config = LiveTradingConfig(
            trading_mode=trading_mode,
        )
        
        if request.max_capital:
            config.max_capital = Decimal(str(request.max_capital))
        if request.max_daily_loss:
            config.max_daily_loss = Decimal(str(request.max_daily_loss))
        if request.max_positions:
            config.max_positions = request.max_positions
        
        # Create engine
        _live_engine = create_live_trading_engine(broker=broker, config=config)
        
        # Start engine
        success = await _live_engine.start()
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to start live trading engine")
        
        # Start alert manager
        alert_manager = get_enhanced_alert_manager()
        await alert_manager.start()
        
        # Start audit trail
        audit_trail = get_audit_trail()
        await audit_trail.start()
        
        return {
            "success": True,
            "message": f"Live trading started in {trading_mode.value} mode",
            "broker": request.broker,
            "stats": _live_engine.get_stats(),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start live trading: {str(e)}")


@router.post("/stop")
async def stop_live_trading():
    """Stop live trading."""
    global _live_engine
    
    if not _live_engine:
        raise HTTPException(status_code=400, detail="Live trading not running")
    
    try:
        stats = _live_engine.get_stats()
        await _live_engine.stop()
        
        # Stop alert manager
        alert_manager = get_enhanced_alert_manager()
        await alert_manager.stop()
        
        # Stop audit trail
        audit_trail = get_audit_trail()
        await audit_trail.stop()
        
        _live_engine = None
        
        return {
            "success": True,
            "message": "Live trading stopped",
            "final_stats": stats,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping live trading: {str(e)}")


@router.get("/status")
async def get_live_status():
    """Get live trading status."""
    if not _live_engine:
        return {
            "running": False,
            "message": "Live trading not started",
        }
    
    return {
        "running": _live_engine._running,
        "stats": _live_engine.get_stats(),
        "positions": _live_engine.get_positions(),
    }


# ============ Order Endpoints ============

@router.post("/order")
async def place_live_order(request: PlaceOrderRequest):
    """
    Place a live order.
    
    This will execute a real order via the connected broker!
    """
    if not _live_engine or not _live_engine._running:
        raise HTTPException(status_code=400, detail="Live trading not running")
    
    try:
        side = OrderSide.BUY if request.side.upper() == "BUY" else OrderSide.SELL
        
        position = await _live_engine.enter_position(
            symbol=request.symbol,
            side=side,
            quantity=request.quantity,
            price=request.price,
            stop_loss=request.stop_loss,
            target=request.target,
            order_type=request.order_type,
            product_type=request.product_type,
            strategy_id=request.strategy_id,
            trailing_sl=request.trailing_sl,
            trailing_sl_points=request.trailing_sl_points,
        )
        
        if not position:
            raise HTTPException(status_code=400, detail="Failed to place order")
        
        return {
            "success": True,
            "position": position.to_dict(),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Order error: {str(e)}")


@router.post("/close")
async def close_live_position(request: ClosePositionRequest):
    """Close a live position."""
    if not _live_engine or not _live_engine._running:
        raise HTTPException(status_code=400, detail="Live trading not running")
    
    try:
        trade = await _live_engine.exit_position(
            symbol=request.symbol,
            reason=request.reason,
            price=request.price,
        )
        
        if not trade:
            raise HTTPException(status_code=400, detail="Failed to close position")
        
        return {
            "success": True,
            "trade": trade.to_dict(),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Close error: {str(e)}")


@router.put("/position")
async def modify_live_position(request: ModifyPositionRequest):
    """Modify a live position (SL/target)."""
    if not _live_engine or not _live_engine._running:
        raise HTTPException(status_code=400, detail="Live trading not running")
    
    try:
        if request.stop_loss:
            await _live_engine.modify_sl(request.symbol, request.stop_loss)
        if request.target:
            await _live_engine.modify_target(request.symbol, request.target)
        
        position = _live_engine.get_position(request.symbol)
        
        return {
            "success": True,
            "position": position,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Modify error: {str(e)}")


@router.get("/positions")
async def get_live_positions():
    """Get all live positions."""
    if not _live_engine:
        return {"positions": []}
    
    return {"positions": _live_engine.get_positions()}


@router.get("/trades")
async def get_live_trades():
    """Get trade history."""
    if not _live_engine:
        return {"trades": []}
    
    return {"trades": _live_engine.get_trades()}


# ============ Order Stream Endpoints ============

@router.post("/stream/connect/fyers")
async def connect_fyers_stream(access_token: str, client_id: str):
    """Connect to Fyers order stream."""
    stream = get_order_stream()
    success = await stream.connect_fyers(access_token, client_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to connect to Fyers stream")
    
    return {"success": True, "status": stream.get_status()}


@router.post("/stream/connect/upstox")
async def connect_upstox_stream(access_token: str):
    """Connect to Upstox portfolio stream."""
    stream = get_order_stream()
    success = await stream.connect_upstox(access_token)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to connect to Upstox stream")
    
    return {"success": True, "status": stream.get_status()}


@router.post("/stream/disconnect")
async def disconnect_order_streams():
    """Disconnect all order streams."""
    stream = get_order_stream()
    await stream.disconnect_all()
    
    return {"success": True, "status": stream.get_status()}


@router.get("/stream/status")
async def get_stream_status():
    """Get order stream status."""
    stream = get_order_stream()
    return stream.get_status()


# ============ Alert Endpoints ============

@router.get("/alerts")
async def get_alerts():
    """Get active alerts."""
    manager = get_enhanced_alert_manager()
    alerts = manager.get_active_alerts()
    
    return {
        "alerts": [a.to_dict() for a in alerts],
        "count": len(alerts),
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    manager = get_enhanced_alert_manager()
    success = manager.acknowledge_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"success": True}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Resolve an alert."""
    manager = get_enhanced_alert_manager()
    success = manager.resolve_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"success": True}


@router.get("/alerts/rules")
async def get_alert_rules():
    """Get configured alert rules."""
    manager = get_enhanced_alert_manager()
    rules = manager.get_rules()
    
    return {
        "rules": [
            {
                "rule_id": r.rule_id,
                "alert_type": r.alert_type.value,
                "name": r.name,
                "severity": r.severity.value,
                "enabled": r.enabled,
                "trigger_count": r.trigger_count,
            }
            for r in rules
        ]
    }


@router.post("/alerts/rules")
async def create_alert_rule(request: AlertRuleRequest):
    """Create a new alert rule."""
    manager = get_enhanced_alert_manager()
    
    from app.services.enhanced_alerts import AlertCondition
    
    condition = AlertCondition(
        field=request.condition.get("field", ""),
        operator=request.condition.get("operator", "gt"),
        value=request.condition.get("value", 0),
        value2=request.condition.get("value2"),
    ) if request.condition else None
    
    rule = AlertRule(
        rule_id=request.rule_id,
        alert_type=AlertType(request.alert_type),
        name=request.name,
        description=request.description,
        condition=condition,
        severity=AlertSeverity(request.severity),
        enabled=request.enabled,
        cooldown_minutes=request.cooldown_minutes,
    )
    
    manager.add_rule(rule)
    
    return {"success": True, "rule_id": rule.rule_id}


@router.put("/alerts/rules/{rule_id}/enable")
async def enable_alert_rule(rule_id: str):
    """Enable an alert rule."""
    manager = get_enhanced_alert_manager()
    manager.enable_rule(rule_id)
    return {"success": True}


@router.put("/alerts/rules/{rule_id}/disable")
async def disable_alert_rule(rule_id: str):
    """Disable an alert rule."""
    manager = get_enhanced_alert_manager()
    manager.disable_rule(rule_id)
    return {"success": True}


@router.post("/alerts/circuit-breaker/reset")
async def reset_circuit_breaker():
    """Reset the circuit breaker."""
    manager = get_enhanced_alert_manager()
    manager.reset_circuit_breaker()
    return {"success": True, "message": "Circuit breaker reset"}


# ============ Audit Trail Endpoints ============

@router.get("/audit")
async def get_audit_events(
    event_type: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
):
    """Get audit trail events."""
    trail = get_audit_trail()
    
    event_types = [AuditEventType(event_type)] if event_type else None
    
    events = await trail.query_events(
        event_types=event_types,
        symbol=symbol,
        limit=limit,
    )
    
    return {
        "events": [e.to_dict() for e in events],
        "count": len(events),
    }


@router.get("/audit/recent")
async def get_recent_audit_events(limit: int = Query(default=50, le=200)):
    """Get recent audit events from memory."""
    trail = get_audit_trail()
    events = trail.get_recent_events(limit)
    
    return {
        "events": [e.to_dict() for e in events],
        "count": len(events),
    }


@router.get("/audit/trades")
async def get_trade_audit(
    symbol: Optional[str] = None,
    limit: int = Query(default=100, le=500),
):
    """Get trade-related audit events."""
    trail = get_audit_trail()
    events = await trail.get_trade_history(symbol=symbol, limit=limit)
    
    return {
        "events": [e.to_dict() for e in events],
        "count": len(events),
    }


@router.get("/audit/risk")
async def get_risk_audit(limit: int = Query(default=50, le=200)):
    """Get risk-related audit events."""
    trail = get_audit_trail()
    events = await trail.get_risk_events(limit=limit)
    
    return {
        "events": [e.to_dict() for e in events],
        "count": len(events),
    }


# ============ Error Handler Endpoints ============

@router.get("/errors")
async def get_errors(
    category: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """Get error history."""
    handler = get_error_handler()
    
    from app.services.error_handler import ErrorCategory
    
    cat = ErrorCategory(category) if category else None
    errors = handler.get_errors(category=cat, limit=limit)
    
    return {
        "errors": [e.to_dict() for e in errors],
        "count": len(errors),
    }


@router.get("/errors/stats")
async def get_error_stats():
    """Get error statistics."""
    handler = get_error_handler()
    return handler.get_error_stats()


@router.get("/health")
async def get_system_health():
    """Get system health status."""
    handler = get_error_handler()
    health = handler.get_all_health()
    
    # Add live trading engine health
    live_health = {
        "live_trading": {
            "healthy": _live_engine is not None and _live_engine._running,
            "running": _live_engine is not None and _live_engine._running,
        }
    }
    
    return {
        "services": {name: {"healthy": h.healthy, "error_count": h.error_count} 
                    for name, h in health.items()},
        **live_health,
        "overall_healthy": all(h.healthy for h in health.values()) and 
                          (_live_engine is None or _live_engine._running),
    }
