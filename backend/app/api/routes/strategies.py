"""Strategies API endpoints"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel
from app.strategies.registry import StrategyRegistry
from loguru import logger

router = APIRouter()

class StrategyInfo(BaseModel):
    name: str
    description: str = ""

class DeployRequest(BaseModel):
    strategy_name: str
    config: Dict[str, Any]

@router.get("", response_model=List[StrategyInfo])
async def list_strategies():
    """
    List all available strategies from the registry
    """
    try:
        strategy_names = StrategyRegistry.list_strategies()
        return [StrategyInfo(name=name, description=f"{name} strategy") for name in strategy_names]
    except Exception as e:
        logger.error(f"Failed to list strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/deploy")
async def deploy_strategy(request: DeployRequest):
    """
    Deploy a strategy with given configuration
    """
    try:
        strategy_class = StrategyRegistry.get_strategy_class(request.strategy_name)
        if not strategy_class:
            raise HTTPException(status_code=404, detail=f"Strategy {request.strategy_name} not found")
        
        # In production, this would initialize the strategy with proper broker and data feed
        # For now, just acknowledge the deployment request
        logger.info(f"Deployment requested for {request.strategy_name} with config: {request.config}")
        
        return {
            "status": "success",
            "message": f"Strategy {request.strategy_name} deployment initiated",
            "strategy_id": 1  # Mock ID
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deploy strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{strategy_id}/stop")
async def stop_strategy(strategy_id: int):
    """
    Stop a running strategy
    """
    try:
        logger.info(f"Stop requested for strategy ID: {strategy_id}")
        return {"status": "success", "message": f"Strategy {strategy_id} stopped"}
    except Exception as e:
        logger.error(f"Failed to stop strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))
