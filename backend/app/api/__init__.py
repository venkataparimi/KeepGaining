"""API router initialization"""
from fastapi import APIRouter
from app.api.routes import (
    positions, strategies, orders, broker, analytics, market, 
    strategy_management, backtest, deployment, trading_mode, 
    broker_management, upstox, calendar, data, trading_execution, websocket,
    dashboard, settings, alerts, trade_chart, trade_analytics, live_trading,
    futures, audit, cache, advanced_analytics, multi_broker, strategy_trades
)
from app.api import comet

api_router = APIRouter()

api_router.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
api_router.include_router(positions.router, prefix="/positions", tags=["positions"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(broker.router, prefix="/broker", tags=["broker"])
api_router.include_router(upstox.router, prefix="/upstox", tags=["upstox"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(comet.router, prefix="/comet", tags=["comet"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(strategy_management.router, prefix="/strategy-management", tags=["strategy-management"])
api_router.include_router(backtest.router, prefix="/backtest", tags=["backtest"])
api_router.include_router(deployment.router, prefix="/deployment", tags=["deployment"])
api_router.include_router(trading_mode.router, prefix="/trading-mode", tags=["trading-mode"])
api_router.include_router(broker_management.router, prefix="/broker-management", tags=["broker-management"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(trade_chart.router, prefix="/trade-chart", tags=["trade-chart"])
api_router.include_router(trade_analytics.router, prefix="/trades", tags=["trade-analytics"])
api_router.include_router(data.router, prefix="/data", tags=["data"])
# New trading execution API with paper/live trading orchestrator
api_router.include_router(trading_execution.router, tags=["trading-execution"])
# Real-time WebSocket streaming API
api_router.include_router(websocket.router, prefix="/realtime", tags=["realtime"])
# Trading dashboard API with Greeks
api_router.include_router(dashboard.router, tags=["dashboard"])
# Live trading with Fyers/Upstox broker integration
api_router.include_router(live_trading.router, prefix="/live", tags=["live-trading"])
# Futures trading API
api_router.include_router(futures.router, tags=["futures"])
# Audit trail API
api_router.include_router(audit.router, tags=["audit"])
# Redis cache management API
api_router.include_router(cache.router, tags=["cache"])
# Advanced Analytics API (ML, Sentiment, Portfolio Optimization)
api_router.include_router(advanced_analytics.router, prefix="/advanced-analytics", tags=["advanced-analytics"])
# Multi-Broker Management API
api_router.include_router(multi_broker.router, prefix="/multi-broker", tags=["multi-broker"])
# Strategy Trades API (backtest results, trade history, analytics)
api_router.include_router(strategy_trades.router, tags=["strategy-trades"])

