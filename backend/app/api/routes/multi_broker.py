"""
Multi-Broker API Routes

Provides unified endpoints for:
- Order management across brokers
- Position aggregation
- Broker status and statistics
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.services.unified_order_manager import (
    get_unified_order_manager, 
    BrokerType, 
    OrderRoutingStrategy,
    BrokerConfig
)
from app.schemas.broker import OrderRequest, OrderType, OrderSide, ProductType
from app.db.models import OrderStatus

router = APIRouter(prefix="/api/broker", tags=["Multi-Broker"])


# ============ Request/Response Models ============

class PlaceOrderRequest(BaseModel):
    """Request to place an order."""
    symbol: str
    exchange: str = "NSE"
    side: str = Field(..., description="buy or sell")
    order_type: str = Field("market", description="market, limit, sl, sl_m")
    quantity: int
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    product: str = Field("mis", description="mis, cnc, nrml")
    broker: Optional[str] = Field(None, description="Specific broker to use")
    tag: str = ""


class ModifyOrderRequest(BaseModel):
    """Request to modify an order."""
    price: Optional[float] = None
    quantity: Optional[int] = None
    trigger_price: Optional[float] = None


class BrokerConfigRequest(BaseModel):
    """Request to configure a broker."""
    broker: str
    priority: int = 1
    enabled: bool = True
    max_orders_per_day: int = 100
    max_order_value: float = 1000000
    allowed_exchanges: List[str] = ["NSE", "BSE", "NFO"]


class RoutingConfigRequest(BaseModel):
    """Request to update routing configuration."""
    strategy: str = Field(..., description="primary, round_robin, best_price, lowest_cost, load_balance")
    enable_failover: bool = True


# ============ Order Management ============

@router.post("/orders/place")
async def place_order(request: PlaceOrderRequest):
    """
    Place an order through the unified order manager.
    
    Automatically routes to appropriate broker based on routing strategy.
    """
    try:
        manager = get_unified_order_manager()
        
        # Convert string enums
        side = OrderSide.BUY if request.side.lower() == "buy" else OrderSide.SELL
        
        order_type_map = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "sl": OrderType.SL,
            "sl_m": OrderType.SL_M,
        }
        order_type = order_type_map.get(request.order_type.lower(), OrderType.MARKET)
        
        product_map = {
            "mis": ProductType.MIS,
            "cnc": ProductType.CNC,
            "nrml": ProductType.NRML,
        }
        product = product_map.get(request.product.lower(), ProductType.MIS)
        
        # Create order request
        order = OrderRequest(
            symbol=request.symbol,
            exchange=request.exchange,
            side=side,
            order_type=order_type,
            quantity=request.quantity,
            price=request.price,
            trigger_price=request.trigger_price,
            product=product,
        )
        
        # Determine broker
        broker = None
        if request.broker:
            try:
                broker = BrokerType(request.broker.lower())
            except ValueError:
                raise HTTPException(400, f"Invalid broker: {request.broker}")
        
        # Place order
        unified_order = await manager.place_order(order, broker=broker, tag=request.tag)
        
        return {
            "unified_id": unified_order.unified_id,
            "broker": unified_order.broker.value,
            "broker_order_id": unified_order.broker_order_id,
            "symbol": unified_order.symbol,
            "exchange": unified_order.exchange,
            "side": unified_order.side.value,
            "order_type": unified_order.order_type.value,
            "quantity": unified_order.quantity,
            "price": unified_order.price,
            "status": unified_order.status.value,
            "message": unified_order.message,
            "placed_at": unified_order.placed_at.isoformat(),
        }
        
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.put("/orders/{unified_id}/modify")
async def modify_order(unified_id: str, request: ModifyOrderRequest):
    """Modify an existing order."""
    try:
        manager = get_unified_order_manager()
        
        order = await manager.modify_order(
            unified_id=unified_id,
            price=request.price,
            quantity=request.quantity,
            trigger_price=request.trigger_price
        )
        
        return {
            "unified_id": order.unified_id,
            "status": order.status.value,
            "price": order.price,
            "quantity": order.quantity,
            "message": order.message,
            "updated_at": order.updated_at.isoformat(),
        }
        
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/orders/{unified_id}")
async def cancel_order(unified_id: str):
    """Cancel an order."""
    try:
        manager = get_unified_order_manager()
        order = await manager.cancel_order(unified_id)
        
        return {
            "unified_id": order.unified_id,
            "status": order.status.value,
            "message": order.message,
            "updated_at": order.updated_at.isoformat(),
        }
        
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/orders/{unified_id}")
async def get_order(unified_id: str):
    """Get order status."""
    try:
        manager = get_unified_order_manager()
        order = await manager.get_order_status(unified_id)
        
        return {
            "unified_id": order.unified_id,
            "broker": order.broker.value,
            "broker_order_id": order.broker_order_id,
            "symbol": order.symbol,
            "exchange": order.exchange,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "filled_quantity": order.filled_quantity,
            "price": order.price,
            "average_price": order.average_price,
            "trigger_price": order.trigger_price,
            "product": order.product.value,
            "status": order.status.value,
            "message": order.message,
            "tag": order.tag,
            "placed_at": order.placed_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
        }
        
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/orders")
async def get_all_orders(
    broker: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500)
):
    """Get all orders with optional filters."""
    try:
        manager = get_unified_order_manager()
        
        broker_filter = None
        if broker:
            try:
                broker_filter = BrokerType(broker.lower())
            except ValueError:
                raise HTTPException(400, f"Invalid broker: {broker}")
        
        status_filter = None
        if status:
            try:
                status_filter = OrderStatus(status.lower())
            except ValueError:
                raise HTTPException(400, f"Invalid status: {status}")
        
        orders = await manager.get_all_orders(broker=broker_filter, status=status_filter)
        
        return [
            {
                "unified_id": o.unified_id,
                "broker": o.broker.value,
                "broker_order_id": o.broker_order_id,
                "symbol": o.symbol,
                "exchange": o.exchange,
                "side": o.side.value,
                "quantity": o.quantity,
                "filled_quantity": o.filled_quantity,
                "price": o.price,
                "status": o.status.value,
                "placed_at": o.placed_at.isoformat(),
            }
            for o in orders[:limit]
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ============ Position Management ============

@router.get("/positions")
async def get_all_positions(broker: Optional[str] = None):
    """Get all positions across brokers."""
    try:
        manager = get_unified_order_manager()
        
        broker_filter = None
        if broker:
            try:
                broker_filter = BrokerType(broker.lower())
            except ValueError:
                raise HTTPException(400, f"Invalid broker: {broker}")
        
        positions = await manager.get_all_positions(broker=broker_filter)
        
        return [
            {
                "symbol": p.symbol,
                "exchange": p.exchange,
                "broker": p.broker.value,
                "quantity": p.quantity,
                "average_price": p.average_price,
                "last_price": p.last_price,
                "pnl": p.pnl,
                "unrealized_pnl": p.unrealized_pnl,
                "realized_pnl": p.realized_pnl,
                "product": p.product,
                "value": p.value,
                "is_long": p.is_long,
            }
            for p in positions
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/positions/aggregated")
async def get_aggregated_positions():
    """Get positions aggregated by symbol across all brokers."""
    try:
        manager = get_unified_order_manager()
        return await manager.get_aggregated_positions()
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/portfolio/summary")
async def get_portfolio_summary():
    """Get unified portfolio summary."""
    try:
        manager = get_unified_order_manager()
        return await manager.get_portfolio_summary()
        
    except Exception as e:
        raise HTTPException(500, str(e))


# ============ Quote Management ============

@router.get("/quote/{exchange}/{symbol}")
async def get_quote(
    exchange: str,
    symbol: str,
    broker: Optional[str] = None
):
    """Get real-time quote."""
    try:
        manager = get_unified_order_manager()
        
        broker_type = None
        if broker:
            try:
                broker_type = BrokerType(broker.lower())
            except ValueError:
                raise HTTPException(400, f"Invalid broker: {broker}")
        
        quote = await manager.get_quote(symbol, exchange, broker=broker_type)
        
        return {
            "symbol": quote.symbol,
            "last_price": quote.last_price,
            "volume": quote.volume,
            "open": quote.open,
            "high": quote.high,
            "low": quote.low,
            "close": quote.close,
            "bid": quote.bid,
            "ask": quote.ask,
            "change": quote.change,
            "change_percent": quote.change_percent,
            "timestamp": quote.timestamp.isoformat() if quote.timestamp else None,
        }
        
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/quote/best/{exchange}/{symbol}")
async def get_best_quote(exchange: str, symbol: str):
    """Get best quote across all brokers."""
    try:
        manager = get_unified_order_manager()
        quote, broker = await manager.get_best_quote(symbol, exchange)
        
        return {
            "symbol": quote.symbol,
            "last_price": quote.last_price,
            "broker": broker.value,
            "volume": quote.volume,
            "timestamp": quote.timestamp.isoformat() if quote.timestamp else None,
        }
        
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


# ============ Broker Management ============

@router.get("/status")
async def get_manager_status():
    """Get unified order manager status."""
    manager = get_unified_order_manager()
    return manager.get_status()


@router.get("/brokers")
async def get_active_brokers():
    """Get list of active brokers."""
    manager = get_unified_order_manager()
    return {
        "active_brokers": [b.value for b in manager.get_active_brokers()],
        "primary_broker": manager.get_primary_broker().value if manager.get_primary_broker() else None,
    }


@router.get("/brokers/stats")
async def get_broker_stats():
    """Get statistics for all brokers."""
    try:
        manager = get_unified_order_manager()
        stats = await manager.get_broker_stats()
        
        return {
            broker: {
                "orders_placed": s.orders_placed,
                "orders_filled": s.orders_filled,
                "orders_rejected": s.orders_rejected,
                "orders_cancelled": s.orders_cancelled,
                "success_rate": round(s.success_rate * 100, 2),
                "total_turnover": s.total_turnover,
                "total_pnl": s.total_pnl,
            }
            for broker, s in stats.items()
        }
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/config/routing")
async def update_routing_config(request: RoutingConfigRequest):
    """Update order routing configuration."""
    try:
        manager = get_unified_order_manager()
        
        try:
            strategy = OrderRoutingStrategy(request.strategy)
        except ValueError:
            raise HTTPException(400, f"Invalid routing strategy: {request.strategy}")
        
        manager.routing_strategy = strategy
        manager.enable_failover = request.enable_failover
        
        return {
            "routing_strategy": manager.routing_strategy.value,
            "enable_failover": manager.enable_failover,
            "message": "Routing configuration updated",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/config/routing")
async def get_routing_config():
    """Get current routing configuration."""
    manager = get_unified_order_manager()
    return {
        "routing_strategy": manager.routing_strategy.value,
        "enable_failover": manager.enable_failover,
        "max_retry_attempts": manager.max_retry_attempts,
    }
