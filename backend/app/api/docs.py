"""
API Documentation Configuration

OpenAPI metadata, tags, and examples for comprehensive API documentation.
"""

# =============================================================================
# API Tags for Organization
# =============================================================================

tags_metadata = [
    {
        "name": "Health",
        "description": "System health checks and status monitoring",
    },
    {
        "name": "Strategies",
        "description": "Trading strategy management and execution",
    },
    {
        "name": "Backtests",
        "description": "Historical strategy backtesting and analysis",
    },
    {
        "name": "Positions",
        "description": "Position tracking and management",
    },
    {
        "name": "Orders",
        "description": "Order placement and management",
    },
    {
        "name": "Brokers",
        "description": "Broker integration and authentication",
    },
    {
        "name": "Data",
        "description": "Market data feeds and historical data",
    },
    {
        "name": "Live Trading",
        "description": "Live trading engine, positions, and execution",
    },
    {
        "name": "Futures",
        "description": "Futures trading and contract management",
    },
    {
        "name": "Alerts",
        "description": "Enhanced alert system and circuit breakers",
    },
    {
        "name": "Audit",
        "description": "Audit trail and compliance logging",
    },
    {
        "name": "Error Handler",
        "description": "Error tracking and service health monitoring",
    },
    {
        "name": "Cache",
        "description": "Redis cache management and statistics",
    },
    {
        "name": "Walk-Forward",
        "description": "Walk-forward backtesting and optimization",
    },
]


# =============================================================================
# API Description
# =============================================================================

description = """
## KeepGaining Trading Platform API

A comprehensive algorithmic trading platform with support for:

* **📊 Multiple Strategies**: Momentum, Mean Reversion, Volume Rocket, Sector Rotation
* **🔄 Live Trading**: Real-time execution with shadow mode and dry-run testing
* **📈 Futures Trading**: Full futures contract management with MTM settlements
* **⚡ Real-time Data**: WebSocket feeds from Fyers and Upstox
* **📉 Backtesting**: Historical analysis with walk-forward optimization
* **🎯 Risk Management**: Position sizing, stop-loss, circuit breakers
* **🔔 Alert System**: Comprehensive alerts for P&L, Greeks, and risk events
* **📝 Audit Trail**: Complete trade history and compliance logging
* **🚀 Redis Caching**: High-performance data caching and pub/sub

### Authentication

Most endpoints require broker authentication. Use the `/brokers/` endpoints to:
1. Exchange OAuth codes for access tokens
2. Authenticate with your broker (Fyers/Upstox)
3. Use the returned tokens for subsequent API calls

### Rate Limiting

API rate limits depend on your broker's limits:
- Fyers: ~10 requests/second
- Upstox: ~25 requests/second

### Error Handling

All errors return JSON with:
```json
{
    "detail": "Error description",
    "error_code": "ERROR_CODE",
    "timestamp": "2024-01-01T00:00:00Z"
}
```

### WebSocket Feeds

Real-time market data available via WebSocket at `/ws/` endpoints.
"""


# =============================================================================
# Example Responses
# =============================================================================

example_backtest_result = {
    "strategy_name": "VolumeRocket",
    "period": {
        "start": "2024-01-01",
        "end": "2024-12-31",
    },
    "performance": {
        "total_return": 45.2,
        "sharpe_ratio": 1.8,
        "max_drawdown": -12.5,
        "win_rate": 62.5,
        "total_trades": 145,
    },
    "trades": [
        {
            "entry_date": "2024-01-15",
            "exit_date": "2024-01-18",
            "symbol": "RELIANCE",
            "pnl": 2500.0,
            "return_pct": 3.5,
        }
    ],
}

example_live_position = {
    "position_id": "POS_20240101_001",
    "symbol": "NIFTY24JAN21000CE",
    "exchange": "NFO",
    "side": "LONG",
    "quantity": 50,
    "average_price": 150.50,
    "current_price": 165.75,
    "unrealized_pnl": 762.50,
    "state": "OPEN",
    "entry_time": "2024-01-01T09:30:00Z",
}

example_futures_contract = {
    "contract_id": "NIFTY24JANFUT",
    "underlying": "NIFTY",
    "exchange": "NFO",
    "contract_type": "INDEX_FUTURE",
    "expiry_date": "2024-01-25",
    "lot_size": 50,
    "tick_size": 0.05,
    "days_to_expiry": 15,
}

example_alert = {
    "alert_id": "ALT_001",
    "rule_id": "RULE_DAILY_LOSS",
    "alert_type": "DAILY_LOSS_LIMIT",
    "severity": "CRITICAL",
    "title": "Daily Loss Limit Breached",
    "message": "Daily loss exceeded ₹5000 threshold",
    "timestamp": "2024-01-01T14:30:00Z",
    "status": "ACTIVE",
}

example_audit_log = {
    "event_id": "AUD_001",
    "timestamp": "2024-01-01T09:30:00Z",
    "event_type": "ORDER_PLACED",
    "user_id": "user123",
    "component": "order_manager",
    "action": "place_order",
    "details": {
        "symbol": "RELIANCE",
        "side": "BUY",
        "quantity": 100,
        "price": 2500.0,
    },
    "status": "SUCCESS",
}

example_error = {
    "error_id": "ERR_001",
    "timestamp": "2024-01-01T10:00:00Z",
    "severity": "ERROR",
    "category": "BROKER",
    "message": "Failed to place order: Insufficient margin",
    "component": "order_manager",
    "stack_trace": "...",
    "recovery_action": "RETRY",
}


# =============================================================================
# OpenAPI Configuration
# =============================================================================

openapi_config = {
    "title": "KeepGaining Trading Platform API",
    "description": description,
    "version": "1.0.0",
    "contact": {
        "name": "KeepGaining Support",
        "url": "https://github.com/keepgaining",
        "email": "support@keepgaining.com",
    },
    "license_info": {
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    "openapi_tags": tags_metadata,
}
