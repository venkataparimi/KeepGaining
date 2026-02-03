"""Orders API endpoints"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.schemas.broker import OrderRequest, OrderResponse
from app.brokers.fyers import FyersBroker
from loguru import logger

router = APIRouter()

broker = None

def get_broker():
    global broker
    if broker is None:
        broker = FyersBroker()
    return broker

@router.get("", response_model=List[Dict[str, Any]])
async def get_orders():
    """
    Fetch order book from Fyers
    """
    try:
        fyers_broker = get_broker()
        await fyers_broker.authenticate()
        orders_response = fyers_broker.client.get_orders()
        
        if orders_response.get('s') == 'ok':
            return orders_response.get('orderBook', [])
        else:
            raise HTTPException(status_code=500, detail=orders_response.get('message', 'Failed to fetch orders'))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/place", response_model=OrderResponse)
async def place_order(order: OrderRequest):
    """
    Place a manual order
    """
    try:
        fyers_broker = get_broker()
        await fyers_broker.authenticate()
        response = await fyers_broker.place_order(order)
        return response
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        raise HTTPException(status_code=500, detail=str(e))
