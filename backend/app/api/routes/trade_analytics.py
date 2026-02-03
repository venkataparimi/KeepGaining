"""
Trade Analytics API Routes
Comprehensive trade-level tracking and analysis endpoints
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from app.schemas.trade_analytics import (
    TradeAnalytics, TradeAnalyticsSummary,
    SetStopLossRequest, SetTargetRequest,
    StopLossType, TradeDirection
)
from app.services.trade_analytics_service import get_trade_analytics_service
from app.brokers.fyers import FyersBroker


router = APIRouter()


@router.get("/trade-analytics", response_model=TradeAnalyticsSummary)
async def get_all_trade_analytics():
    """
    Get analytics for all active trades.
    Returns comprehensive data including:
    - Entry context (spot price, IV, Greeks at entry)
    - Current state (P&L, Greeks change)
    - Stop loss recommendations
    - Risk metrics
    """
    try:
        service = get_trade_analytics_service()
        
        # First sync from broker positions
        broker = FyersBroker()
        positions_response = broker.client.get_positions()
        
        if positions_response.get("s") == "ok":
            positions = positions_response.get("netPositions", [])
            await service.sync_from_positions(positions, broker.client)
            
            # Update current prices for all trades with actual spot prices
            for pos in positions:
                symbol = pos.get("symbol", "")
                ltp = pos.get("ltp", 0)
                
                # Fetch actual underlying spot price for options
                spot_price = await service.fetch_underlying_spot_price(symbol, broker.client)
                if spot_price is None:
                    spot_price = ltp  # Fallback to option LTP
                
                await service.update_trade_state(
                    symbol=symbol,
                    current_ltp=ltp,
                    current_spot_price=spot_price
                )
        
        return await service.get_all_trade_analytics()
        
    except Exception as e:
        logger.error(f"Error getting trade analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade-analytics/{symbol}", response_model=TradeAnalytics)
async def get_trade_analytics_by_symbol(symbol: str):
    """
    Get detailed analytics for a specific trade.
    
    Returns:
    - Entry context (spot price, IV, Greeks, market conditions at entry)
    - Stop loss configuration and recommendations
    - Target configuration
    - Current state with real-time P&L and risk metrics
    """
    try:
        service = get_trade_analytics_service()
        broker = FyersBroker()
        positions_response = broker.client.get_positions()
        
        if positions_response.get("s") == "ok":
            positions = positions_response.get("netPositions", [])
            
            # First sync all positions to create analytics if not exists
            await service.sync_from_positions(positions, broker.client)
            
            # Then update the specific trade state with current prices
            for pos in positions:
                if pos.get("symbol") == symbol:
                    ltp = pos.get("ltp", 0)
                    
                    # Fetch actual underlying spot price
                    spot_price = await service.fetch_underlying_spot_price(symbol, broker.client)
                    if spot_price is None:
                        spot_price = ltp  # Fallback
                    
                    await service.update_trade_state(
                        symbol=symbol,
                        current_ltp=ltp,
                        current_spot_price=spot_price
                    )
                    break
        
        analytics = await service.get_trade_analytics(symbol)
        
        if not analytics:
            raise HTTPException(status_code=404, detail=f"No analytics found for {symbol}. Make sure you have an open position for this symbol.")
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trade analytics for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade-analytics/{symbol}/stop-loss")
async def set_trade_stop_loss(symbol: str, request: SetStopLossRequest):
    """
    Set or update stop loss for a trade.
    
    Supports multiple SL types:
    - FIXED: Fixed price SL
    - PERCENTAGE: % from entry
    - ATR_BASED: Based on ATR multiplier
    - TRAILING: Auto-adjusts with price movement
    """
    try:
        service = get_trade_analytics_service()
        
        analytics = await service.set_stop_loss(
            symbol=symbol,
            sl_type=request.sl_type,
            sl_price=request.sl_price,
            sl_percentage=request.sl_percentage,
            trailing_distance=request.trailing_distance,
            trailing_trigger_price=request.trailing_trigger_price
        )
        
        if not analytics:
            raise HTTPException(status_code=404, detail=f"No trade found for {symbol}")
        
        return {
            "success": True,
            "message": f"Stop loss set for {symbol}",
            "stop_loss": analytics.stop_loss
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting stop loss for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade-analytics/{symbol}/target")
async def set_trade_target(symbol: str, request: SetTargetRequest):
    """
    Set or update target for a trade.
    
    Supports:
    - Fixed target price
    - Percentage-based target
    - Partial targets for scaling out
    """
    try:
        service = get_trade_analytics_service()
        
        analytics = await service.set_target(
            symbol=symbol,
            target_price=request.target_price,
            target_percentage=request.target_percentage,
            partial_targets=request.partial_targets
        )
        
        if not analytics:
            raise HTTPException(status_code=404, detail=f"No trade found for {symbol}")
        
        return {
            "success": True,
            "message": f"Target set for {symbol}",
            "targets": analytics.targets
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting target for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade-analytics/{symbol}/sl-recommendation")
async def get_sl_recommendation(symbol: str):
    """
    Get stop loss recommendations for a trade.
    
    Returns multiple SL calculation methods:
    - ATR-based (1.5x ATR)
    - Percentage-based (standard %)
    - Support-based (below key support)
    - Swing low based
    
    Plus a recommended SL with confidence score and reasoning.
    """
    try:
        service = get_trade_analytics_service()
        analytics = await service.get_trade_analytics(symbol)
        
        if not analytics:
            raise HTTPException(status_code=404, detail=f"No trade found for {symbol}")
        
        return analytics.sl_recommendation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SL recommendation for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade-analytics/{symbol}/apply-recommended-sl")
async def apply_recommended_sl(symbol: str):
    """
    Apply the recommended stop loss to the trade.
    """
    try:
        service = get_trade_analytics_service()
        analytics = await service.get_trade_analytics(symbol)
        
        if not analytics:
            raise HTTPException(status_code=404, detail=f"No trade found for {symbol}")
        
        rec = analytics.sl_recommendation
        
        # Apply the recommended SL
        updated = await service.set_stop_loss(
            symbol=symbol,
            sl_type=rec.recommended_sl_type,
            sl_price=rec.recommended_sl
        )
        
        return {
            "success": True,
            "message": f"Applied recommended SL for {symbol}",
            "sl_price": rec.recommended_sl,
            "sl_type": rec.recommended_sl_type,
            "reasoning": rec.reasoning
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying recommended SL for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade-analytics/risk/summary")
async def get_risk_summary():
    """
    Get overall portfolio risk summary.
    
    Returns:
    - Total risk if all SLs hit
    - Portfolio heat (% at risk)
    - Net Greeks exposure
    - Worst case scenario analysis
    """
    try:
        service = get_trade_analytics_service()
        summary = await service.get_all_trade_analytics()
        
        return {
            "total_trades": summary.total_trades,
            "total_unrealized_pnl": summary.total_unrealized_pnl,
            "net_delta": summary.net_delta,
            "net_theta": summary.net_theta,
            "net_vega": summary.net_vega,
            "total_risk_if_sl_hit": summary.total_risk_if_sl_hit,
            "max_single_trade_risk": summary.max_single_trade_risk,
            "portfolio_heat": summary.portfolio_heat,
            "risk_assessment": _assess_risk_level(summary)
        }
        
    except Exception as e:
        logger.error(f"Error getting risk summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _assess_risk_level(summary: TradeAnalyticsSummary) -> dict:
    """Assess overall risk level based on metrics."""
    
    # Simple risk assessment
    risk_score = 0
    warnings = []
    
    if summary.total_risk_if_sl_hit > 10000:
        risk_score += 3
        warnings.append("High total risk exposure")
    
    if abs(summary.net_delta) > 500:
        risk_score += 2
        warnings.append(f"High delta exposure: {summary.net_delta:.0f}")
    
    if summary.net_theta < -500:
        risk_score += 1
        warnings.append(f"Significant theta decay: ₹{summary.net_theta:.0f}/day")
    
    # Determine risk level
    if risk_score >= 4:
        level = "HIGH"
        color = "red"
    elif risk_score >= 2:
        level = "MEDIUM"
        color = "yellow"
    else:
        level = "LOW"
        color = "green"
    
    return {
        "level": level,
        "color": color,
        "score": risk_score,
        "warnings": warnings
    }
