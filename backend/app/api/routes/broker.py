"""Broker API endpoints"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel
from app.brokers.fyers import FyersBroker
from app.brokers.mock import MockBroker
from app.core.config import settings
from loguru import logger

router = APIRouter()

broker = None
mock_broker = None

def get_broker():
    global broker
    if broker is None:
        broker = FyersBroker()
    return broker

def get_mock_broker():
    global mock_broker
    if mock_broker is None:
        mock_broker = MockBroker()
    return mock_broker

class BrokerStatus(BaseModel):
    connected: bool
    broker_name: str
    message: str
    credentials_missing: bool = False

@router.get("/status", response_model=BrokerStatus)
async def get_broker_status():
    """
    Check if Fyers broker is connected
    """
    try:
        # Check if credentials are configured
        if not settings.FYERS_CLIENT_ID or not settings.FYERS_SECRET_KEY:
            logger.warning("Fyers credentials not configured")
            return BrokerStatus(
                connected=False,
                broker_name="Fyers",
                message="Credentials not configured. Please set FYERS_CLIENT_ID and FYERS_SECRET_KEY environment variables.",
                credentials_missing=True
            )
        
        fyers_broker = get_broker()
        is_connected = await fyers_broker.authenticate()
        
        return BrokerStatus(
            connected=is_connected,
            broker_name="Fyers",
            message="Connected" if is_connected else "Disconnected",
            credentials_missing=False
        )
    except Exception as e:
        logger.error(f"Failed to check broker status: {e}")
        return BrokerStatus(
            connected=False,
            broker_name="Fyers",
            message=f"Error: {str(e)}",
            credentials_missing=False
        )

@router.get("/funds", response_model=Dict[str, Any])
async def get_funds():
    """
    Fetch available funds from Fyers
    """
    try:
        fyers_broker = get_broker()
        await fyers_broker.authenticate()
        funds = fyers_broker.client.get_funds()
        
        if funds.get('s') == 'ok':
            return funds.get('fund_limit', [{}])[0] if funds.get('fund_limit') else {}
        else:
            raise HTTPException(status_code=500, detail=funds.get('message', 'Failed to fetch funds'))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch funds: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/demo-status", response_model=BrokerStatus)
async def get_demo_broker_status():
    """
    Check if demo broker is available (for testing without credentials)
    """
    try:
        mock_broker = get_mock_broker()
        is_connected = await mock_broker.authenticate()
        
        return BrokerStatus(
            connected=is_connected,
            broker_name="Demo (Mock)",
            message="Demo broker is ready for testing",
            credentials_missing=False
        )
    except Exception as e:
        logger.error(f"Failed to check demo broker status: {e}")
        return BrokerStatus(
            connected=False,
            broker_name="Demo (Mock)",
            message=f"Error: {str(e)}",
            credentials_missing=False
        )
