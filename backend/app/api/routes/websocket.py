"""
WebSocket API for Real-Time Data Streaming
KeepGaining Trading Platform

Provides real-time data streaming to frontend via WebSocket.
Features:
- Market data streaming (quotes, ticks)
- Option chain streaming with Greeks
- Portfolio updates (orders, positions)
- Price alerts
- Market scanner results
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from loguru import logger

from app.services.realtime_hub import (
    RealTimeDataHub,
    StreamType,
    get_data_hub,
    initialize_data_hub,
)
from app.core.config import settings


router = APIRouter()


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Main WebSocket endpoint for real-time data streaming.
    
    Protocol:
    1. Client connects
    2. Server sends: {"type": "connected", "client_id": "xxx"}
    3. Client can send commands:
       - Subscribe: {"action": "subscribe", "instruments": [...], "stream_type": "market_data"}
       - Unsubscribe: {"action": "unsubscribe", "instruments": [...]}
       - Add alert: {"action": "add_alert", "instrument": "...", "condition": "above", "price": 100}
       - Remove alert: {"action": "remove_alert", "alert_id": "..."}
       - Subscribe option chain: {"action": "subscribe_option_chain", "underlying": "...", "expiry": "..."}
    4. Server streams data:
       - Tick: {"type": "tick", "instrument_key": "...", "ltp": 100, ...}
       - Option chain: {"type": "option_chain", "data": {...}}
       - Portfolio: {"type": "portfolio_update", "update_type": "order", "data": {...}}
       - Alert: {"type": "alert_triggered", "alert_id": "...", ...}
       - Heartbeat: {"type": "heartbeat", "timestamp": "..."}
    """
    await websocket.accept()
    
    hub = await get_data_hub()
    client_id = None
    
    try:
        # Register client
        client_id = await hub.register_client(websocket)
        logger.info(f"WebSocket client {client_id} connected")
        
        # Process messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                await handle_client_message(hub, client_id, message, websocket)
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        if client_id:
            await hub.unregister_client(client_id)


async def handle_client_message(
    hub: RealTimeDataHub,
    client_id: str,
    message: Dict[str, Any],
    websocket: WebSocket,
) -> None:
    """Handle incoming client message."""
    action = message.get("action", "")
    
    if action == "subscribe":
        instruments = message.get("instruments", [])
        stream_type_str = message.get("stream_type", "market_data")
        
        try:
            stream_type = StreamType(stream_type_str)
        except ValueError:
            stream_type = StreamType.MARKET_DATA
        
        success = await hub.subscribe_client(client_id, instruments, stream_type)
        
        await websocket.send_json({
            "type": "subscribed",
            "instruments": instruments,
            "stream_type": stream_type_str,
            "success": success,
        })
    
    elif action == "unsubscribe":
        instruments = message.get("instruments", [])
        success = await hub.unsubscribe_client(client_id, instruments)
        
        await websocket.send_json({
            "type": "unsubscribed",
            "instruments": instruments,
            "success": success,
        })
    
    elif action == "subscribe_option_chain":
        underlying = message.get("underlying", "")
        expiry = message.get("expiry", "")
        
        success = await hub.subscribe_option_chain(
            client_id=client_id,
            underlying_key=underlying,
            expiry_date=expiry,
        )
        
        await websocket.send_json({
            "type": "option_chain_subscribed",
            "underlying": underlying,
            "expiry": expiry,
            "success": success,
        })
    
    elif action == "add_alert":
        instrument = message.get("instrument", "")
        condition = message.get("condition", "above")
        price = message.get("price", 0)
        
        alert_id = await hub.add_alert(
            instrument_key=instrument,
            condition=condition,
            price=price,
        )
        
        await websocket.send_json({
            "type": "alert_added",
            "alert_id": alert_id,
            "instrument": instrument,
            "condition": condition,
            "price": price,
        })
    
    elif action == "remove_alert":
        alert_id = message.get("alert_id", "")
        success = await hub.remove_alert(alert_id)
        
        await websocket.send_json({
            "type": "alert_removed",
            "alert_id": alert_id,
            "success": success,
        })
    
    elif action == "get_alerts":
        alerts = await hub.get_alerts()
        
        await websocket.send_json({
            "type": "alerts_list",
            "alerts": alerts,
        })
    
    elif action == "subscribe_portfolio":
        async with hub._client_lock:
            if client_id in hub._clients:
                hub._clients[client_id].stream_types.add(StreamType.PORTFOLIO)
        
        await websocket.send_json({
            "type": "portfolio_subscribed",
            "success": True,
        })
    
    elif action == "subscribe_scanner":
        async with hub._client_lock:
            if client_id in hub._clients:
                hub._clients[client_id].stream_types.add(StreamType.SCANNER)
        
        await websocket.send_json({
            "type": "scanner_subscribed",
            "success": True,
        })
    
    elif action == "ping":
        await websocket.send_json({
            "type": "pong",
            "timestamp": message.get("timestamp"),
        })
    
    else:
        await websocket.send_json({
            "type": "error",
            "message": f"Unknown action: {action}",
        })


# =============================================================================
# REST API Endpoints (for initialization and status)
# =============================================================================

@router.post("/hub/initialize")
async def initialize_hub(
    upstox_token: Optional[str] = None,
    fyers_token: Optional[str] = None,
):
    """
    Initialize the real-time data hub.
    
    Call this endpoint to set up the data hub with broker tokens.
    """
    try:
        hub = await initialize_data_hub(
            upstox_token=upstox_token,
            fyers_token=fyers_token,
        )
        return {
            "status": "success",
            "message": "Data hub initialized",
            "hub_status": hub.get_status(),
        }
    except Exception as e:
        logger.error(f"Failed to initialize hub: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hub/status")
async def get_hub_status():
    """Get the status of the real-time data hub."""
    hub = await get_data_hub()
    return hub.get_status()


@router.post("/hub/stream/market/start")
async def start_market_stream(
    instruments: List[str],
    mode: str = Query(default="full", regex="^(ltpc|full|option_greeks|full_d30)$"),
):
    """
    Start market data streaming for instruments.
    
    Args:
        instruments: List of instrument keys
        mode: Data mode (ltpc, full, option_greeks, full_d30)
    """
    hub = await get_data_hub()
    success = await hub.start_market_stream(instruments, mode)
    
    return {
        "status": "success" if success else "error",
        "message": f"Market stream {'started' if success else 'failed to start'}",
        "instruments": len(instruments),
        "mode": mode,
    }


@router.post("/hub/stream/market/stop")
async def stop_market_stream():
    """Stop market data streaming."""
    hub = await get_data_hub()
    await hub.stop_market_stream()
    
    return {
        "status": "success",
        "message": "Market stream stopped",
    }


@router.post("/hub/stream/portfolio/start")
async def start_portfolio_stream():
    """Start portfolio streaming (orders, positions)."""
    hub = await get_data_hub()
    success = await hub.start_portfolio_stream()
    
    return {
        "status": "success" if success else "error",
        "message": f"Portfolio stream {'started' if success else 'failed to start'}",
    }


# =============================================================================
# Option Chain REST API
# =============================================================================

@router.get("/option-chain/{underlying}")
async def get_option_chain(
    underlying: str,
    expiry: str = Query(..., description="Expiry date in YYYY-MM-DD format"),
):
    """
    Get option chain for an underlying.
    
    Args:
        underlying: Underlying instrument key (e.g., NSE_INDEX|Nifty 50)
        expiry: Expiry date (YYYY-MM-DD)
    """
    hub = await get_data_hub()
    chain = await hub.get_option_chain(underlying, expiry)
    
    if not chain:
        raise HTTPException(status_code=404, detail="Option chain not available")
    
    return chain.to_dict()


@router.get("/option-chain/{underlying}/expiries")
async def get_option_expiries(underlying: str):
    """Get available expiry dates for an underlying."""
    hub = await get_data_hub()
    expiries = await hub.get_option_expiries(underlying)
    
    return {
        "underlying": underlying,
        "expiries": [e.isoformat() for e in expiries],
    }


# =============================================================================
# Price Alerts REST API
# =============================================================================

@router.get("/alerts")
async def get_alerts():
    """Get all price alerts."""
    hub = await get_data_hub()
    alerts = await hub.get_alerts()
    return {"alerts": alerts}


@router.post("/alerts")
async def create_alert(
    instrument: str,
    condition: str = Query(..., regex="^(above|below|cross_above|cross_below)$"),
    price: float = Query(..., gt=0),
):
    """
    Create a price alert.
    
    Args:
        instrument: Instrument key
        condition: Alert condition (above, below, cross_above, cross_below)
        price: Target price
    """
    hub = await get_data_hub()
    alert_id = await hub.add_alert(
        instrument_key=instrument,
        condition=condition,
        price=price,
    )
    
    return {
        "status": "success",
        "alert_id": alert_id,
        "instrument": instrument,
        "condition": condition,
        "price": price,
    }


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    """Delete a price alert."""
    hub = await get_data_hub()
    success = await hub.remove_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"status": "success", "message": "Alert deleted"}


# =============================================================================
# Market Scanner REST API
# =============================================================================

@router.post("/scanner")
async def create_scanner(
    name: str,
    conditions: List[Dict[str, Any]],
    instruments: List[str],
):
    """
    Create a market scanner.
    
    Args:
        name: Scanner name
        conditions: List of conditions
            Example: [{"field": "change_percent", "op": ">", "value": 5}]
        instruments: List of instrument keys to scan
    """
    hub = await get_data_hub()
    scanner_id = await hub.create_scanner(
        name=name,
        conditions=conditions,
        instruments=instruments,
    )
    
    return {
        "status": "success",
        "scanner_id": scanner_id,
        "name": name,
    }


@router.get("/scanner/{scanner_id}/run")
async def run_scanner(scanner_id: str):
    """Run a scanner and get matching instruments."""
    hub = await get_data_hub()
    matches = await hub.run_scanner(scanner_id)
    
    return {
        "scanner_id": scanner_id,
        "matches": matches,
        "count": len(matches),
    }


# =============================================================================
# Module Export
# =============================================================================

__all__ = ["router"]
