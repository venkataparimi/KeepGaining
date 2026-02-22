# KeepGaining Trading Platform - Comprehensive Codebase Overview

**Version:** 1.0  
**Last Updated:** December 18, 2025  
**Status:** Production-Ready

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Technology Stack](#3-technology-stack)
4. [Trading Strategies Catalog](#4-trading-strategies-catalog)
5. [Data Models Reference](#5-data-models-reference)
6. [Services Layer](#6-services-layer)
7. [Broker Integrations](#7-broker-integrations)
8. [API Reference Summary](#8-api-reference-summary)
9. [Comet AI Integration](#9-comet-ai-integration)
10. [Development Guide](#10-development-guide)
11. [Scripts Reference](#11-scripts-reference)

---

## 1. Executive Summary

### What is KeepGaining?

KeepGaining is a **production-grade, fully observable, broker-agnostic, UI-driven algorithmic trading platform** designed for the Indian stock market (NSE F&O).

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **Primary Focus** | Options buying intraday strategies (low capital, defined risk) |
| **Asset Coverage** | 180+ F&O stocks, 5+ indices, futures & options |
| **Trading Styles** | Scalping (1-5m), Intraday (5m-1h), Swing, Positional |
| **Data Frequency** | 1-minute base data aggregated to all timeframes |
| **Deployment** | Local-first with cloud-ready architecture |

### Current Data Coverage

| Category | Instruments | Candles |
|----------|-------------|---------|
| **Equity** | 200 | 65.2M |
| **Index** | 15 | 5M |
| **Stock Futures** | 3,239 | 24.3M |
| **Stock Options (CE)** | 31,550 | 113.3M |
| **Stock Options (PE)** | 31,823 | 110.3M |
| **Total** | 72,877 | **340M+** |

---

## 2. Architecture Overview

### System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL SYSTEMS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  DATA SOURCES                    EXECUTION                 REFERENCE        │
│  ├── Fyers (Live feed)          ├── Fyers (Trading)       ├── NSE Website  │
│  ├── Upstox (Historical)        ├── Upstox               └── SEBI         │
│  └── Dhan (Backup)              ├── Zerodha                                │
│                                  └── Angel One                              │
└─────────────────┬───────────────────────────┬───────────────────────────────┘
                  │                           │               
                  ▼                           ▼               
┌─────────────────────────────────────────────────────────────────────────────┐
│                          KEEPGAINING PLATFORM                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Data Feed    │  │  Strategy    │  │     OMS      │  │  Position    │   │
│  │  Service     │  │   Engine     │  │   Service    │  │   Manager    │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         └─────────────────┼─────────────────┼─────────────────┘           │
│                           ▼                 ▼                             │
│                    ┌──────────────────────────────┐                        │
│                    │    EVENT BUS (Redis)         │                        │
│                    └──────────────────────────────┘                        │
│                           │                 │                             │
│                           ▼                 ▼                             │
│                    ┌─────────────┐   ┌─────────────┐                      │
│                    │ PostgreSQL  │   │   Telegram  │                      │
│                    │ TimescaleDB │   │   (Alerts)  │                      │
│                    └─────────────┘   └─────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layered Architecture

| Layer | Components | Purpose |
|-------|------------|---------|
| **Presentation** | Next.js Web UI, Telegram Bot, REST API | User interaction |
| **Application** | Strategy Engine, OMS, Position Manager | Business logic |
| **Integration** | Event Bus (Redis Streams) | Component communication |
| **Data** | PostgreSQL/TimescaleDB, Redis Cache | Persistence & caching |
| **Infrastructure** | Docker Compose, Kubernetes-ready | Deployment |

### Event-Driven Flow

```
TICK → Candle Builder → CANDLE → Strategy Engine → SIGNAL → OMS → ORDER → Broker
                                                                          ↓
                                                                       FILL
                                                                          ↓
                                                              Position Manager
                                                                          ↓
                                                              SL/Target Monitor
```

---

## 3. Technology Stack

### Backend

| Component | Technology | Version |
|-----------|------------|---------|
| **Framework** | FastAPI | Latest |
| **Python** | Python | 3.12+ |
| **ORM** | SQLAlchemy (Async) | 2.x |
| **Database** | PostgreSQL + TimescaleDB | 15+ |
| **Cache** | Redis | 7+ |
| **ML** | Scikit-learn, XGBoost | Latest |
| **Technical Analysis** | TA-Lib, Pandas | Latest |
| **Logging** | Loguru | Latest |

### Frontend

| Component | Technology | Version |
|-----------|------------|---------|
| **Framework** | Next.js | 14.1.0 |
| **UI Library** | React | 18 |
| **Styling** | Tailwind CSS | 3.3.0 |
| **Components** | Radix UI | Latest |
| **TypeScript** | TypeScript | 5.3.3 |

### Infrastructure

| Component | Technology |
|-----------|------------|
| **Containerization** | Docker & Docker Compose |
| **Reverse Proxy** | Nginx |
| **Migrations** | Alembic |

---

## 4. Trading Strategies Catalog

### 4.1 Intraday Momentum OI Strategy

**File:** [`backend/app/strategies/intraday_momentum_oi.py`](file:///c:/code/KeepGaining/backend/app/strategies/intraday_momentum_oi.py)  
**Lines:** 1,349  
**Type:** Price Action + Open Interest

#### Description
A pure price action + OI-based strategy for option buying. **NO technical indicators** (no EMA, RSI, VWAP) - uses only price action and open interest analysis to identify smart money flow.

#### Key Components

| Component | Purpose |
|-----------|---------|
| **Market Phase Detection** | Pre-market, First Hour, Entry Window, Momentum Fade |
| **Bullish CE Setup** | Open above PDH, Day high breakout, Strong body candles |
| **Bearish PE Setup** | Open below PDL, Day low breakdown, Bearish candles |
| **OI Confirmation** | Monitor OI changes to confirm smart money participation |

#### Entry Rules (CE/Bullish)
1. Stock opens above previous day high (PDH)
2. First hour establishes bullish control
3. Day high breakout with volume confirmation
4. 3+ consecutive bullish candles
5. OI increase confirms smart money participation

#### Exit Rules
- **Stop Loss:** 1% initial, with 0.5% trailing
- **Target:** Based on risk:reward ratio
- **Time Exit:** Before 3:15 PM (auto square-off)

#### Configuration

```python
IntradayMomentumConfig(
    market_open=time(9, 15),
    first_hour_end=time(10, 15),
    entry_window_start=time(10, 15),
    entry_window_end=time(14, 00),
    min_gap_percent=0.5,
    min_body_ratio=0.6,
    initial_sl_pct=1.0,
    trailing_sl_pct=0.5,
    max_trades_per_day=2,
)
```

---

### 4.2 EMA Scalping Strategy

**File:** [`backend/app/strategies/ema_scalping.py`](file:///c:/code/KeepGaining/backend/app/strategies/ema_scalping.py)  
**Lines:** 611  
**Type:** Moving Average Crossover with Momentum Filter

#### Description
A high-accuracy scalping strategy using 9/15 EMA crossover with a **30-degree slope filter** for trend confirmation.

#### Entry Rules (Bullish)
1. 9 EMA > 15 EMA (bullish alignment)
2. Slope of both EMAs >= 30 degrees (strong momentum)
3. Dual-index confirmation (BankNifty not at resistance)
4. Valid entry candle pattern:
   - Pin Bar (small body, long wick)
   - Big Body (>60% of range)
   - Engulfing pattern
   - EMA Rejection (touches EMA, bounces)

#### Entry Rules (Bearish)
1. 9 EMA < 15 EMA (bearish alignment)
2. Slope of both EMAs >= 30 degrees downward
3. Dual-index confirmation (Nifty not at support)
4. Bearish candle pattern detected

#### Exit Rules
- **Stop Loss:** 1 ATR from entry
- **Target:** 2:1 Risk-Reward ratio
- **EMA Cross Exit:** If 9 EMA crosses opposite direction

#### Configuration

```python
EMAScalpingConfig(
    fast_ema_period=9,
    slow_ema_period=15,
    min_slope_degrees=30.0,
    slope_lookback_candles=3,
    risk_reward_ratio=2.0,
    max_trades_per_day=3,
    require_dual_index_confirm=True,
)
```

---

### 4.3 Sector Momentum Strategy

**File:** [`backend/app/strategies/sector_momentum.py`](file:///c:/code/KeepGaining/backend/app/strategies/sector_momentum.py)  
**Lines:** 476  
**Type:** Sector Rotation / Morning Gap Strategy

#### Description
Identifies strong sectors at market open and trades stocks within those sectors. Exploits the momentum generated by sector-wide moves.

#### Sector Index Mapping

| Sector | Index |
|--------|-------|
| Banking | NIFTY BANK |
| IT | NIFTY IT |
| Auto | NIFTY AUTO |
| Pharma | NIFTY PHARMA |
| Metals | NIFTY METAL |
| Realty | NIFTY REALTY |
| FMCG | NIFTY FMCG |
| Energy | NIFTY ENERGY |

#### Strategy Logic
1. **9:15-9:30 AM:** Rank all sector indices by:
   - Gap percentage from previous close
   - First candle strength (body ratio)
   - Price vs 9 EMA
2. **Select Top 3 Sectors:** Bullish and Bearish separately
3. **Stock Selection:** Within top sectors, rank stocks by:
   - Alignment with sector direction
   - Volume multiplier
   - Individual stock strength
4. **Trade Entry:** Enter top-ranked stocks with defined SL/Target

#### Scoring Formula

---

### 4.4 Earnings Momentum & Sentiment (EMOS) Strategy

**File:** [`backend/app/strategies/emos_strategy.py`](file:///c:/code/KeepGaining/backend/app/strategies/emos_strategy.py)  
**Lines:** 893  
**Type:** Momentum / Event-Driven

#### Description
Capitalizes on extreme price action clustering around major news catalysts and corporate earnings cycles via technical + volatility breakout measurement. 

#### Entry Rules
1. Volume profile expands significantly vs 20-day baseline > 2.0x.
2. Implied Volatility jumps outside Bollinger Bands threshold.
3. EMA confirms initial breakout direction.

#### Scoring Formula

```
Sector Score = (Gap Score × 40%) + (Candle Strength × 35%) + (Momentum × 25%)
```

---

### 4.4 Indicator-Based Strategies

**File:** [`backend/app/strategies/indicator_strategies.py`](file:///c:/code/KeepGaining/backend/app/strategies/indicator_strategies.py)  
**Type:** Multi-Indicator Confirmation

#### VolumeRocket Strategy

Combines VWMA crossover with Supertrend and volume confirmation.

**Entry Conditions:**
1. VWMA(20) crosses above VWMA(50)
2. Price above Supertrend
3. RSI > 50
4. Volume > 1.5x average

---

### 4.5 Raw Candle Strategies

**File:** [`backend/app/strategies/raw_candle_strategies.py`](file:///c:/code/KeepGaining/backend/app/strategies/raw_candle_strategies.py)  
**Type:** Volume-Based Candle Patterns

Strategies based on pure candle analysis without indicators:
- Volume spike detection
- Support/Resistance breakouts
- Opening range breakouts

---

## 5. Data Models Reference

> [!TIP]
> **Full SQL Schemas Available**: For complete DDL with all columns, indexes, constraints, and TimescaleDB configuration, see **[HIGH_LEVEL_DESIGN.md - Section 4: Data Model](file:///c:/code/KeepGaining/docs/HIGH_LEVEL_DESIGN.md)** (lines 298-900+).

### Master Data Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `instrument_master` | All tradeable instruments | symbol, type, exchange, lot_size |
| `equity_master` | Equity-specific data | sector, market_cap, indices |
| `option_master` | Option contracts | underlying, strike, expiry, option_type |
| `future_master` | Future contracts | underlying, expiry, contract_size |
| `sector_master` | Sector hierarchy | sector_name, index_id |

### Time-Series Data Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `candle_data` | 1-minute OHLCV | instrument_id, timestamp, OHLCV, volume, OI |
| `indicator_data` | Pre-computed indicators | SMA, EMA, RSI, MACD, BB, ATR, etc. |
| `option_greeks` | Option Greeks | IV, delta, gamma, theta, vega |
| `option_chain_snapshot` | Full chain snapshots | strikes, OI, volume, PCR |

### Trading Data Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `strategy_config` | Strategy definitions | name, config JSON, status |
| `strategy_definition` | Entry/exit rules | entry_rules, exit_rules, position_sizing |
| `orders` | Order history | order_id, status, filled_quantity |
| `positions` | Open positions | instrument, quantity, entry_price, SL, target |
| `trades` | Completed trades | entry_price, exit_price, PnL |

### Calendar Tables

| Table | Purpose |
|-------|---------|
| `holiday_calendar` | Market holidays |
| `expiry_calendar` | Options/futures expiries |
| `lot_size_history` | Historical lot size changes |
| `fo_ban_list` | F&O ban stocks |

---

## 6. Services Layer

### Core Services

| Service | File | Purpose |
|---------|------|---------|
| **StrategyEngine** | `strategy_engine.py` | Signal generation, strategy lifecycle |
| **OrderManager** | `order_manager.py` | Order creation, validation, routing |
| **PositionManager** | `position_manager.py` | Position tracking, SL/Target monitoring |
| **RiskManager** | `risk_manager.py` | Risk limits, circuit breakers |

### Data Services

| Service | File | Purpose |
|---------|------|---------|
| **DataDownloadService** | `data_download_service.py` | Historical data backfill |
| **DataOrchestrator** | `data_orchestrator.py` | Data pipeline coordination |
| **CandleBuilder** | `candle_builder.py` | Tick to candle aggregation |
| **IndicatorComputation** | `indicator_computation.py` | Technical indicators |

### Real-Time Services

| Service | File | Purpose |
|---------|------|---------|
| **RealTimeDataHub** | `realtime_hub.py` | Multi-source aggregation |
| **UpstoxEnhanced** | `upstox_enhanced.py` | Upstox with Greeks API |
| **EventPublisher** | `event_publisher.py` | Redis event bus |

### Analytics Services

| Service | File | Purpose |
|---------|------|---------|
| **MLSignalEnhancer** | `ml_signal_enhancer.py` | ML-based signal scoring |
| **SentimentAnalyzer** | `sentiment_analyzer.py` | News/social sentiment |
| **PortfolioOptimizer** | `portfolio_optimizer.py` | Mean-variance, risk parity |
| **TradeAnalytics** | `trade_analytics_service.py` | Performance metrics |

### MCP Automation Services

| Service | File | Purpose |
|---------|------|---------|
| **MCPManager** | `mcp/manager.py` | Master orchestrator of DevTools & Playwright modules |
| **BrokerLogin** | `mcp/automators/broker_login.py` | Auto TOTP resolution and credential lifecycle |
| **TrendlyneScraper**| `mcp/scrapers/trendlyne.py` | Browser-driven F&O scraping from trendlyne |
| **ChartinkScraper** | `mcp/scrapers/chartink.py` | Headless evaluation of custom screener logic |

---

## 7. Broker Integrations

### Supported Brokers

| Broker | Status | Capabilities |
|--------|--------|--------------|
| **Fyers** | ✅ Primary | Live data, Trading, WebSocket |
| **Upstox** | ✅ Active | Historical data, Greeks API, Trading |
| **Zerodha** | ✅ Active | Kite Connect integration |
| **Angel One** | ✅ Active | SmartAPI, GTT orders |

### Broker Files

| File | Purpose |
|------|---------|
| `fyers.py` | Fyers broker adapter |
| `fyers_client.py` | Fyers API client (26KB) |
| `fyers_websocket.py` | Fyers WebSocket streaming |
| `upstox_data.py` | Upstox data service |
| `upstox_live.py` | Upstox trading |
| `upstox_websocket.py` | Upstox WebSocket |
| `zerodha_live.py` | Zerodha Kite integration |
| `angelone.py` | Angel One SmartAPI |
| `unified_order_manager.py` | Multi-broker routing |

### Authentication

All brokers support:
- OAuth 2.0 flow
- TOTP 2FA (where required)
- Token refresh and persistence

---

## 8. API Reference Summary

### Trading APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/trading/start` | POST | Start paper/live trading |
| `/api/trading/status` | GET | System status |
| `/api/trading/portfolio` | GET | Portfolio summary |
| `/api/trading/positions` | GET | Open positions |
| `/api/trading/trades` | GET | Trade history |

### Live Trading APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/live/start` | POST | Start live session |
| `/api/live/orders/place` | POST | Place order |
| `/api/live/orders/{id}/modify` | POST | Modify order |
| `/api/live/orders/{id}/cancel` | POST | Cancel order |

### Market Data APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/dashboard/portfolio` | GET | Portfolio with Greeks |
| `/api/dashboard/option-chain/{underlying}` | GET | Full option chain |
| `/api/dashboard/market-overview` | GET | Index quotes |
| `/api/realtime/ws/stream` | WebSocket | Real-time streaming |

### Analytics APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/analytics/trades` | GET | Trade analytics |
| `/api/analytics/equity-curve` | GET | P&L curve |
| `/api/analytics/daily-pnl` | GET | Daily P&L |
| `/api/advanced-analytics/ml/*` | Various | ML predictions |
| `/api/advanced-analytics/sentiment/*` | Various | Sentiment analysis |

### Broker APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/broker/status` | GET | Broker connection status |
| `/api/upstox/auth/automated` | POST | Automated OAuth |
| `/api/multi-broker/positions` | GET | Unified positions |

---

## 9. Comet AI Integration

### Overview

Comet AI provides intelligent signal validation before trade execution using Perplexity Pro API.

### Validation Flow

```
Signal Generated → TradingOrchestrator → CometSignalValidator → Perplexity Pro
                                                                      ↓
                                                           AI Sentiment Score
                                                                      ↓
                                                        Combined Score Check
                                                                      ↓
                                                         APPROVE or REJECT
```

### Scoring Formula

| Component | Weight |
|-----------|--------|
| Technical Score | 50% |
| AI Sentiment | 35% |
| AI Confidence | 15% |

### Rejection Criteria

- AI detects major risks → Immediate rejection
- AI sentiment < 0.55
- AI confidence < 0.65
- Combined score < 0.65

### Configuration

```python
OrchestratorConfig(
    ai_validation_enabled=True,
    ai_min_sentiment=0.55,
    ai_min_confidence=0.65,
    ai_min_combined_score=0.65,
)
```

---

## 10. Development Guide

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 15+ with TimescaleDB
- Redis 7+

### Quick Start

#### Start Infrastructure

```bash
docker-compose up -d db redis
```

#### Backend Setup

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
# Server on http://localhost:8000
```

#### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Server on http://localhost:3002
```

### Environment Variables

Create `backend/.env`:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/keepgaining

# Redis
REDIS_URL=redis://localhost:6379

# Fyers
FYERS_CLIENT_ID=your_client_id
FYERS_SECRET_KEY=your_secret_key
FYERS_ACCESS_TOKEN=your_token  # Optional

# Upstox
UPSTOX_API_KEY=your_api_key
UPSTOX_API_SECRET=your_secret

# AI
PERPLEXITY_API_KEY=pplx-xxx
ANTHROPIC_API_KEY=your_key
```

### Project Structure

```
KeepGaining/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   ├── brokers/       # Broker integrations
│   │   ├── comet/         # AI integration
│   │   ├── core/          # Configuration
│   │   ├── db/            # Database models
│   │   ├── execution/     # Trading execution
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic
│   │   └── strategies/    # Trading strategies
│   ├── alembic/           # Migrations
│   ├── scripts/           # Utility scripts
│   └── tests/             # Test suite
├── frontend/
│   ├── app/               # Next.js pages
│   ├── components/        # React components
│   └── lib/               # Utilities
└── docs/                  # Documentation
```

---

## 11. Scripts Reference

### Data Management

| Script | Purpose |
|--------|---------|
| `backfill_all_data.py` | Comprehensive data backfill |
| `backfill_equity_data.py` | Equity historical data |
| `backfill_expired_options.py` | Expired options data |
| `generate_dataset.py` | Create ML datasets |
| `refresh_indicators.py` | Recompute indicators |

### Backtesting

| Script | Purpose |
|--------|---------|
| `backtest_strategy_a.py` | Single strategy backtest |
| `backtest_sector_momentum.py` | Sector strategy backtest |
| `backtest_ema_scalping.py` | EMA scalping backtest |
| `multi_strategy_backtest.py` | Multi-strategy comparison |
| `final_realistic_backtest.py` | Production-like backtest |

### Analysis

| Script | Purpose |
|--------|---------|
| `analyze_ce_trades.py` | Call option trade analysis |
| `analyze_pe_exits.py` | Put exit analysis |
| `strategy_discovery_engine.py` | AI-assisted strategy discovery |
| `comprehensive_indicator_analysis.py` | Indicator effectiveness |

### Utilities

| Script | Purpose |
|--------|---------|
| `data_cli.py` | Data management CLI |
| `trading_cli.py` | Trading CLI |
| `refresh_upstox_token.py` | Token refresh |
| `check_fo_coverage.py` | Data coverage check |

---

## Appendix: Related Documents

| Document | Purpose |
|----------|---------|
| [HIGH_LEVEL_DESIGN.md](file:///c:/code/KeepGaining/docs/HIGH_LEVEL_DESIGN.md) | Detailed architecture spec |
| [SETUP_GUIDE.md](file:///c:/code/KeepGaining/SETUP_GUIDE.md) | Installation instructions |
| [PRODUCTION_GUIDE.md](file:///c:/code/KeepGaining/PRODUCTION_GUIDE.md) | Deployment guide |
| [UPSTOX_API_REFERENCE.md](file:///c:/code/KeepGaining/backend/scripts/UPSTOX_API_REFERENCE.md) | Upstox API learnings |

---

**Document Version:** 1.0  
**Created:** December 18, 2025  
**Maintainer:** System Architecture Team
