"""
Trading Dashboard API
KeepGaining Trading Platform

Comprehensive API endpoints for the trading dashboard.
Provides:
- Portfolio summary with Greeks
- Real-time P&L tracking
- Option chain with Greeks
- Market overview
- Trading controls
"""

from datetime import datetime, date, timezone, timedelta
from typing import Any, Dict, List, Optional
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from loguru import logger

from app.services.realtime_hub import get_data_hub, StreamType
from app.services.upstox_enhanced import create_upstox_enhanced_service, UpstoxEnhancedService


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class PositionGreeks(BaseModel):
    """Position with Greeks."""
    instrument_key: str
    symbol: str
    tradingsymbol: str
    quantity: int
    average_price: float
    ltp: float
    pnl: float
    pnl_percent: float
    # Greeks
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    # Position Greeks (multiplied by quantity)
    position_delta: Optional[float] = None
    position_gamma: Optional[float] = None
    position_theta: Optional[float] = None
    position_vega: Optional[float] = None


class PortfolioSummary(BaseModel):
    """Portfolio summary with aggregated Greeks."""
    total_positions: int
    total_pnl: float
    total_pnl_percent: float
    realized_pnl: float
    unrealized_pnl: float
    margin_used: float
    margin_available: float
    # Aggregated Greeks
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    # Risk metrics
    max_loss: float
    max_profit: float
    breakeven: Optional[float] = None
    # Positions breakdown
    positions: List[PositionGreeks]


class OptionStrikeData(BaseModel):
    """Option strike data for chain."""
    strike_price: float
    # Call data
    call_ltp: Optional[float] = None
    call_iv: Optional[float] = None
    call_delta: Optional[float] = None
    call_gamma: Optional[float] = None
    call_theta: Optional[float] = None
    call_vega: Optional[float] = None
    call_oi: Optional[float] = None
    call_volume: Optional[int] = None
    call_bid: Optional[float] = None
    call_ask: Optional[float] = None
    # Put data
    put_ltp: Optional[float] = None
    put_iv: Optional[float] = None
    put_delta: Optional[float] = None
    put_gamma: Optional[float] = None
    put_theta: Optional[float] = None
    put_vega: Optional[float] = None
    put_oi: Optional[float] = None
    put_volume: Optional[int] = None
    put_bid: Optional[float] = None
    put_ask: Optional[float] = None


class OptionChainResponse(BaseModel):
    """Option chain response."""
    underlying: str
    spot_price: float
    expiry: str
    timestamp: datetime
    # Chain stats
    pcr: float
    max_pain: float
    iv_rank: Optional[float] = None
    # Strikes
    strikes: List[OptionStrikeData]


class MarketOverview(BaseModel):
    """Market overview data."""
    nifty: Dict[str, Any]
    banknifty: Dict[str, Any]
    finnifty: Dict[str, Any]
    sensex: Dict[str, Any]
    market_status: str
    vix: float
    advance_decline: Dict[str, int]
    fii_dii: Dict[str, float]
    timestamp: datetime


class OrderRequest(BaseModel):
    """Order placement request."""
    symbol: str
    exchange: str = "NFO"
    transaction_type: str  # BUY, SELL
    order_type: str  # MARKET, LIMIT, SL, SL-M
    product_type: str  # INTRADAY, DELIVERY, MARGIN
    quantity: int
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    disclosed_quantity: int = 0
    validity: str = "DAY"
    tag: Optional[str] = None


class OrderResponse(BaseModel):
    """Order response."""
    order_id: str
    status: str
    message: str
    timestamp: datetime


# =============================================================================
# Portfolio Endpoints
# =============================================================================

@router.get("/dashboard/portfolio", response_model=PortfolioSummary)
async def get_portfolio_with_greeks():
    """
    Get portfolio summary with Greeks for all positions.
    
    Returns aggregated portfolio Greeks and individual position details.
    """
    try:
        hub = await get_data_hub()
        
        # For now, return mock data structure
        # In production, this would fetch from position manager + Greeks API
        
        positions = []
        net_delta = 0.0
        net_gamma = 0.0
        net_theta = 0.0
        net_vega = 0.0
        total_pnl = 0.0
        
        # TODO: Fetch actual positions from position manager
        # TODO: Enrich with Greeks from Upstox API
        
        return PortfolioSummary(
            total_positions=len(positions),
            total_pnl=total_pnl,
            total_pnl_percent=0.0,
            realized_pnl=0.0,
            unrealized_pnl=total_pnl,
            margin_used=0.0,
            margin_available=0.0,
            net_delta=net_delta,
            net_gamma=net_gamma,
            net_theta=net_theta,
            net_vega=net_vega,
            max_loss=0.0,
            max_profit=0.0,
            positions=positions,
        )
        
    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/positions")
async def get_positions_with_greeks():
    """
    Get all positions with real-time Greeks.
    """
    try:
        # TODO: Implement with actual position manager
        # This would:
        # 1. Get positions from PositionManager
        # 2. Get Greeks from Upstox API for option positions
        # 3. Combine and return
        
        return {"positions": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Option Chain Endpoints
# =============================================================================

@router.get("/dashboard/option-chain/{underlying}", response_model=OptionChainResponse)
async def get_option_chain_with_greeks(
    underlying: str,
    expiry: str = Query(..., description="Expiry date YYYY-MM-DD"),
):
    """
    Get option chain with Greeks for an underlying.
    
    Args:
        underlying: Underlying symbol (NIFTY, BANKNIFTY, etc.)
        expiry: Expiry date in YYYY-MM-DD format
    """
    try:
        hub = await get_data_hub()
        
        # Map symbol to instrument key
        instrument_map = {
            "NIFTY": "NSE_INDEX|Nifty 50",
            "BANKNIFTY": "NSE_INDEX|Nifty Bank",
            "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
            "SENSEX": "BSE_INDEX|SENSEX",
        }
        
        underlying_key = instrument_map.get(underlying.upper(), underlying)
        
        chain = await hub.get_option_chain(underlying_key, expiry)
        
        if not chain:
            raise HTTPException(status_code=404, detail="Option chain not available")
        
        # Convert to response format
        strikes = []
        for strike in chain.strikes:
            strike_data = OptionStrikeData(
                strike_price=strike.strike_price,
            )
            
            if strike.call_data:
                strike_data.call_ltp = strike.call_data.ltp
                strike_data.call_oi = strike.call_data.oi
                strike_data.call_volume = strike.call_data.volume
                strike_data.call_bid = strike.call_data.bid
                strike_data.call_ask = strike.call_data.ask
                
                if strike.call_greeks:
                    strike_data.call_iv = strike.call_greeks.iv
                    strike_data.call_delta = strike.call_greeks.delta
                    strike_data.call_gamma = strike.call_greeks.gamma
                    strike_data.call_theta = strike.call_greeks.theta
                    strike_data.call_vega = strike.call_greeks.vega
            
            if strike.put_data:
                strike_data.put_ltp = strike.put_data.ltp
                strike_data.put_oi = strike.put_data.oi
                strike_data.put_volume = strike.put_data.volume
                strike_data.put_bid = strike.put_data.bid
                strike_data.put_ask = strike.put_data.ask
                
                if strike.put_greeks:
                    strike_data.put_iv = strike.put_greeks.iv
                    strike_data.put_delta = strike.put_greeks.delta
                    strike_data.put_gamma = strike.put_greeks.gamma
                    strike_data.put_theta = strike.put_greeks.theta
                    strike_data.put_vega = strike.put_greeks.vega
            
            strikes.append(strike_data)
        
        return OptionChainResponse(
            underlying=underlying,
            spot_price=chain.spot_price,
            expiry=expiry,
            timestamp=chain.timestamp,
            pcr=chain.pcr or 0.0,
            max_pain=chain.max_pain or 0.0,
            strikes=strikes,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting option chain: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/option-chain/{underlying}/expiries")
async def get_expiry_dates(underlying: str):
    """Get available expiry dates for an underlying."""
    try:
        hub = await get_data_hub()
        
        instrument_map = {
            "NIFTY": "NSE_INDEX|Nifty 50",
            "BANKNIFTY": "NSE_INDEX|Nifty Bank",
            "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
        }
        
        underlying_key = instrument_map.get(underlying.upper(), underlying)
        expiries = await hub.get_option_expiries(underlying_key)
        
        return {
            "underlying": underlying,
            "expiries": [e.isoformat() for e in expiries],
        }
        
    except Exception as e:
        logger.error(f"Error getting expiries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Market Overview Endpoints
# =============================================================================

@router.get("/dashboard/market-overview")
async def get_market_overview():
    """
    Get market overview with index quotes and market status.
    Falls back to Fyers API if realtime hub cache is empty.
    """
    try:
        hub = await get_data_hub()
        
        # Get cached quotes for indices
        indices = {
            "nifty": hub._quote_cache.get("NSE_INDEX|Nifty 50"),
            "banknifty": hub._quote_cache.get("NSE_INDEX|Nifty Bank"),
            "finnifty": hub._quote_cache.get("NSE_INDEX|Nifty Fin Service"),
            "vix": hub._quote_cache.get("NSE_INDEX|India VIX"),
        }
        
        def format_index(quote):
            if not quote:
                return {"ltp": 0, "change": 0, "change_percent": 0}
            return {
                "ltp": quote.ltp,
                "change": quote.change,
                "change_percent": quote.change_percent,
                "open": quote.open,
                "high": quote.high,
                "low": quote.low,
                "prev_close": quote.prev_close,
            }
        
        result = {
            "nifty": format_index(indices["nifty"]),
            "banknifty": format_index(indices["banknifty"]),
            "finnifty": format_index(indices["finnifty"]),
            "vix": format_index(indices["vix"]),
            "market_status": "OPEN" if datetime.now().hour >= 9 and datetime.now().hour < 16 else "CLOSED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        # If cache is empty, try to fetch from Fyers
        if all(v["ltp"] == 0 for v in [result["nifty"], result["banknifty"], result["finnifty"]]):
            try:
                from app.brokers.fyers_client import FyersClient
                from app.core.config import settings
                
                client = FyersClient(
                    client_id=settings.FYERS_CLIENT_ID,
                    secret_key=settings.FYERS_SECRET_KEY,
                    redirect_uri=settings.FYERS_REDIRECT_URI,
                    username=settings.FYERS_USER_ID,
                    pin=settings.FYERS_PIN,
                    totp_key=settings.FYERS_TOTP_KEY
                )
                
                # Fetch quotes for indices
                symbols = ["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "NSE:FINNIFTY-INDEX", "NSE:INDIAVIX-INDEX"]
                quotes_response = client.get_quotes(symbols)
                
                if quotes_response.get("s") == "ok":
                    for quote in quotes_response.get("d", []):
                        symbol = quote.get("n", "")
                        v = quote.get("v", {})
                        data = {
                            "ltp": v.get("lp", 0),
                            "change": v.get("ch", 0),
                            "change_percent": v.get("chp", 0),
                            "open": v.get("open_price", 0),
                            "high": v.get("high_price", 0),
                            "low": v.get("low_price", 0),
                            "prev_close": v.get("prev_close_price", 0),
                        }
                        
                        if "NIFTY50" in symbol:
                            result["nifty"] = data
                        elif "NIFTYBANK" in symbol:
                            result["banknifty"] = data
                        elif "FINNIFTY" in symbol:
                            result["finnifty"] = data
                        elif "INDIAVIX" in symbol:
                            result["vix"] = data
            except Exception as e:
                logger.warning(f"Failed to fetch from Fyers fallback: {e}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting market overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/quotes")
async def get_quotes(symbols: str = Query(..., description="Comma-separated symbols")):
    """
    Get real-time quotes for multiple symbols.
    
    Args:
        symbols: Comma-separated list of symbols
    """
    try:
        hub = await get_data_hub()
        symbol_list = [s.strip() for s in symbols.split(",")]
        
        quotes = []
        for symbol in symbol_list:
            quote = hub._quote_cache.get(symbol)
            if quote:
                quotes.append({
                    "symbol": symbol,
                    "ltp": quote.ltp,
                    "change": quote.change,
                    "change_percent": quote.change_percent,
                    "volume": quote.volume,
                    "oi": quote.oi,
                    "bid": quote.bid,
                    "ask": quote.ask,
                    "timestamp": quote.timestamp.isoformat() if quote.timestamp else None,
                })
        
        return {"quotes": quotes, "count": len(quotes)}
        
    except Exception as e:
        logger.error(f"Error getting quotes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Greeks Endpoints
# =============================================================================

@router.get("/dashboard/greeks")
async def get_greeks(instruments: str = Query(..., description="Comma-separated instrument keys")):
    """
    Get real-time Greeks for option instruments.
    
    Args:
        instruments: Comma-separated instrument keys
    """
    try:
        hub = await get_data_hub()
        
        if not hub._upstox_service:
            raise HTTPException(status_code=503, detail="Upstox service not available")
        
        instrument_list = [i.strip() for i in instruments.split(",")]
        greeks = await hub._upstox_service.get_option_greeks(instrument_list)
        
        return {
            "greeks": [
                {
                    "instrument_key": g.instrument_key,
                    "ltp": g.ltp,
                    "iv": g.iv,
                    "delta": g.delta,
                    "gamma": g.gamma,
                    "theta": g.theta,
                    "vega": g.vega,
                    "timestamp": g.timestamp.isoformat() if g.timestamp else None,
                }
                for g in greeks
            ],
            "count": len(greeks),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Greeks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Order Endpoints
# =============================================================================

@router.post("/dashboard/orders", response_model=OrderResponse)
async def place_order(order: OrderRequest):
    """
    Place an order.
    
    This endpoint integrates with the trading orchestrator
    to place orders in either paper or live mode.
    """
    try:
        # TODO: Integrate with OrderManager/TradingOrchestrator
        # For now, return a mock response
        
        logger.info(f"Order request: {order}")
        
        return OrderResponse(
            order_id="mock_order_123",
            status="PENDING",
            message="Order placement not implemented in this version",
            timestamp=datetime.now(timezone.utc),
        )
        
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/orders")
async def get_orders(
    status: Optional[str] = Query(None, description="Filter by status"),
    date_from: Optional[str] = Query(None, description="From date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="To date YYYY-MM-DD"),
):
    """Get orders with optional filters."""
    try:
        # TODO: Integrate with OrderManager
        return {"orders": [], "count": 0}
        
    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/dashboard/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an order."""
    try:
        # TODO: Integrate with OrderManager
        return {"status": "success", "message": f"Order {order_id} cancellation not implemented"}
        
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Strategy Endpoints
# =============================================================================

@router.get("/dashboard/strategies")
async def get_active_strategies():
    """Get active trading strategies."""
    try:
        # TODO: Integrate with StrategyEngine
        return {
            "strategies": [],
            "count": 0,
        }
        
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: str, enabled: bool = True):
    """Enable or disable a strategy."""
    try:
        # TODO: Integrate with StrategyEngine
        return {
            "strategy_id": strategy_id,
            "enabled": enabled,
            "message": "Strategy toggle not implemented",
        }
        
    except Exception as e:
        logger.error(f"Error toggling strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Risk Metrics Endpoints
# =============================================================================

@router.get("/dashboard/risk-metrics")
async def get_risk_metrics():
    """
    Get portfolio risk metrics.
    
    Returns:
    - VaR (Value at Risk)
    - Maximum drawdown
    - Sharpe ratio
    - Position-wise Greeks exposure
    """
    try:
        # TODO: Calculate from PositionManager + RiskManager
        return {
            "var_1d": 0.0,
            "var_5d": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "beta": 0.0,
            "total_delta_exposure": 0.0,
            "total_gamma_exposure": 0.0,
            "total_theta_exposure": 0.0,
            "total_vega_exposure": 0.0,
            "margin_utilization": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error getting risk metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# P&L Endpoints
# =============================================================================

@router.get("/dashboard/pnl")
async def get_pnl_summary():
    """Get P&L summary."""
    try:
        # TODO: Calculate from PositionManager
        return {
            "today": {
                "realized": 0.0,
                "unrealized": 0.0,
                "total": 0.0,
                "trades": 0,
            },
            "week": {
                "realized": 0.0,
                "unrealized": 0.0,
                "total": 0.0,
                "trades": 0,
            },
            "month": {
                "realized": 0.0,
                "unrealized": 0.0,
                "total": 0.0,
                "trades": 0,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error getting P&L: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/pnl/history")
async def get_pnl_history(
    period: str = Query("1M", regex="^(1D|1W|1M|3M|6M|1Y|ALL)$"),
):
    """Get P&L history for charting."""
    try:
        # TODO: Fetch from database
        return {
            "period": period,
            "data": [],  # [{date, pnl, cumulative_pnl}]
        }
        
    except Exception as e:
        logger.error(f"Error getting P&L history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/today-activity")
async def get_today_activity():
    """
    Get today's trading activity summary.
    Returns order counts by status and active strategies.
    Uses broker abstraction for portable status code handling.
    """
    try:
        from app.brokers.fyers import FyersBroker
        
        fyers_broker = FyersBroker()
        
        # Use the broker's standardized method for order activity
        # This encapsulates broker-specific status code mapping
        summary = await fyers_broker.get_order_activity_summary()
        
        # Get active strategies count (from database or config)
        strategies_running = 0
        try:
            # TODO: Get actual running strategies from strategy manager
            pass
        except Exception:
            pass
        
        return {
            "orders_placed": summary["orders_placed"],
            "orders_executed": summary["orders_executed"],
            "orders_rejected": summary["orders_rejected"],
            "orders_pending": summary["orders_pending"],
            "orders_cancelled": summary["orders_cancelled"],
            "strategies_running": strategies_running,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting today's activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Module Export
# =============================================================================

__all__ = ["router"]
