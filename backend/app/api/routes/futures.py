"""
Futures Trading API Routes

Endpoints for futures-specific trading operations:
- Position management (open, close, modify)
- Contract information
- Rollover management
- MTM settlements
- Margin monitoring
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from loguru import logger


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class FuturesContractResponse(BaseModel):
    """Futures contract information."""
    contract_id: str
    underlying: str
    symbol: str
    exchange: str
    contract_type: str
    expiry_date: date
    lot_size: int
    tick_size: float
    last_price: float
    spot_price: float
    basis: float
    basis_pct: float
    days_to_expiry: int
    is_near_expiry: bool


class FuturesPositionResponse(BaseModel):
    """Futures position information."""
    position_id: str
    symbol: str
    underlying: str
    side: str
    quantity: int  # Lots
    product_type: str
    entry_price: float
    current_price: float
    unrealized_pnl: float
    mtm_pnl: float
    notional_value: float
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    trailing_stop: bool = False
    initial_margin: float
    current_margin: float
    expiry_date: date
    days_to_expiry: int
    needs_rollover: bool
    strategy_id: Optional[str] = None


class OpenFuturesPositionRequest(BaseModel):
    """Request to open a futures position."""
    symbol: str = Field(..., description="Futures symbol like NIFTY24DECFUT")
    side: str = Field(..., pattern="^(LONG|SHORT)$")
    quantity: int = Field(..., gt=0, description="Number of lots")
    product_type: str = Field("NRML", pattern="^(NRML|MIS)$")
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    trailing_stop: bool = False
    strategy_id: Optional[str] = None


class ModifyFuturesPositionRequest(BaseModel):
    """Request to modify a futures position."""
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    trailing_stop: Optional[bool] = None


class CloseFuturesPositionRequest(BaseModel):
    """Request to close a futures position."""
    reason: str = Field("manual", description="Reason for closing")


class RolloverRequest(BaseModel):
    """Request to roll over a position."""
    position_id: str
    new_symbol: str = Field(..., description="New contract symbol")
    strategy: str = Field("auto", pattern="^(auto|spread|close)$")


class MarginRequirementResponse(BaseModel):
    """Margin requirement details."""
    initial_margin: float
    maintenance_margin: float
    exposure_margin: float
    total_margin: float
    margin_percentage: float


class MTMSettlementResponse(BaseModel):
    """MTM settlement record."""
    settlement_date: date
    position_id: str
    previous_price: float
    current_price: float
    mtm_pnl: float
    cumulative_mtm: float


class FuturesPortfolioSummary(BaseModel):
    """Portfolio summary for futures."""
    total_positions: int
    total_unrealized_pnl: float
    total_margin_used: float
    total_notional_value: float
    positions_needing_rollover: int
    positions_by_underlying: dict


# =============================================================================
# Mock Engine (Replace with actual engine instance in production)
# =============================================================================

# In production, this would be injected via dependency injection
_futures_engine = None


def get_futures_engine():
    """Get the futures trading engine instance."""
    global _futures_engine
    if _futures_engine is None:
        from app.execution.futures_trading import create_futures_engine
        _futures_engine = create_futures_engine()
    return _futures_engine


# =============================================================================
# Contract Endpoints
# =============================================================================

@router.get("/futures/contracts", response_model=List[FuturesContractResponse])
async def list_contracts(
    underlying: Optional[str] = Query(None, description="Filter by underlying"),
    exchange: str = Query("NSE", description="Exchange (NSE/BSE)"),
):
    """List available futures contracts."""
    engine = get_futures_engine()
    
    if underlying:
        contracts = engine.get_contracts_for_underlying(underlying)
    else:
        contracts = list(engine._contracts.values())
    
    return [
        FuturesContractResponse(
            contract_id=c.contract_id,
            underlying=c.underlying,
            symbol=c.symbol,
            exchange=c.exchange,
            contract_type=c.contract_type.value,
            expiry_date=c.expiry_date,
            lot_size=c.lot_size,
            tick_size=float(c.tick_size),
            last_price=float(c.last_price),
            spot_price=float(c.spot_price),
            basis=float(c.basis),
            basis_pct=float(c.basis_percentage),
            days_to_expiry=c.days_to_expiry,
            is_near_expiry=c.is_near_expiry,
        )
        for c in contracts
    ]


@router.get("/futures/contracts/{symbol}", response_model=FuturesContractResponse)
async def get_contract(symbol: str):
    """Get contract details by symbol."""
    engine = get_futures_engine()
    
    # Find contract by symbol
    for contract in engine._contracts.values():
        if contract.symbol == symbol:
            return FuturesContractResponse(
                contract_id=contract.contract_id,
                underlying=contract.underlying,
                symbol=contract.symbol,
                exchange=contract.exchange,
                contract_type=contract.contract_type.value,
                expiry_date=contract.expiry_date,
                lot_size=contract.lot_size,
                tick_size=float(contract.tick_size),
                last_price=float(contract.last_price),
                spot_price=float(contract.spot_price),
                basis=float(contract.basis),
                basis_pct=float(contract.basis_percentage),
                days_to_expiry=contract.days_to_expiry,
                is_near_expiry=contract.is_near_expiry,
            )
    
    raise HTTPException(status_code=404, detail=f"Contract not found: {symbol}")


@router.get("/futures/contracts/{underlying}/near-month", response_model=FuturesContractResponse)
async def get_near_month_contract(underlying: str):
    """Get the near month contract for an underlying."""
    engine = get_futures_engine()
    contract = engine.get_near_month_contract(underlying)
    
    if not contract:
        raise HTTPException(status_code=404, detail=f"No contracts found for {underlying}")
    
    return FuturesContractResponse(
        contract_id=contract.contract_id,
        underlying=contract.underlying,
        symbol=contract.symbol,
        exchange=contract.exchange,
        contract_type=contract.contract_type.value,
        expiry_date=contract.expiry_date,
        lot_size=contract.lot_size,
        tick_size=float(contract.tick_size),
        last_price=float(contract.last_price),
        spot_price=float(contract.spot_price),
        basis=float(contract.basis),
        basis_pct=float(contract.basis_percentage),
        days_to_expiry=contract.days_to_expiry,
        is_near_expiry=contract.is_near_expiry,
    )


# =============================================================================
# Position Endpoints
# =============================================================================

@router.get("/futures/positions", response_model=List[FuturesPositionResponse])
async def list_positions(
    underlying: Optional[str] = Query(None, description="Filter by underlying"),
):
    """List all open futures positions."""
    engine = get_futures_engine()
    
    if underlying:
        positions = engine.get_positions_for_underlying(underlying)
    else:
        positions = engine.get_all_positions()
    
    return [
        FuturesPositionResponse(
            position_id=p.position_id,
            symbol=p.contract.symbol,
            underlying=p.contract.underlying,
            side=p.side,
            quantity=p.quantity,
            product_type=p.product_type.value,
            entry_price=float(p.entry_price),
            current_price=float(p.current_price),
            unrealized_pnl=float(p.unrealized_pnl),
            mtm_pnl=float(p.mtm_pnl),
            notional_value=float(p.notional_value),
            stop_loss=float(p.stop_loss) if p.stop_loss else None,
            target=float(p.target) if p.target else None,
            trailing_stop=p.trailing_stop,
            initial_margin=float(p.initial_margin),
            current_margin=float(p.current_margin),
            expiry_date=p.contract.expiry_date,
            days_to_expiry=p.contract.days_to_expiry,
            needs_rollover=p.needs_rollover,
            strategy_id=p.strategy_id,
        )
        for p in positions
    ]


@router.get("/futures/positions/{position_id}", response_model=FuturesPositionResponse)
async def get_position(position_id: str):
    """Get a specific position."""
    engine = get_futures_engine()
    position = engine.get_position(position_id)
    
    if not position:
        raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")
    
    return FuturesPositionResponse(
        position_id=position.position_id,
        symbol=position.contract.symbol,
        underlying=position.contract.underlying,
        side=position.side,
        quantity=position.quantity,
        product_type=position.product_type.value,
        entry_price=float(position.entry_price),
        current_price=float(position.current_price),
        unrealized_pnl=float(position.unrealized_pnl),
        mtm_pnl=float(position.mtm_pnl),
        notional_value=float(position.notional_value),
        stop_loss=float(position.stop_loss) if position.stop_loss else None,
        target=float(position.target) if position.target else None,
        trailing_stop=position.trailing_stop,
        initial_margin=float(position.initial_margin),
        current_margin=float(position.current_margin),
        expiry_date=position.contract.expiry_date,
        days_to_expiry=position.contract.days_to_expiry,
        needs_rollover=position.needs_rollover,
        strategy_id=position.strategy_id,
    )


@router.post("/futures/positions", response_model=FuturesPositionResponse)
async def open_position(request: OpenFuturesPositionRequest):
    """Open a new futures position."""
    engine = get_futures_engine()
    
    # Find contract by symbol
    contract = None
    for c in engine._contracts.values():
        if c.symbol == request.symbol:
            contract = c
            break
    
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract not found: {request.symbol}")
    
    # Open position
    from app.execution.futures_trading import FuturesProductType
    
    position = await engine.open_position(
        contract=contract,
        side=request.side,
        quantity=request.quantity,
        entry_price=contract.last_price,
        product_type=FuturesProductType(request.product_type),
        stop_loss=Decimal(str(request.stop_loss)) if request.stop_loss else None,
        target=Decimal(str(request.target)) if request.target else None,
        strategy_id=request.strategy_id,
    )
    
    if not position:
        raise HTTPException(status_code=400, detail="Failed to open position (limit exceeded?)")
    
    return FuturesPositionResponse(
        position_id=position.position_id,
        symbol=position.contract.symbol,
        underlying=position.contract.underlying,
        side=position.side,
        quantity=position.quantity,
        product_type=position.product_type.value,
        entry_price=float(position.entry_price),
        current_price=float(position.current_price),
        unrealized_pnl=float(position.unrealized_pnl),
        mtm_pnl=float(position.mtm_pnl),
        notional_value=float(position.notional_value),
        stop_loss=float(position.stop_loss) if position.stop_loss else None,
        target=float(position.target) if position.target else None,
        trailing_stop=position.trailing_stop,
        initial_margin=float(position.initial_margin),
        current_margin=float(position.current_margin),
        expiry_date=position.contract.expiry_date,
        days_to_expiry=position.contract.days_to_expiry,
        needs_rollover=position.needs_rollover,
        strategy_id=position.strategy_id,
    )


@router.patch("/futures/positions/{position_id}", response_model=dict)
async def modify_position(position_id: str, request: ModifyFuturesPositionRequest):
    """Modify a futures position."""
    engine = get_futures_engine()
    
    success = await engine.modify_position(
        position_id=position_id,
        stop_loss=Decimal(str(request.stop_loss)) if request.stop_loss else None,
        target=Decimal(str(request.target)) if request.target else None,
        trailing_stop=request.trailing_stop,
    )
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")
    
    return {"success": True, "message": "Position modified"}


@router.delete("/futures/positions/{position_id}", response_model=dict)
async def close_position(position_id: str, request: CloseFuturesPositionRequest):
    """Close a futures position."""
    engine = get_futures_engine()
    
    position = engine.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")
    
    pnl = await engine.close_position(
        position_id=position_id,
        exit_price=position.current_price,
        reason=request.reason,
    )
    
    return {
        "success": True,
        "position_id": position_id,
        "realized_pnl": float(pnl) if pnl else 0,
        "reason": request.reason,
    }


# =============================================================================
# Rollover Endpoints
# =============================================================================

@router.get("/futures/rollover/pending", response_model=List[FuturesPositionResponse])
async def get_pending_rollovers():
    """Get positions that need rollover."""
    engine = get_futures_engine()
    positions = await engine.check_rollovers()
    
    return [
        FuturesPositionResponse(
            position_id=p.position_id,
            symbol=p.contract.symbol,
            underlying=p.contract.underlying,
            side=p.side,
            quantity=p.quantity,
            product_type=p.product_type.value,
            entry_price=float(p.entry_price),
            current_price=float(p.current_price),
            unrealized_pnl=float(p.unrealized_pnl),
            mtm_pnl=float(p.mtm_pnl),
            notional_value=float(p.notional_value),
            stop_loss=float(p.stop_loss) if p.stop_loss else None,
            target=float(p.target) if p.target else None,
            trailing_stop=p.trailing_stop,
            initial_margin=float(p.initial_margin),
            current_margin=float(p.current_margin),
            expiry_date=p.contract.expiry_date,
            days_to_expiry=p.contract.days_to_expiry,
            needs_rollover=p.needs_rollover,
            strategy_id=p.strategy_id,
        )
        for p in positions
    ]


@router.post("/futures/rollover", response_model=FuturesPositionResponse)
async def rollover_position(request: RolloverRequest):
    """Roll over a position to a new contract."""
    engine = get_futures_engine()
    
    # Find new contract
    new_contract = None
    for c in engine._contracts.values():
        if c.symbol == request.new_symbol:
            new_contract = c
            break
    
    if not new_contract:
        raise HTTPException(status_code=404, detail=f"New contract not found: {request.new_symbol}")
    
    from app.execution.futures_trading import RolloverStrategy
    
    strategy = RolloverStrategy(request.strategy)
    new_position = await engine.rollover_position(
        position_id=request.position_id,
        new_contract=new_contract,
        strategy=strategy,
    )
    
    if not new_position:
        raise HTTPException(status_code=400, detail="Rollover failed")
    
    return FuturesPositionResponse(
        position_id=new_position.position_id,
        symbol=new_position.contract.symbol,
        underlying=new_position.contract.underlying,
        side=new_position.side,
        quantity=new_position.quantity,
        product_type=new_position.product_type.value,
        entry_price=float(new_position.entry_price),
        current_price=float(new_position.current_price),
        unrealized_pnl=float(new_position.unrealized_pnl),
        mtm_pnl=float(new_position.mtm_pnl),
        notional_value=float(new_position.notional_value),
        stop_loss=float(new_position.stop_loss) if new_position.stop_loss else None,
        target=float(new_position.target) if new_position.target else None,
        trailing_stop=new_position.trailing_stop,
        initial_margin=float(new_position.initial_margin),
        current_margin=float(new_position.current_margin),
        expiry_date=new_position.contract.expiry_date,
        days_to_expiry=new_position.contract.days_to_expiry,
        needs_rollover=new_position.needs_rollover,
        strategy_id=new_position.strategy_id,
    )


# =============================================================================
# Margin & Portfolio Endpoints
# =============================================================================

@router.get("/futures/margin/{symbol}", response_model=MarginRequirementResponse)
async def get_margin_requirement(
    symbol: str,
    quantity: int = Query(1, gt=0, description="Number of lots"),
    side: str = Query("LONG", pattern="^(LONG|SHORT)$"),
):
    """Get margin requirement for a futures position."""
    engine = get_futures_engine()
    
    # Find contract
    contract = None
    for c in engine._contracts.values():
        if c.symbol == symbol:
            contract = c
            break
    
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract not found: {symbol}")
    
    margin = engine._calculate_margin(contract, quantity, side)
    
    return MarginRequirementResponse(
        initial_margin=float(margin.initial_margin),
        maintenance_margin=float(margin.maintenance_margin),
        exposure_margin=float(margin.exposure_margin),
        total_margin=float(margin.total_margin),
        margin_percentage=float(margin.margin_percentage * 100),
    )


@router.get("/futures/portfolio", response_model=FuturesPortfolioSummary)
async def get_portfolio_summary():
    """Get futures portfolio summary."""
    engine = get_futures_engine()
    summary = engine.get_portfolio_summary()
    
    return FuturesPortfolioSummary(**summary)


# =============================================================================
# MTM Settlement Endpoints
# =============================================================================

@router.get("/futures/settlements", response_model=List[MTMSettlementResponse])
async def get_mtm_settlements(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    position_id: Optional[str] = Query(None),
):
    """Get MTM settlement history."""
    engine = get_futures_engine()
    
    settlements = engine._settlements
    
    # Apply filters
    if start_date:
        settlements = [s for s in settlements if s.settlement_date >= start_date]
    if end_date:
        settlements = [s for s in settlements if s.settlement_date <= end_date]
    if position_id:
        settlements = [s for s in settlements if s.position_id == position_id]
    
    return [
        MTMSettlementResponse(
            settlement_date=s.settlement_date,
            position_id=s.position_id,
            previous_price=float(s.previous_settlement_price),
            current_price=float(s.current_settlement_price),
            mtm_pnl=float(s.mtm_profit_loss),
            cumulative_mtm=float(s.cumulative_mtm),
        )
        for s in settlements
    ]
