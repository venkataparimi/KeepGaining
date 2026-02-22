from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.strategies.emos_strategy import EMOSStrategy
from app.brokers.fyers import FyersBroker
from app.brokers.upstox_data import create_upstox_service
from loguru import logger

router = APIRouter()

class BacktestRequest(BaseModel):
    start_date: datetime
    end_date: datetime
    capital: float = 100000
    risk_per_trade: float = 0.01
    stock_universe: Optional[List[str]] = None

class RunRequest(BaseModel):
    days_ahead: int = 7
    capital: float = 100000
    risk_per_trade: float = 0.01
    stock_universe: Optional[List[str]] = None

async def get_strategy_instance(config: Dict[str, Any]) -> EMOSStrategy:
    """Helper to instantiate strategy with dependencies."""
    broker = FyersBroker()
    # Note: Broker authentication is handled internally or via environment variables
    
    # Initialize Upstox service
    upstox = await create_upstox_service(auto_auth=True)
    
    return EMOSStrategy(broker, upstox, config)

@router.post("/run_emos")
async def run_emos_strategy(request: RunRequest, background_tasks: BackgroundTasks):
    """
    Trigger the EMOS (Earnings Momentum Option Scalping) daily scan.
    
    Scans for upcoming earnings, checks historical momentum, 
    analyzes sentiment, and generates/executes trades.
    """
    try:
        config = {
            "capital": request.capital,
            "days_ahead": request.days_ahead,
            "risk_per_trade": request.risk_per_trade
        }
        if request.stock_universe:
            config["stock_universe"] = request.stock_universe
            
        strategy = await get_strategy_instance(config)
        
        # Run initialization
        await strategy.on_start()
        
        # Run logic in background
        async def run_logic():
            try:
                await strategy.run_daily_scan()
            finally:
                await strategy.on_stop()
                
        background_tasks.add_task(run_logic)
        
        return {
            "status": "success", 
            "message": "EMOS Strategy scan initiated. Check logs for progress.",
            "config": config
        }
    except Exception as e:
        logger.error(f"Failed to initiate EMOS strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/backtest_emos")
async def backtest_emos(request: BacktestRequest):
    """
    Run backtest for EMOS strategy on historical data.
    """
    try:
        config = {
            "capital": request.capital,
            "risk_per_trade": request.risk_per_trade
        }
        if request.stock_universe:
            config["stock_universe"] = request.stock_universe
            
        strategy = await get_strategy_instance(config)
        
        # Initialize (needed for data service)
        await strategy.on_start()
        
        try:
            results = await strategy.backtest(request.start_date, request.end_date)
            return {
                "status": "success",
                "params": {
                    "start_date": request.start_date,
                    "end_date": request.end_date
                },
                "results": results
            }
        finally:
            await strategy.on_stop()
            
    except Exception as e:
        logger.error(f"Failed to run EMOS backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))
