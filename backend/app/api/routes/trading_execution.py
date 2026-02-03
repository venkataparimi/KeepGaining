"""
Trading Execution API

Comprehensive API for trading operations:
- Trading mode management (paper/live)
- Strategy execution control
- Position and order management
- Portfolio and performance monitoring
- Real-time status and alerts

All endpoints integrate with the TradingOrchestrator.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.execution.orchestrator import (
    TradingOrchestrator,
    TradingMode,
    OrchestratorConfig,
    get_orchestrator,
    create_orchestrator
)
from app.core.events import get_event_bus


router = APIRouter(prefix="/trading", tags=["Trading"])


# ===============================
# Request/Response Models
# ===============================

class StartTradingRequest(BaseModel):
    """Request to start trading system."""
    mode: str = Field(default="paper", description="Trading mode: paper or live")
    strategies: Optional[List[str]] = Field(default=None, description="Strategy IDs to activate")
    initial_capital: Optional[float] = Field(default=None, description="Override initial capital")
    
    class Config:
        json_schema_extra = {
            "example": {
                "mode": "paper",
                "strategies": ["VOLROCKET"],
                "initial_capital": 100000
            }
        }


class AddStrategyRequest(BaseModel):
    """Request to add a strategy."""
    strategy_id: str = Field(..., description="Strategy ID to add")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Strategy configuration")


class ModifyPositionRequest(BaseModel):
    """Request to modify a position."""
    symbol: str = Field(..., description="Symbol to modify")
    stop_loss: Optional[float] = Field(default=None, description="New stop loss price")
    target: Optional[float] = Field(default=None, description="New target price")


class ClosePositionRequest(BaseModel):
    """Request to close a position."""
    symbol: str = Field(..., description="Symbol to close")
    reason: str = Field(default="MANUAL", description="Reason for closing")


class UpdatePriceRequest(BaseModel):
    """Request to update price manually (for testing)."""
    symbol: str = Field(..., description="Symbol to update")
    price: float = Field(..., description="New price")


class SystemStatusResponse(BaseModel):
    """System status response."""
    status: str
    mode: str
    trading_halted: bool
    halt_reason: Optional[str]
    session: Optional[Dict[str, Any]]
    daily_stats: Dict[str, Any]


class PortfolioResponse(BaseModel):
    """Portfolio response."""
    initial_capital: float
    current_capital: float
    available_capital: float
    used_margin: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    total_return_percent: float
    open_positions: int
    total_trades: int
    positions: List[Dict[str, Any]]


class UpdateConfigRequest(BaseModel):
    """Request to update orchestrator configuration."""
    ai_validation_enabled: Optional[bool] = None
    ai_min_sentiment: Optional[float] = None
    ai_min_confidence: Optional[float] = None
    ai_min_combined_score: Optional[float] = None


class PerformanceResponse(BaseModel):
    """Performance metrics response."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_return_percent: float
    profit_factor: float
    max_drawdown_percent: float
    sharpe_ratio: float
    avg_holding_minutes: float


# ===============================
# Dependencies
# ===============================

def get_trading_orchestrator() -> TradingOrchestrator:
    """Get the trading orchestrator instance."""
    return get_orchestrator()


# ===============================
# System Control Endpoints
# ===============================

@router.patch("/config", response_model=Dict[str, Any])
async def update_config(
    request: UpdateConfigRequest,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Update trading orchestrator configuration.
    
    Allows dynamic update of system settings including AI validation.
    """
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Orchestrator not initialized")
    
    updated_fields = {}
    
    # Update AI validation settings
    if request.ai_validation_enabled is not None:
        orchestrator.config.ai_validation_enabled = request.ai_validation_enabled
        updated_fields["ai_validation_enabled"] = request.ai_validation_enabled
        
        # Also update the validator if it exists
        if orchestrator.signal_validator:
            orchestrator.signal_validator.enabled = request.ai_validation_enabled
            
    if request.ai_min_sentiment is not None:
        orchestrator.config.ai_min_sentiment = request.ai_min_sentiment
        updated_fields["ai_min_sentiment"] = request.ai_min_sentiment
        if orchestrator.signal_validator:
            orchestrator.signal_validator.min_sentiment = request.ai_min_sentiment
            
    if request.ai_min_confidence is not None:
        orchestrator.config.ai_min_confidence = request.ai_min_confidence
        updated_fields["ai_min_confidence"] = request.ai_min_confidence
        if orchestrator.signal_validator:
            orchestrator.signal_validator.min_confidence = request.ai_min_confidence
            
    if request.ai_min_combined_score is not None:
        orchestrator.config.ai_min_combined_score = request.ai_min_combined_score
        updated_fields["ai_min_combined_score"] = request.ai_min_combined_score
        if orchestrator.signal_validator:
            orchestrator.signal_validator.min_combined_score = request.ai_min_combined_score
            
    return {
        "status": "success", 
        "message": "Configuration updated",
        "updated_fields": updated_fields,
        "current_config": {
            "ai_validation_enabled": orchestrator.config.ai_validation_enabled,
            "ai_min_sentiment": orchestrator.config.ai_min_sentiment,
            "ai_min_confidence": orchestrator.config.ai_min_confidence,
            "ai_min_combined_score": orchestrator.config.ai_min_combined_score
        }
    }


@router.get("/config", response_model=Dict[str, Any])
async def get_config(
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """Get current orchestrator configuration."""
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Orchestrator not initialized")
        
    return {
        "ai_validation_enabled": orchestrator.config.ai_validation_enabled,
        "ai_min_sentiment": orchestrator.config.ai_min_sentiment,
        "ai_min_confidence": orchestrator.config.ai_min_confidence,
        "ai_min_combined_score": orchestrator.config.ai_min_combined_score,
        "mode": orchestrator.mode,
        "status": orchestrator.status
    }


@router.post("/start", response_model=Dict[str, Any])
async def start_trading(
    request: StartTradingRequest,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Start the trading system.
    
    Initializes the trading system in the specified mode with optional strategies.
    
    - **mode**: Trading mode - "paper" for simulation, "live" for real trading
    - **strategies**: List of strategy IDs to activate
    - **initial_capital**: Override initial capital (paper mode only)
    """
    try:
        # Parse mode
        mode = TradingMode.PAPER if request.mode.lower() == "paper" else TradingMode.LIVE
        
        # Update config if capital specified
        if request.initial_capital and mode == TradingMode.PAPER:
            orchestrator.config.paper_capital = Decimal(str(request.initial_capital))
        
        success = await orchestrator.start(
            mode=mode,
            strategies=request.strategies
        )
        
        if success:
            return {
                "success": True,
                "message": f"Trading system started in {mode.value} mode",
                "status": orchestrator.get_status()
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to start trading system"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error starting trading system: {str(e)}"
        )


@router.post("/stop", response_model=Dict[str, Any])
async def stop_trading(
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Stop the trading system.
    
    Gracefully stops all trading activity and closes the current session.
    Open positions are NOT automatically closed.
    """
    try:
        await orchestrator.stop()
        
        return {
            "success": True,
            "message": "Trading system stopped",
            "final_status": orchestrator.get_status()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error stopping trading system: {str(e)}"
        )


@router.post("/pause", response_model=Dict[str, Any])
async def pause_trading(
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Pause the trading system.
    
    Stops processing new signals while maintaining existing positions.
    """
    await orchestrator.pause()
    
    return {
        "success": True,
        "message": "Trading system paused",
        "status": orchestrator.get_status()
    }


@router.post("/resume", response_model=Dict[str, Any])
async def resume_trading(
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Resume the trading system.
    
    Resumes processing signals after a pause.
    """
    await orchestrator.resume()
    
    return {
        "success": True,
        "message": "Trading system resumed",
        "status": orchestrator.get_status()
    }


@router.post("/switch-mode", response_model=Dict[str, Any])
async def switch_mode(
    mode: str = Query(..., description="New mode: paper or live"),
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Switch trading mode.
    
    Switches between paper and live trading modes.
    Preserves strategy configuration but restarts the session.
    
    **Warning**: Switching to live mode requires live_trading_enabled in config.
    """
    try:
        new_mode = TradingMode.PAPER if mode.lower() == "paper" else TradingMode.LIVE
        
        success = await orchestrator.switch_mode(new_mode)
        
        if success:
            return {
                "success": True,
                "message": f"Switched to {new_mode.value} mode",
                "status": orchestrator.get_status()
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to switch mode. Live trading may be disabled."
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error switching mode: {str(e)}"
        )


# ===============================
# Status Endpoints
# ===============================

@router.get("/status", response_model=Dict[str, Any])
async def get_status(
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Get comprehensive system status.
    
    Returns current trading status, mode, session info, and daily stats.
    """
    return orchestrator.get_status()


@router.get("/portfolio", response_model=Dict[str, Any])
async def get_portfolio(
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Get current portfolio status.
    
    Returns capital, positions, and P&L information.
    """
    portfolio = orchestrator.get_portfolio()
    
    if not portfolio:
        raise HTTPException(
            status_code=404,
            detail="Portfolio data not available. Is trading system running?"
        )
    
    return portfolio


@router.get("/performance", response_model=Dict[str, Any])
async def get_performance(
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Get performance metrics.
    
    Returns comprehensive trading performance statistics including:
    - Win rate
    - Profit factor
    - Sharpe ratio
    - Max drawdown
    """
    performance = orchestrator.get_performance()
    
    if not performance:
        raise HTTPException(
            status_code=404,
            detail="Performance data not available"
        )
    
    return performance


# ===============================
# Strategy Endpoints
# ===============================

@router.post("/strategies/add", response_model=Dict[str, Any])
async def add_strategy(
    request: AddStrategyRequest,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Add and activate a strategy.
    
    Adds a new strategy to the trading system with optional configuration.
    
    **Available Strategies**:
    - `VOLROCKET`: Volume Rocket Strategy (VWMA crossover + Supertrend)
    """
    success = orchestrator.add_strategy(
        strategy_id=request.strategy_id,
        config=request.config
    )
    
    if success:
        return {
            "success": True,
            "message": f"Strategy {request.strategy_id} added",
            "active_strategies": orchestrator.get_status().get("session", {}).get("strategies_active", [])
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to add strategy {request.strategy_id}"
        )


@router.post("/strategies/{strategy_id}/enable", response_model=Dict[str, Any])
async def enable_strategy(
    strategy_id: str,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """Enable a strategy."""
    success = orchestrator.enable_strategy(strategy_id)
    
    if success:
        return {
            "success": True,
            "message": f"Strategy {strategy_id} enabled"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy {strategy_id} not found"
        )


@router.post("/strategies/{strategy_id}/disable", response_model=Dict[str, Any])
async def disable_strategy(
    strategy_id: str,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """Disable a strategy."""
    success = orchestrator.disable_strategy(strategy_id)
    
    if success:
        return {
            "success": True,
            "message": f"Strategy {strategy_id} disabled"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy {strategy_id} not found"
        )


@router.delete("/strategies/{strategy_id}", response_model=Dict[str, Any])
async def remove_strategy(
    strategy_id: str,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """Remove a strategy."""
    success = orchestrator.remove_strategy(strategy_id)
    
    if success:
        return {
            "success": True,
            "message": f"Strategy {strategy_id} removed"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy {strategy_id} not found"
        )


# ===============================
# Position Endpoints
# ===============================

@router.get("/positions", response_model=List[Dict[str, Any]])
async def get_positions(
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Get all open positions.
    
    Returns list of current positions with P&L and SL/Target info.
    """
    return orchestrator.get_positions()


@router.post("/positions/modify", response_model=Dict[str, Any])
async def modify_position(
    request: ModifyPositionRequest,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Modify position stop loss or target.
    
    Updates the SL or target for an existing position.
    """
    if orchestrator.mode != TradingMode.PAPER:
        raise HTTPException(
            status_code=400,
            detail="Position modification only supported in paper mode via API"
        )
    
    if not orchestrator.paper_engine:
        raise HTTPException(
            status_code=400,
            detail="Paper trading engine not running"
        )
    
    result = False
    
    if request.stop_loss:
        result = await orchestrator.paper_engine.modify_position_sl(
            request.symbol,
            Decimal(str(request.stop_loss))
        )
    
    if request.target:
        result = await orchestrator.paper_engine.modify_position_target(
            request.symbol,
            Decimal(str(request.target))
        )
    
    if result:
        return {
            "success": True,
            "message": f"Position {request.symbol} modified"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Position {request.symbol} not found"
        )


@router.post("/positions/close", response_model=Dict[str, Any])
async def close_position(
    request: ClosePositionRequest,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Close a position manually.
    
    Closes the specified position at current market price.
    """
    success = await orchestrator.close_position(
        request.symbol,
        request.reason
    )
    
    if success:
        return {
            "success": True,
            "message": f"Position {request.symbol} closed"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Position {request.symbol} not found or could not be closed"
        )


@router.post("/positions/close-all", response_model=Dict[str, Any])
async def close_all_positions(
    reason: str = Query(default="MANUAL_CLOSE_ALL"),
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Close all open positions.
    
    Emergency function to close all positions immediately.
    """
    positions = orchestrator.get_positions()
    closed = []
    failed = []
    
    for pos in positions:
        symbol = pos.get("symbol")
        success = await orchestrator.close_position(symbol, reason)
        if success:
            closed.append(symbol)
        else:
            failed.append(symbol)
    
    return {
        "success": len(failed) == 0,
        "closed": closed,
        "failed": failed,
        "message": f"Closed {len(closed)} positions, {len(failed)} failed"
    }


# ===============================
# Trade History Endpoints
# ===============================

@router.get("/trades", response_model=List[Dict[str, Any]])
async def get_trades(
    limit: int = Query(default=50, le=500),
    strategy_id: Optional[str] = Query(default=None),
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Get trade history.
    
    Returns list of completed trades with P&L details.
    """
    trades = orchestrator.get_trades()
    
    if strategy_id:
        trades = [t for t in trades if t.get("strategy_id") == strategy_id]
    
    return trades[:limit]


# ===============================
# Testing/Development Endpoints
# ===============================

@router.post("/test/update-price", response_model=Dict[str, Any])
async def update_price(
    request: UpdatePriceRequest,
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Manually update price for a symbol (TESTING ONLY).
    
    This is for testing paper trading without a live data feed.
    In production, prices come from the data feed service.
    """
    if orchestrator.mode != TradingMode.PAPER:
        raise HTTPException(
            status_code=400,
            detail="Manual price updates only available in paper mode"
        )
    
    await orchestrator.update_price(
        request.symbol,
        Decimal(str(request.price))
    )
    
    return {
        "success": True,
        "message": f"Price updated for {request.symbol}: {request.price}"
    }


@router.post("/test/simulate-signal", response_model=Dict[str, Any])
async def simulate_signal(
    symbol: str = Query(...),
    signal_type: str = Query(default="long_entry"),
    entry_price: float = Query(...),
    stop_loss: float = Query(...),
    target: float = Query(...),
    orchestrator: TradingOrchestrator = Depends(get_trading_orchestrator)
):
    """
    Simulate a trading signal (TESTING ONLY).
    
    Manually triggers a signal as if it came from a strategy.
    """
    if orchestrator.mode != TradingMode.PAPER:
        raise HTTPException(
            status_code=400,
            detail="Signal simulation only available in paper mode"
        )
    
    if not orchestrator.paper_engine:
        raise HTTPException(
            status_code=400,
            detail="Paper trading engine not running"
        )
    
    # Update price first
    await orchestrator.update_price(symbol, Decimal(str(entry_price)))
    
    # Create a mock signal
    from app.services.strategy_engine import Signal, SignalType, SignalStrength
    from datetime import timedelta
    
    now = datetime.now()
    signal = Signal(
        signal_id=f"TEST-{now.strftime('%H%M%S')}",
        strategy_id="TEST",
        strategy_name="Manual Test",
        symbol=symbol,
        exchange="NSE",
        signal_type=SignalType(signal_type),
        strength=SignalStrength.MODERATE,
        entry_price=Decimal(str(entry_price)),
        stop_loss=Decimal(str(stop_loss)),
        target_price=Decimal(str(target)),
        quantity_pct=5.0,
        timeframe="5m",
        indicators={},
        reason="Manual test signal",
        generated_at=now,
        valid_until=now + timedelta(minutes=5)
    )
    
    # Execute the signal
    order = await orchestrator.paper_engine.execute_signal(signal)
    
    if order:
        return {
            "success": True,
            "message": f"Signal executed",
            "order": {
                "order_id": order.order_id,
                "status": order.status.value,
                "filled_quantity": order.filled_quantity,
                "average_price": float(order.average_fill_price)
            }
        }
    else:
        return {
            "success": False,
            "message": "Signal could not be executed"
        }
