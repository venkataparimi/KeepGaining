"""Positions API endpoints"""
from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas.broker import Position
from app.brokers.fyers import FyersBroker
from loguru import logger

router = APIRouter()

# Initialize broker (in production, this would be a singleton/dependency)
broker = None

def get_broker():
    global broker
    if broker is None:
        broker = FyersBroker()
    return broker

@router.get("", response_model=List[Position])
async def get_positions():
    """
    Fetch current positions from Fyers broker
    """
    try:
        fyers_broker = get_broker()
        await fyers_broker.authenticate()
        positions = await fyers_broker.get_positions()
        return positions
    except Exception as e:
        logger.error(f"Failed to fetch positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
