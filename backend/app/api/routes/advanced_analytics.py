"""
Advanced Analytics API Routes

Provides endpoints for:
- ML Signal Enhancement
- Sentiment Analysis
- Portfolio Optimization
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.services.ml_signal_enhancer import get_ml_enhancer, SignalConfidence, MarketRegime
from app.services.sentiment_analyzer import get_sentiment_analyzer, SentimentLevel
from app.services.portfolio_optimizer import get_portfolio_optimizer, OptimizationMethod

import pandas as pd
import numpy as np

router = APIRouter(prefix="/api/analytics/advanced", tags=["Advanced Analytics"])


# ============ ML Signal Enhancement ============

class SignalInput(BaseModel):
    """Input for signal enhancement."""
    signal_type: str = Field(..., description="Signal type: buy, sell, long_entry, etc.")
    symbol: str
    price: float
    strength: float = 1.0
    metadata: Dict[str, Any] = {}


class EnhanceSignalRequest(BaseModel):
    """Request to enhance a signal."""
    signal: SignalInput
    ohlcv_data: List[Dict[str, Any]] = Field(..., description="Recent OHLCV data")


class TrainModelsRequest(BaseModel):
    """Request to train ML models."""
    symbols: List[str]
    days: int = 252


@router.post("/ml/enhance-signal")
async def enhance_signal(request: EnhanceSignalRequest):
    """
    Enhance a trading signal with ML predictions.
    
    Returns ML probability, confidence level, market regime,
    and position sizing recommendations.
    """
    try:
        enhancer = get_ml_enhancer()
        
        # Convert OHLCV to DataFrame
        df = pd.DataFrame(request.ohlcv_data)
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp')
        
        # Ensure required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                raise HTTPException(400, f"Missing required column: {col}")
        
        # Enhance signal
        enhanced = await enhancer.enhance_signal(
            signal=request.signal.model_dump(),
            market_data=df
        )
        
        return {
            "original_signal": enhanced.original_signal,
            "ml_probability": enhanced.ml_probability,
            "confidence": enhanced.confidence.value,
            "regime": enhanced.regime.value,
            "recommended_size_multiplier": enhanced.recommended_size_multiplier,
            "risk_score": enhanced.risk_score,
            "supporting_factors": enhanced.supporting_factors,
            "opposing_factors": enhanced.opposing_factors,
            "feature_importance": enhanced.feature_importance,
            "timestamp": enhanced.timestamp.isoformat(),
        }
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/ml/status")
async def get_ml_status():
    """Get ML model status and metrics."""
    enhancer = get_ml_enhancer()
    return enhancer.get_model_status()


@router.post("/ml/train")
async def train_models(request: TrainModelsRequest):
    """
    Train ML models on historical data.
    
    This is a long-running operation. In production, use
    a background task queue.
    """
    try:
        # This would typically fetch data from database
        # For demo, return placeholder
        return {
            "status": "training_queued",
            "symbols": request.symbols,
            "days": request.days,
            "message": "Training job queued. Check /ml/status for progress.",
        }
        
    except Exception as e:
        raise HTTPException(500, str(e))


# ============ Sentiment Analysis ============

@router.get("/sentiment/symbol/{symbol}")
async def get_symbol_sentiment(symbol: str):
    """
    Get aggregated sentiment for a symbol.
    
    Combines news, social media, options, and institutional flow sentiment.
    """
    try:
        analyzer = get_sentiment_analyzer()
        sentiment = await analyzer.get_aggregate_sentiment(symbol)
        
        return {
            "symbol": sentiment.symbol,
            "score": sentiment.score,
            "level": sentiment.level.value,
            "confidence": sentiment.confidence,
            "sources": sentiment.sources,
            "sample_size": sentiment.sample_size,
            "timestamp": sentiment.timestamp.isoformat(),
        }
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/sentiment/market")
async def get_market_sentiment():
    """
    Get overall market sentiment indicators.
    
    Returns Fear/Greed index, PCR, VIX, FII/DII flows.
    """
    try:
        analyzer = get_sentiment_analyzer()
        sentiment = await analyzer.get_market_sentiment()
        
        return {
            "fear_greed_index": sentiment.fear_greed_index,
            "put_call_ratio": sentiment.put_call_ratio,
            "vix_level": sentiment.vix_level,
            "fii_net_flow": sentiment.fii_net_flow,
            "dii_net_flow": sentiment.dii_net_flow,
            "advance_decline_ratio": sentiment.advance_decline_ratio,
            "sentiment_level": sentiment.sentiment_level.value,
            "timestamp": sentiment.timestamp.isoformat(),
        }
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/sentiment/sector/{sector}")
async def get_sector_sentiment(sector: str):
    """
    Get sentiment for a specific sector.
    
    Sectors: banking, it, pharma, auto, fmcg, energy, metals, realty
    """
    try:
        analyzer = get_sentiment_analyzer()
        return await analyzer.get_sector_sentiment(sector)
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/sentiment/news")
async def get_news_sentiment(
    symbol: Optional[str] = None,
    sector: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100)
):
    """Get news articles with sentiment analysis."""
    try:
        analyzer = get_sentiment_analyzer()
        news = await analyzer.get_news_sentiment(symbol=symbol, sector=sector, limit=limit)
        
        return [
            {
                "title": n.title,
                "source": n.source,
                "url": n.url,
                "published_at": n.published_at.isoformat(),
                "sentiment_score": n.sentiment_score,
                "relevance_score": n.relevance_score,
                "symbols": n.symbols,
                "summary": n.summary,
            }
            for n in news
        ]
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/sentiment/social/{symbol}")
async def get_social_sentiment(symbol: str):
    """Get social media sentiment for a symbol."""
    try:
        analyzer = get_sentiment_analyzer()
        return await analyzer.get_social_sentiment(symbol)
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/sentiment/options/{symbol}")
async def get_options_sentiment(symbol: str):
    """Get options-based sentiment indicators."""
    try:
        analyzer = get_sentiment_analyzer()
        return await analyzer.get_options_sentiment(symbol)
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/sentiment/fii-dii")
async def get_fii_dii_sentiment():
    """Get FII/DII flow sentiment."""
    try:
        analyzer = get_sentiment_analyzer()
        return await analyzer.get_fii_dii_sentiment()
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/sentiment/analyze-text")
async def analyze_text_sentiment(text: str, context: Optional[str] = None):
    """Analyze sentiment of arbitrary text."""
    try:
        analyzer = get_sentiment_analyzer()
        return await analyzer.analyze_text(text, context)
        
    except Exception as e:
        raise HTTPException(500, str(e))


# ============ Portfolio Optimization ============

class OptimizePortfolioRequest(BaseModel):
    """Request to optimize portfolio."""
    prices: Dict[str, List[float]] = Field(..., description="Symbol -> list of closing prices")
    method: str = Field("max_sharpe", description="Optimization method")
    min_weight: float = Field(0.0, ge=0, le=1)
    max_weight: float = Field(0.4, ge=0, le=1)


class BlackLittermanRequest(BaseModel):
    """Request for Black-Litterman optimization."""
    prices: Dict[str, List[float]]
    views: Dict[str, float] = Field(..., description="Symbol -> expected return view")
    view_confidences: Optional[Dict[str, float]] = None


class RebalanceRequest(BaseModel):
    """Request for rebalancing recommendations."""
    current_weights: Dict[str, float]
    target_weights: Dict[str, float]
    threshold: float = Field(0.05, ge=0, le=1)


@router.post("/portfolio/optimize")
async def optimize_portfolio(request: OptimizePortfolioRequest):
    """
    Optimize portfolio allocation.
    
    Methods: max_sharpe, min_volatility, risk_parity, max_return, equal_weight, inverse_volatility
    """
    try:
        optimizer = get_portfolio_optimizer()
        optimizer.min_weight = request.min_weight
        optimizer.max_weight = request.max_weight
        
        # Convert to DataFrame
        df = pd.DataFrame(request.prices)
        
        # Validate method
        try:
            method = OptimizationMethod(request.method)
        except ValueError:
            raise HTTPException(400, f"Invalid method: {request.method}")
        
        allocation = await optimizer.optimize(df, method)
        
        return {
            "weights": allocation.weights,
            "expected_return": allocation.expected_return,
            "volatility": allocation.volatility,
            "sharpe_ratio": allocation.sharpe_ratio,
            "var_95": allocation.var_95,
            "cvar_95": allocation.cvar_95,
            "max_drawdown": allocation.max_drawdown,
            "diversification_ratio": allocation.diversification_ratio,
            "method": allocation.optimization_method.value,
            "timestamp": allocation.timestamp.isoformat(),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/portfolio/efficient-frontier")
async def get_efficient_frontier(
    prices: Dict[str, List[float]],
    n_points: int = Query(50, ge=10, le=200)
):
    """Generate efficient frontier points."""
    try:
        optimizer = get_portfolio_optimizer()
        df = pd.DataFrame(prices)
        
        points = await optimizer.efficient_frontier(df, n_points)
        
        return [
            {
                "return": p.return_,
                "volatility": p.volatility,
                "sharpe_ratio": p.sharpe_ratio,
                "weights": p.weights,
            }
            for p in points
        ]
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/portfolio/risk-contribution")
async def analyze_risk_contribution(
    prices: Dict[str, List[float]],
    weights: Dict[str, float]
):
    """Analyze risk contribution of each asset."""
    try:
        optimizer = get_portfolio_optimizer()
        df = pd.DataFrame(prices)
        
        contributions = await optimizer.risk_contribution_analysis(df, weights)
        
        return [
            {
                "symbol": c.symbol,
                "weight": c.weight,
                "marginal_risk": c.marginal_risk,
                "risk_contribution": c.risk_contribution,
                "risk_contribution_pct": c.risk_contribution_pct,
            }
            for c in contributions
        ]
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/portfolio/rebalance")
async def get_rebalance_recommendations(request: RebalanceRequest):
    """Get portfolio rebalancing recommendations."""
    try:
        optimizer = get_portfolio_optimizer()
        
        recommendations = await optimizer.rebalance_recommendations(
            current_weights=request.current_weights,
            target_weights=request.target_weights,
            threshold=request.threshold
        )
        
        return [
            {
                "symbol": r.symbol,
                "current_weight": r.current_weight,
                "target_weight": r.target_weight,
                "action": r.action,
                "amount_pct": r.amount_pct,
                "reason": r.reason,
            }
            for r in recommendations
        ]
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/portfolio/black-litterman")
async def black_litterman_optimization(request: BlackLittermanRequest):
    """
    Black-Litterman portfolio optimization.
    
    Combines market equilibrium with investor views.
    """
    try:
        optimizer = get_portfolio_optimizer()
        df = pd.DataFrame(request.prices)
        
        allocation = await optimizer.black_litterman(
            prices=df,
            views=request.views,
            view_confidences=request.view_confidences
        )
        
        return {
            "weights": allocation.weights,
            "expected_return": allocation.expected_return,
            "volatility": allocation.volatility,
            "sharpe_ratio": allocation.sharpe_ratio,
            "method": "black_litterman",
            "views_applied": request.views,
            "timestamp": allocation.timestamp.isoformat(),
        }
        
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/portfolio/optimizer-config")
async def get_optimizer_config():
    """Get portfolio optimizer configuration."""
    optimizer = get_portfolio_optimizer()
    return optimizer.get_summary()
