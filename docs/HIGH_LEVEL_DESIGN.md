# KeepGaining Trading Platform
## High-Level Design Document

**Version:** 1.2  
**Date:** December 6, 2025  
**Author:** System Architecture Team  
**Status:** Approved for Implementation

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-28 | Architecture Team | Initial design document |
| 1.1 | 2025-12-02 | System | Added Database Indexes Reference (Section 4.7) |
| 1.2 | 2025-12-06 | System | Added Advanced Analytics (ML, Sentiment, Portfolio) and Multi-Broker Support |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Architecture Design](#3-architecture-design)
4. [Data Model](#4-data-model)
5. [Component Design](#5-component-design)
6. [Multi-Broker Integration](#6-multi-broker-integration)
7. [Market Calendar System](#7-market-calendar-system)
8. [Risk Management](#8-risk-management)
9. [Operational Workflows](#9-operational-workflows)
10. [Deployment Architecture](#10-deployment-architecture)
11. [Frontend Design](#11-frontend-design)
12. [Implementation Phases](#12-implementation-phases)
13. [Technology Stack](#13-technology-stack)
14. [Non-Functional Requirements](#14-non-functional-requirements)
15. [Advanced Analytics](#15-advanced-analytics)
16. [Appendices](#16-appendices)

---

## 1. Executive Summary

### 1.1 Purpose

KeepGaining is a personal algorithmic trading platform designed for intraday options buying strategies with the capability to scale to futures, equities, and swing/positional trading across all timeframes.

### 1.2 Key Objectives

| Objective | Description |
|-----------|-------------|
| **Primary Focus** | Options buying intraday (low capital, defined risk) |
| **Asset Coverage** | 180+ F&O stocks, indices, futures, options |
| **Trading Styles** | Scalping, Intraday, Swing, Positional |
| **Data Frequency** | 1-minute base data, aggregated to all timeframes |
| **Deployment** | Local-first, cloud-ready architecture |
| **Scalability** | Single user today, enterprise-grade design |

### 1.3 Design Principles

1. **Decoupled Architecture** - Components communicate via event bus, independently deployable
2. **Broker Agnostic** - Pluggable data sources and execution brokers
3. **Data Source Agnostic** - Multiple data providers, normalized internal format
4. **Configuration-Driven** - No code changes for environment switches
5. **Stateless Services** - Can restart, scale, or migrate without data loss
6. **Cloud-Ready** - Same code runs locally or in cloud
7. **Single Codebase** - Same code for backtesting, paper trading, and live trading
8. **Test-Driven** - All critical paths must be testable
9. **Fail-Safe** - Graceful degradation and recovery

---

## 2. System Overview

### 2.1 System Context

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL SYSTEMS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DATA SOURCES                    EXECUTION                 REFERENCE        │
│  ├── Fyers (Live feed)          ├── Fyers (Trading)       ├── NSE Website  │
│  ├── Upstox (Historical)        └── Paper Broker          ├── BSE Website  │
│  ├── Dhan (Backup)                   (Simulation)         └── SEBI         │
│  └── NSE Bhavcopy (EOD)                                                    │
│                                                                             │
└─────────────────┬───────────────────────────┬───────────────┬──────────────┘
                  │                           │               │
                  ▼                           ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          KEEPGAINING PLATFORM                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Data Feed    │  │  Strategy    │  │     OMS      │  │  Position    │   │
│  │  Service     │  │   Engine     │  │   Service    │  │   Manager    │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         │                 │                 │                 │           │
│         └─────────────────┼─────────────────┼─────────────────┘           │
│                           ▼                 ▼                             │
│                    ┌──────────────────────────────┐                        │
│                    │    EVENT BUS (Redis)         │                        │
│                    └──────────────────────────────┘                        │
│                           │                 │                             │
│                           ▼                 ▼                             │
│                    ┌─────────────┐   ┌─────────────┐                      │
│                    │ PostgreSQL  │   │   Telegram  │                      │
│                    │  (Storage)  │   │   (Alerts)  │                      │
│                    └─────────────┘   └─────────────┘                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Trading Universe

| Category | Count | Description |
|----------|-------|-------------|
| **F&O Stocks** | 180+ | All NSE F&O enabled equities |
| **Broad Indices** | 5 | NIFTY 50, BANK NIFTY, FINNIFTY, MIDCAP NIFTY, SENSEX |
| **Sectoral Indices** | 10+ | NIFTY IT, NIFTY BANK, NIFTY PHARMA, etc. |
| **Index Derivatives** | Variable | Futures + Options (weekly/monthly expiry) |
| **Stock Derivatives** | Variable | Futures + Options (monthly expiry) |

### 2.3 Supported Trading Styles

| Style | Timeframe | Supported |
|-------|-----------|----------|
| **Scalping** | 1m - 5m | ✅ Phase 2 |
| **Intraday** | 5m - 1h | ✅ Phase 1 (Primary) |
| **Swing** | 1h - Daily | ✅ Phase 2 |
| **Positional** | Daily - Weekly | ✅ Phase 3 |

### 2.4 User Journey

#### Phase 1: Options Buying Intraday

```
PRE-MARKET (8:30 - 9:15)
├── System loads holiday & expiry calendars
├── Fetches previous day's OI data
├── Calculates max pain, PCR for index options
└── Pre-subscribes to index options (ATM ± 10)

MARKET HOURS (9:15 - 3:30)
├── Upstox Batch API scans 180 F&O stocks every 1 minute
├── Strategy Engine identifies opportunities
├── When signal found:
│   ├── Fetch live option chain (500ms)
│   ├── Select optimal strike
│   └── Switch to Fyers WebSocket for execution
├── Position Manager tracks SL/Target
└── Telegram alerts on trades and errors

POST-MARKET (3:30 - 5:00)
├── Download full option chain data (EOD)
├── Download NSE Bhavcopy
├── Compute IV, Greeks for all options
├── Store EOD snapshot
├── Generate daily P&L report
└── Reconcile with broker

OVERNIGHT (Anytime)
├── Run backtests on historical data
├── Analyze OI/IV patterns
├── Optimize strategy parameters
└── Prepare for next day
```

---

## 3. Architecture Design

### 3.1 Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │   Web UI     │  │  Telegram    │  │     API      │                      │
│  │  (Next.js)   │  │   Bot        │  │  Endpoints   │                      │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Data Feed    │  │  Strategy    │  │     OMS      │  │  Position    │   │
│  │  Service     │  │   Engine     │  │   Service    │  │   Manager    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │   Candle     │  │  Backfill    │  │    Broker    │                      │
│  │   Builder    │  │   Service    │  │   Gateway    │                      │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INTEGRATION LAYER                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    EVENT BUS (Redis Streams)                           │ │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │ │
│  │  │ TICK │ │CANDLE│ │SIGNAL│ │ORDER │ │ FILL │ │ POS  │ │ERROR │      │ │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │ PostgreSQL   │  │    Redis     │  │  File Store  │                      │
│  │ (TimeSeries) │  │   (Cache)    │  │   (Backups)  │                      │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INFRASTRUCTURE LAYER                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │   Docker     │  │  Kubernetes  │  │     AWS      │                      │
│  │   Compose    │  │  (Future)    │  │  (Future)    │                      │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Event-Driven Architecture

#### Event Flow Diagram

```
DATA SOURCE          EVENT BUS           CONSUMERS
────────────         ─────────          ──────────

Upstox Batch ──┐
               ├──► TICK Event ────┬──► Candle Builder
Fyers WS ──────┘                   ├──► Strategy Engine
                                   └──► Storage Service

Candle Builder ────► CANDLE Event ─┬──► Strategy Engine
                                   └──► Storage Service

Strategy Engine ───► SIGNAL Event ──► OMS Service

OMS Service ────────► ORDER Event ──┬──► Broker Gateway
                                   └──► Storage Service

Broker Gateway ─────► FILL Event ───┬──► Position Manager
                                   ├──► OMS (ack)
                                   └──► Storage Service

Position Manager ───► POS_UPDATE ───┬──► Dashboard (with Dynamic TS Charts)
                                   ├──► Telegram
                                   └──► Storage Service

Position Manager ───► SL_TRIGGER ───► OMS (exit signal)

Any Service ────────► ERROR Event ──┬──► Telegram
                                   └──► Log Service
```

### 3.3 Component Responsibilities

| Component | Responsibility | NOT Responsible For |
|-----------|----------------|---------------------|
| **Data Feed Service** | Connect to sources, normalize data, publish ticks | Storage, Strategy logic |
| **Candle Builder** | Aggregate ticks to candles, multi-timeframe | Fetching data, Indicators |
| **Indicator Engine** | Compute technical indicators | Signal generation |
| **Strategy Engine** | Generate trading signals | Order execution |
| **OMS** | Risk check, order routing, queue management | Position tracking |
| **Position Manager** | Track positions, SL/Target, trailing | Signal generation |
| **Broker Gateway** | Execute orders via broker APIs | Strategy logic |
| **Storage Service** | Persist all data | Data fetching |
| **Calendar Service** | Holidays, expiries, trading hours | Trading logic |

#### Event Types

| Event | Publisher | Subscribers | Persistence |
|-------|-----------|-------------|-------------|
| `TICK` | Data Feed Service | Candle Builder, Strategy Engine, Position Manager | No |
| `CANDLE` | Candle Builder | Strategy Engine, Storage Service | Yes (1m base) |
| `SIGNAL` | Strategy Engine | OMS Service | Yes |
| `ORDER_REQUEST` | OMS Service | Broker Gateway | Yes |
| `ORDER_PLACED` | Broker Gateway | Position Manager, Storage | Yes |
| `ORDER_FILLED` | Broker Gateway | Position Manager, Storage | Yes |
| `ORDER_REJECTED` | Broker Gateway, OMS | Alerting, Storage | Yes |
| `POSITION_UPDATE` | Position Manager | Dashboard, Storage | Yes |
| `SL_TRIGGERED` | Position Manager | OMS (exit order) | Yes |
| `TARGET_HIT` | Position Manager | OMS (exit order) | Yes |
| `TRAILING_SL_UPDATE` | Position Manager | OMS (modify order) | Yes |
| `BROKER_DISCONNECTED` | Broker Gateway | Alerting, OMS (pause) | Yes |
| `DATA_GAP_DETECTED` | Storage Service | Backfill Service | Yes |
| `BACKFILL_COMPLETE` | Backfill Service | Strategy Engine | No |

---

## 4. Data Model

### 4.1 Master Data Entities

#### 4.1.1 Instrument Master

```sql
CREATE TABLE instrument_master (
    instrument_id UUID PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200),
    instrument_type VARCHAR(20) NOT NULL, -- INDEX, EQUITY, FUTURE, OPTION
    exchange VARCHAR(20) NOT NULL,        -- NSE, BSE, MCX
    segment VARCHAR(20),                  -- CASH, FO, CURRENCY, COMMODITY
    lot_size INTEGER DEFAULT 1,
    tick_size DECIMAL(10,2),
    is_tradeable BOOLEAN DEFAULT true,
    is_fo_enabled BOOLEAN DEFAULT false,
    isin VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_instrument_type ON instrument_master(instrument_type);
CREATE INDEX idx_exchange ON instrument_master(exchange);
CREATE INDEX idx_is_tradeable ON instrument_master(is_tradeable);
```

#### 4.1.2 Equity Master

```sql
CREATE TABLE equity_master (
    instrument_id UUID PRIMARY KEY REFERENCES instrument_master(instrument_id),
    sector_id UUID REFERENCES sector_master(sector_id),
    industry VARCHAR(100),
    market_cap DECIMAL(18,2),
    free_float_percent DECIMAL(5,2),
    face_value DECIMAL(10,2),
    indices JSONB -- Array of index memberships
);
```

#### 4.1.3 Derivative Master (Futures)

```sql
CREATE TABLE future_master (
    instrument_id UUID PRIMARY KEY REFERENCES instrument_master(instrument_id),
    underlying_id UUID REFERENCES instrument_master(instrument_id),
    expiry_date DATE NOT NULL,
    expiry_type VARCHAR(20), -- WEEKLY, MONTHLY, QUARTERLY
    contract_size INTEGER,
    INDEX idx_expiry (expiry_date),
    INDEX idx_underlying (underlying_id)
);
```

#### 4.1.4 Option Master

```sql
CREATE TABLE option_master (
    instrument_id UUID PRIMARY KEY REFERENCES instrument_master(instrument_id),
    underlying_id UUID REFERENCES instrument_master(instrument_id),
    expiry_date DATE NOT NULL,
    expiry_type VARCHAR(20), -- WEEKLY, MONTHLY
    strike_price DECIMAL(10,2) NOT NULL,
    option_type VARCHAR(2) NOT NULL, -- CE, PE
    contract_size INTEGER,
    INDEX idx_expiry (expiry_date),
    INDEX idx_underlying_expiry (underlying_id, expiry_date),
    INDEX idx_strike (strike_price)
);
```

#### 4.1.5 Sector Master

```sql
CREATE TABLE sector_master (
    sector_id UUID PRIMARY KEY,
    sector_name VARCHAR(100) NOT NULL UNIQUE,
    sector_index_id UUID REFERENCES instrument_master(instrument_id),
    parent_sector_id UUID REFERENCES sector_master(sector_id),
    description TEXT
);
```

#### 4.1.6 Index Constituents

```sql
CREATE TABLE index_constituents (
    id SERIAL PRIMARY KEY,
    index_id UUID REFERENCES instrument_master(instrument_id),
    equity_id UUID REFERENCES instrument_master(instrument_id),
    weight DECIMAL(5,2),
    effective_from DATE NOT NULL,
    effective_to DATE,
    INDEX idx_index (index_id),
    INDEX idx_equity (equity_id)
);
```

### 4.2 Time-Series Data

#### 4.2.1 Base Candle (1-Minute)

```sql
CREATE TABLE candle_data (
    instrument_id UUID NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DECIMAL(18,4) NOT NULL,
    high DECIMAL(18,4) NOT NULL,
    low DECIMAL(18,4) NOT NULL,
    close DECIMAL(18,4) NOT NULL,
    volume BIGINT NOT NULL,
    oi BIGINT DEFAULT 0,
    oi_change BIGINT DEFAULT 0,
    trades_count INTEGER,
    vwap DECIMAL(18,4),
    delivery_volume BIGINT,
    PRIMARY KEY (instrument_id, timestamp)
);

-- TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('candle_data', 'timestamp', chunk_time_interval => INTERVAL '1 day');

-- Compression after 7 days
ALTER TABLE candle_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'instrument_id'
);

SELECT add_compression_policy('candle_data', INTERVAL '7 days');
```

#### 4.2.2 Pre-Computed Indicators

```sql
CREATE TABLE indicator_data (
    instrument_id UUID NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    timeframe VARCHAR(10) NOT NULL, -- 1m, 5m, 15m, 1h, 1d
    
    -- Moving Averages
    sma_9 DECIMAL(18,4),
    sma_20 DECIMAL(18,4),
    sma_50 DECIMAL(18,4),
    sma_200 DECIMAL(18,4),
    ema_9 DECIMAL(18,4),
    ema_21 DECIMAL(18,4),
    ema_50 DECIMAL(18,4),
    vwma_20 DECIMAL(18,4),
    vwma_22 DECIMAL(18,4),
    vwma_31 DECIMAL(18,4),
    
    -- Momentum
    rsi_14 DECIMAL(10,4),
    macd DECIMAL(18,4),
    macd_signal DECIMAL(18,4),
    macd_histogram DECIMAL(18,4),
    stoch_k DECIMAL(10,4),
    stoch_d DECIMAL(10,4),
    
    -- Volatility
    atr_14 DECIMAL(18,4),
    bb_upper DECIMAL(18,4),
    bb_middle DECIMAL(18,4),
    bb_lower DECIMAL(18,4),
    bb_width DECIMAL(10,4),
    
    -- Volume
    obv BIGINT,
    volume_sma_20 BIGINT,
    
    -- Trend
    adx_14 DECIMAL(10,4),
    supertrend DECIMAL(18,4),
    supertrend_direction SMALLINT,
    
    PRIMARY KEY (instrument_id, timestamp, timeframe)
);

SELECT create_hypertable('indicator_data', 'timestamp');
```

#### 4.2.3 Option Greeks

```sql
CREATE TABLE option_greeks (
    option_id UUID NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    underlying_price DECIMAL(18,4),
    iv DECIMAL(10,4),         -- Implied Volatility
    delta DECIMAL(10,6),
    gamma DECIMAL(10,6),
    theta DECIMAL(10,6),
    vega DECIMAL(10,6),
    rho DECIMAL(10,6),
    intrinsic_value DECIMAL(18,4),
    extrinsic_value DECIMAL(18,4),
    bid_iv DECIMAL(10,4),
    ask_iv DECIMAL(10,4),
    PRIMARY KEY (option_id, timestamp)
);

SELECT create_hypertable('option_greeks', 'timestamp');
```

#### 4.2.4 Option Chain Snapshot

```sql
CREATE TABLE option_chain_snapshot (
    underlying_id UUID NOT NULL,
    expiry_date DATE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    strike DECIMAL(10,2) NOT NULL,
    ce_ltp DECIMAL(18,4),
    ce_oi BIGINT,
    ce_oi_change BIGINT,
    ce_volume BIGINT,
    ce_iv DECIMAL(10,4),
    ce_delta DECIMAL(10,6),
    pe_ltp DECIMAL(18,4),
    pe_oi BIGINT,
    pe_oi_change BIGINT,
    pe_volume BIGINT,
    pe_iv DECIMAL(10,4),
    pe_delta DECIMAL(10,6),
    pcr DECIMAL(10,4),
    max_pain DECIMAL(10,2),
    PRIMARY KEY (underlying_id, expiry_date, timestamp, strike)
);

SELECT create_hypertable('option_chain_snapshot', 'timestamp');
```

### 4.3 Broker Integration Data

#### 4.3.1 Symbol Mapping

```sql
CREATE TABLE broker_symbol_mapping (
    id SERIAL PRIMARY KEY,
    internal_symbol VARCHAR(50) NOT NULL,
    broker VARCHAR(50) NOT NULL,
    broker_symbol VARCHAR(100) NOT NULL,
    broker_token VARCHAR(50),
    segment VARCHAR(50),
    last_verified TIMESTAMP DEFAULT NOW(),
    UNIQUE(internal_symbol, broker)
);

CREATE INDEX idx_internal_symbol ON broker_symbol_mapping(internal_symbol);
CREATE INDEX idx_broker ON broker_symbol_mapping(broker);
```

#### 4.3.2 Broker Configuration

```sql
CREATE TABLE broker_config (
    broker_name VARCHAR(50) PRIMARY KEY,
    enabled BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 99,
    use_for_live_feed BOOLEAN DEFAULT false,
    use_for_historical BOOLEAN DEFAULT false,
    use_for_trading BOOLEAN DEFAULT false,
    rate_limit_per_second INTEGER,
    rate_limit_per_minute INTEGER,
    websocket_limit INTEGER,
    credentials_encrypted TEXT,
    last_auth_at TIMESTAMP
);
```

#### 4.3.3 Rate Limit Tracker

```sql
CREATE TABLE rate_limit_tracker (
    broker VARCHAR(50) NOT NULL,
    window_type VARCHAR(20) NOT NULL, -- SECOND, MINUTE, HOUR
    window_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER DEFAULT 0,
    limit_value INTEGER,
    PRIMARY KEY (broker, window_type, window_start)
);
```

### 4.4 Calendar & Schedule Data

#### 4.4.1 Expiry Calendar

```sql
CREATE TABLE expiry_calendar (
    expiry_id UUID PRIMARY KEY,
    underlying VARCHAR(50) NOT NULL,
    expiry_type VARCHAR(20) NOT NULL, -- WEEKLY, MONTHLY, QUARTERLY
    scheduled_expiry DATE NOT NULL,
    actual_expiry DATE NOT NULL,
    expiry_day VARCHAR(20),            -- TUESDAY, THURSDAY, etc.
    is_holiday_adjusted BOOLEAN DEFAULT false,
    contract_start DATE,
    is_active BOOLEAN DEFAULT true,
    INDEX idx_underlying (underlying),
    INDEX idx_actual_expiry (actual_expiry)
);
```

#### 4.4.2 Holiday Calendar

```sql
CREATE TABLE holiday_calendar (
    holiday_id UUID PRIMARY KEY,
    date DATE NOT NULL,
    exchange VARCHAR(20) NOT NULL,     -- NSE, BSE, MCX, ALL
    holiday_name VARCHAR(200),
    holiday_type VARCHAR(20),          -- FULL, PARTIAL
    market_open TIME,
    market_close TIME,
    year INTEGER,
    source VARCHAR(100),
    INDEX idx_date (date),
    INDEX idx_exchange (exchange)
);
```

#### 4.4.3 Lot Size History

```sql
-- Track lot size changes over time (critical for backtesting accuracy)
CREATE TABLE lot_size_history (
    id SERIAL PRIMARY KEY,
    instrument_id UUID REFERENCES instrument_master(instrument_id),
    lot_size INTEGER NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,                 -- NULL means current
    source VARCHAR(100),               -- NSE_CIRCULAR, BROKER_API
    created_at TIMESTAMPTZ DEFAULT NOW(),
    INDEX idx_instrument (instrument_id),
    INDEX idx_effective (effective_from, effective_to)
);
```

#### 4.4.4 F&O Ban List

```sql
-- Daily F&O ban list (stocks exceeding OI limits)
CREATE TABLE fo_ban_list (
    id SERIAL PRIMARY KEY,
    instrument_id UUID REFERENCES instrument_master(instrument_id),
    ban_date DATE NOT NULL,
    entry_reason VARCHAR(100),         -- OI_LIMIT_BREACH
    exit_date DATE,                    -- NULL if still banned
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(instrument_id, ban_date)
);

CREATE INDEX idx_ban_date ON fo_ban_list(ban_date);
CREATE INDEX idx_active_bans ON fo_ban_list(instrument_id) WHERE exit_date IS NULL;
```

#### 4.4.5 Master Data Refresh Log

```sql
-- Track when master data was last refreshed
CREATE TABLE master_data_refresh_log (
    id SERIAL PRIMARY KEY,
    data_type VARCHAR(50) NOT NULL,    -- INSTRUMENTS, LOT_SIZES, INDEX_CONSTITUENTS, HOLIDAYS, EXPIRIES
    refresh_date TIMESTAMPTZ NOT NULL,
    records_added INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_deleted INTEGER DEFAULT 0,
    source VARCHAR(100),               -- NSE_WEBSITE, BROKER_API, MANUAL
    status VARCHAR(20),                -- SUCCESS, PARTIAL, FAILED
    error_message TEXT,
    duration_seconds INTEGER
);

CREATE INDEX idx_data_type ON master_data_refresh_log(data_type);
CREATE INDEX idx_refresh_date ON master_data_refresh_log(refresh_date);
```

### 4.5 Trading Data

#### 4.5.1 Strategy Configuration

```sql
CREATE TABLE strategy_config (
    strategy_id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    version VARCHAR(20),
    config JSONB,
    status VARCHAR(20) DEFAULT 'DRAFT', -- DRAFT, PAPER, LIVE, PAUSED, STOPPED
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 4.5.1.2 Strategy Definition (Logic & Rules)

```sql
-- Store high-level strategy logic and conditions
CREATE TABLE strategy_definition (
    definition_id UUID PRIMARY KEY,
    strategy_id UUID REFERENCES strategy_config(strategy_id),
    
    -- Entry Conditions
    entry_rules JSONB NOT NULL,        -- Array of conditions for entry
    entry_timeframe VARCHAR(10),       -- Primary timeframe for entry
    entry_confirmation_tf VARCHAR(10), -- Confirmation timeframe (optional)
    
    -- Exit Conditions
    exit_rules JSONB,                  -- Array of conditions for exit
    sl_type VARCHAR(20),               -- FIXED, ATR_BASED, SWING_LOW, PERCENTAGE
    sl_value DECIMAL(10,4),            -- SL value based on type
    target_type VARCHAR(20),           -- FIXED, RR_RATIO, TRAILING, RESISTANCE
    target_value DECIMAL(10,4),        -- Target value based on type
    trailing_sl_enabled BOOLEAN DEFAULT false,
    trailing_sl_trigger DECIMAL(10,4), -- Trigger point for trailing
    trailing_sl_step DECIMAL(10,4),    -- Step size for trailing
    
    -- Position Sizing
    position_size_type VARCHAR(20),    -- FIXED_QTY, FIXED_VALUE, RISK_PERCENT
    position_size_value DECIMAL(18,4),
    max_positions INTEGER DEFAULT 1,
    
    -- Filters
    instrument_filter JSONB,           -- Which instruments to trade
    time_filter JSONB,                 -- Trading hours, avoid expiry, etc.
    market_filter JSONB,               -- Trend filter, volatility filter
    
    -- Risk Overrides (strategy-level)
    max_daily_loss DECIMAL(18,4),
    max_daily_trades INTEGER,
    consecutive_loss_limit INTEGER,
    
    -- Metadata
    logic_description TEXT,            -- Human-readable description
    version VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_strategy_def_strategy ON strategy_definition(strategy_id);
```

**Entry/Exit Rules JSON Schema:**
```json
{
  "entry_rules": [
    {
      "id": "rule_1",
      "indicator": "ema_21",
      "operator": "crosses_above",
      "compare_to": "ema_50",
      "timeframe": "5m",
      "required": true
    },
    {
      "id": "rule_2",
      "indicator": "rsi_14",
      "operator": "greater_than",
      "value": 50,
      "timeframe": "5m",
      "required": true
    },
    {
      "id": "rule_3",
      "indicator": "supertrend_direction",
      "operator": "equals",
      "value": 1,
      "timeframe": "15m",
      "required": false,
      "weight": 0.5
    }
  ],
  "logic": "(rule_1 AND rule_2) OR (rule_1 AND rule_3)"
}
```

#### 4.5.3 Orders

```sql
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    broker_order_id VARCHAR(50),
    strategy_id UUID REFERENCES strategy_config(strategy_id),
    instrument_id UUID REFERENCES instrument_master(instrument_id),
    side VARCHAR(10) NOT NULL,             -- BUY, SELL
    order_type VARCHAR(20) NOT NULL,       -- MARKET, LIMIT, SL, SL-M
    product_type VARCHAR(20) NOT NULL,     -- MIS, CNC, NRML
    quantity INTEGER NOT NULL,
    price DECIMAL(18,4),                   -- Limit price
    trigger_price DECIMAL(18,4),           -- SL trigger price
    status VARCHAR(20) NOT NULL,           -- PENDING, OPEN, FILLED, CANCELLED, REJECTED
    filled_quantity INTEGER DEFAULT 0,
    avg_fill_price DECIMAL(18,4),
    reject_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_strategy ON orders(strategy_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);
```

#### 4.5.4 Trades

```sql
CREATE TABLE trades (
    trade_id UUID PRIMARY KEY,
    order_id UUID REFERENCES orders(order_id),
    strategy_id UUID REFERENCES strategy_config(strategy_id),
    instrument_id UUID REFERENCES instrument_master(instrument_id),
    broker_order_id VARCHAR(50),
    side VARCHAR(10) NOT NULL,         -- BUY, SELL
    quantity INTEGER NOT NULL,
    entry_price DECIMAL(18,4),
    exit_price DECIMAL(18,4),
    entry_time TIMESTAMPTZ,
    exit_time TIMESTAMPTZ,
    pnl DECIMAL(18,4),
    pnl_percent DECIMAL(10,4),
    commission DECIMAL(18,4),
    status VARCHAR(20),
    metadata JSONB
);

CREATE INDEX idx_trades_strategy ON trades(strategy_id);
CREATE INDEX idx_trades_entry_time ON trades(entry_time);
```

#### 4.5.5 Positions

```sql
CREATE TABLE positions (
    position_id UUID PRIMARY KEY,
    instrument_id UUID REFERENCES instrument_master(instrument_id),
    strategy_id UUID REFERENCES strategy_config(strategy_id),
    side VARCHAR(10),
    quantity INTEGER,
    avg_price DECIMAL(18,4),
    current_price DECIMAL(18,4),
    pnl DECIMAL(18,4),
    unrealized_pnl DECIMAL(18,4),
    sl_price DECIMAL(18,4),
    target_price DECIMAL(18,4),
    trailing_sl BOOLEAN DEFAULT false,
    opened_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.6 Audit & Logs

#### 4.6.1 Signal Log

```sql
CREATE TABLE signal_log (
    signal_id UUID PRIMARY KEY,
    strategy_id UUID,
    instrument_id UUID,
    timestamp TIMESTAMPTZ NOT NULL,
    signal_type VARCHAR(20),
    strength DECIMAL(5,4),
    metadata JSONB,
    executed BOOLEAN DEFAULT false
);

SELECT create_hypertable('signal_log', 'timestamp');
```

#### 4.6.2 Order Log

```sql
CREATE TABLE order_log (
    log_id UUID PRIMARY KEY,
    order_id VARCHAR(50),
    strategy_id UUID,
    instrument_id UUID,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50),            -- CREATED, PLACED, FILLED, REJECTED, CANCELLED
    order_data JSONB,
    broker_response JSONB
);

SELECT create_hypertable('order_log', 'timestamp');
```

### 4.7 Database Indexes Reference

> **Last Updated:** December 2, 2025  
> **Script:** `backend/scripts/analyze_indexes.py`

This section documents all database indexes for performance optimization across UI, strategies, backtesting, and backfill validation.

#### 4.7.1 candle_data (97 GB, 363M+ rows)

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_candle_data` | (instrument_id, timeframe, timestamp) | Primary key, upserts |
| `idx_candle_instrument_time` | (instrument_id, timestamp) | Single instrument queries |
| `idx_candle_time` | (timestamp) | Time range scans |

#### 4.7.2 candle_data_summary (Materialized View)

Pre-aggregated stats for 33,000x faster aggregate queries (0.013s vs 431s).

| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_summary_instrument` | (instrument_id) | Fast instrument lookup |
| `idx_summary_last_date` | (last_date) | Find stale data |

**Refresh after bulk inserts:**
```sql
REFRESH MATERIALIZED VIEW candle_data_summary;
```

#### 4.7.3 instrument_master (19 MB)

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_instrument_master` | (instrument_id) | Primary key |
| `uq_instrument_symbol_exchange` | (trading_symbol, exchange) | Unique constraint |
| `idx_instrument_active` | (is_active) | Filter active instruments |
| `idx_instrument_type` | (instrument_type) | Filter CE/PE/FUTURES/EQ |
| `idx_instrument_underlying` | (underlying) | Filter by underlying |
| `idx_im_trading_symbol` | (trading_symbol) | Symbol lookups |
| `idx_im_segment` | (segment) | Filter by segment |
| `idx_im_type_underlying` | (instrument_type, underlying) | Combined filter |

#### 4.7.4 option_master

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_option_master` | (option_id) | Primary key |
| `idx_option_composite` | (underlying_instrument_id, expiry_date, option_type) | Chain lookup |
| `idx_om_expiry_date` | (expiry_date) | Filter by expiry |
| `idx_om_strike_price` | (strike_price) | Filter by strike |
| `idx_om_underlying_inst` | (underlying_instrument_id) | Filter by underlying |
| `idx_om_option_type` | (option_type) | Filter CE/PE |
| `idx_om_underlying_expiry` | (underlying_instrument_id, expiry_date) | Options chain |
| `idx_om_underlying_expiry_strike` | (underlying_instrument_id, expiry_date, strike_price) | Full chain lookup |

#### 4.7.5 future_master

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_future_master` | (future_id) | Primary key |
| `idx_fm_expiry_date` | (expiry_date) | Filter by expiry |
| `idx_fm_underlying_inst` | (underlying_instrument_id) | Filter by underlying |

#### 4.7.6 indicator_data

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_indicator_data` | (instrument_id, timeframe, timestamp) | Primary key |
| `idx_indicator_time` | (timestamp) | Time range queries |
| `idx_ind_instrument_time` | (instrument_id, timestamp) | Instrument time series |

#### 4.7.7 orders

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_orders` | (order_id) | Primary key |
| `idx_order_status` | (status) | Filter by status |
| `idx_order_created` | (created_at) | Sort by time |
| `idx_order_strategy` | (strategy_id) | Filter by strategy |
| `idx_order_instrument` | (instrument_id) | Filter by instrument |
| `idx_order_broker` | (broker_name) | Filter by broker |
| `idx_ord_status` | (status) | Filter pending/filled |
| `idx_ord_created` | (created_at) | Recent orders |
| `idx_ord_strategy` | (strategy_id) | Strategy orders |

#### 4.7.8 trades

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_trades` | (trade_id) | Primary key |
| `idx_trade_executed` | (executed_at) | Time range queries |
| `idx_trade_strategy` | (strategy_id) | Filter by strategy |
| `idx_trade_order` | (order_id) | Link to order |
| `idx_trade_instrument` | (instrument_id) | Filter by instrument |
| `idx_trd_executed_at` | (executed_at) | Sort by execution time |

#### 4.7.9 positions

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_positions` | (position_id) | Primary key |
| `idx_position_status` | (status) | Open/closed filter |
| `idx_position_strategy` | (strategy_id) | Filter by strategy |
| `idx_position_instrument` | (instrument_id) | Filter by instrument |
| `idx_pos_instrument` | (instrument_id) | Position lookup |
| `idx_pos_strategy` | (strategy_id) | Strategy positions |

#### 4.7.10 signal_log

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_signal_log` | (signal_id) | Primary key |
| `idx_signal_time` | (generated_at) | Time range queries |
| `idx_signal_strategy` | (strategy_id) | Filter by strategy |
| `idx_signal_type` | (signal_type) | Filter by signal type |
| `idx_sig_generated_at` | (generated_at) | Recent signals |
| `idx_sig_strategy` | (strategy_id) | Strategy signals |

#### 4.7.11 option_chain_snapshot

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_option_chain_snapshot` | (snapshot_id) | Primary key |
| `idx_chain_time` | (timestamp) | Time range queries |
| `idx_chain_underlying` | (underlying_instrument_id) | Filter by underlying |
| `idx_chain_expiry` | (expiry_date) | Filter by expiry |
| `idx_ocs_timestamp` | (timestamp) | Time series |
| `idx_ocs_underlying_inst` | (underlying_instrument_id) | Underlying lookup |
| `idx_ocs_expiry_date` | (expiry_date) | Expiry filter |

#### 4.7.12 option_greeks

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_option_greeks` | (option_id, timestamp) | Primary key |
| `idx_greeks_time` | (timestamp) | Time range queries |
| `idx_og_option_time` | (option_id, timestamp) | Greeks time series |

#### 4.7.13 expiry_calendar

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_expiry_calendar` | (expiry_id) | Primary key |
| `idx_expiry_date` | (expiry_date) | Find expiries |
| `idx_expiry_underlying` | (underlying) | Filter by underlying |
| `idx_ec_expiry_date` | (expiry_date) | Expiry lookup |
| `idx_ec_underlying` | (underlying) | Underlying filter |

#### 4.7.14 daily_pnl

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_daily_pnl` | (pnl_id) | Primary key |
| `idx_pnl_date` | (date) | Filter by date |
| `idx_pnl_strategy` | (strategy_id) | Filter by strategy |

#### 4.7.15 Index Maintenance Scripts

| Script | Purpose |
|--------|---------|
| `backend/scripts/analyze_indexes.py` | Analyze and create missing indexes |
| `backend/scripts/optimize_indexes.py` | Create materialized views and optimize |
| `backend/scripts/verify_coverage.py` | Fast data coverage check using summary view |

---

## 5. Component Design

### 5.1 Data Feed Service

#### Responsibilities
- Connect to multiple data sources (WebSocket, REST, File)
- Normalize tick data to internal format
- Publish to event bus
- Handle reconnection and failover

#### Interfaces

```python
class DataSource(ABC):
    @abstractmethod
    async def connect(self, symbols: List[str], on_tick: Callable)
    
    @abstractmethod
    async def disconnect(self)
    
    @abstractmethod
    async def subscribe(self, symbols: List[str])
    
    @abstractmethod
    async def unsubscribe(self, symbols: List[str])
```

#### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `sources` | `[fyers_ws, upstox_batch]` | Active data sources |
| `primary_source` | `fyers_ws` | Primary for live trading |
| `fallback_source` | `upstox_batch` | Fallback if primary fails |
| `batch_interval` | `60` | Seconds between batch polls |
| `reconnect_delay` | `5` | Seconds before reconnect attempt |
| `max_reconnect_attempts` | `5` | Max reconnection tries |

### 5.2 Candle Builder Service

#### Responsibilities
- Aggregate ticks into 1-minute candles
- Build higher timeframe candles (5m, 15m, 1h, daily)
- Publish completed candles to event bus

#### Aggregation Rules

| Timeframe | Source | Alignment | Completion Event |
|-----------|--------|-----------|------------------|
| 1m | Ticks | :00, :01, :02... | On next minute start |
| 5m | 5 × 1m | :00, :05, :10... | After 5th minute complete |
| 15m | 15 × 1m | :00, :15, :30, :45 | After 15th minute complete |
| 1h | 60 × 1m | :00 each hour | After hour complete |
| 1d | All day's 1m | Market open (09:15) | At market close |

### 5.3 Strategy Engine

#### Responsibilities
- Load registered strategies
- Process market data (ticks/candles)
- Generate trading signals
- Publish signals to OMS

#### Strategy Interface

```python
class BaseStrategy(ABC):
    @abstractmethod
    async def on_tick(self, tick: Tick) -> Optional[Signal]
    
    @abstractmethod
    async def on_candle(self, candle: Candle) -> Optional[Signal]
    
    @abstractmethod
    async def on_start(self)
    
    @abstractmethod
    async def on_stop(self)
```

#### Signal Format

```python
@dataclass
class Signal:
    strategy_id: str
    symbol: str
    direction: str          # BUY, SELL, EXIT
    strength: float         # 0-1 confidence
    sl_price: Optional[float]
    target_price: Optional[float]
    metadata: dict
    timestamp: datetime
```

### 5.4 Order Management System (OMS)

#### Responsibilities
- Receive signals from strategies
- Validate against risk rules
- Queue orders for execution
- Route to broker gateway
- Track order lifecycle

#### Order States

```
CREATED → VALIDATED → QUEUED → SENT → PENDING → FILLED
                                            ↓
                                      CANCELLED
                                            ↓
                                       REJECTED
```

#### Risk Checks

| Check | Description | Action on Failure |
|-------|-------------|-------------------|
| Position Limit | Max positions per strategy | Reject order |
| Order Size | Max order value | Reject order |
| Daily Loss Limit | Max loss per day | Halt trading |
| Consecutive Losses | Max losses in a row | Pause strategy |
| Restricted Symbol | Banned instruments | Reject order |
| Market Hours | Trading allowed | Reject order |

### 5.5 Position Manager

#### Responsibilities
- Track open positions
- Monitor SL/Target levels
- Implement trailing stop loss
- Emit exit signals to OMS
- Calculate P&L

#### Position Lifecycle

```
SIGNAL → ENTRY_ORDER → POSITION_OPEN → MONITOR
                                    ↓
                                SL/TARGET
                                    ↓
                              EXIT_ORDER
                                    ↓
                            POSITION_CLOSED
```

#### Trailing SL Logic

```
For Long Position:
1. Track highest_price_since_entry
2. If current_price > highest_price:
     highest_price = current_price
     new_sl = current_price × (1 - trailing_percent)
     if new_sl > current_sl:
         current_sl = new_sl
         Emit MODIFY_SL event
```

### 5.6 Broker Gateway

#### Responsibilities
- Translate internal orders to broker format
- Execute via broker API
- Handle broker responses
- Publish fill/rejection events

#### Broker Adapter Interface

```python
class BaseBroker(ABC):
    @abstractmethod
    async def authenticate(self) -> bool
    
    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResponse
    
    @abstractmethod
    async def modify_order(self, order_id: str, changes: dict) -> OrderResponse
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> OrderResponse
    
    @abstractmethod
    async def get_positions(self) -> List[Position]
    
    @abstractmethod
    async def get_orders(self) -> List[Order]
```

### 5.7 Storage Service

#### Responsibilities
- Subscribe to relevant events
- Batch writes for efficiency
- Store tick/candle/trade data
- Provide query interface

#### Storage Strategy

| Data Type | Storage | Batch Size | Flush Interval |
|-----------|---------|------------|----------------|
| Ticks | Optional | 1000 | 10 seconds |
| 1m Candles | Required | 100 | 60 seconds |
| Indicators | Required | 100 | 60 seconds |
| Trades | Required | 1 | Immediate |
| Signals | Required | 10 | 5 seconds |

### 5.8 Backfill Service

#### Responsibilities
- Detect data gaps
- Fetch missing historical data
- Distribute requests across brokers
- Respect rate limits

#### Gap Detection

```
For each instrument:
1. Query last timestamp in database
2. If gap > 1 minute:
     Calculate missing range
3. Split range into chunks (90 days for intraday)
4. Distribute across brokers based on rate limits
5. Fetch and store
```

---

## 6. Multi-Broker Integration

### 6.1 Supported Brokers

| Broker | Live Feed | Historical | Trading | Expired Data |
|--------|-----------|------------|---------|--------------|
| **Fyers** | ✅ WebSocket (200) | ✅ 200/min | ✅ Primary | ⚠️ Limited |
| **Upstox** | ✅ WebSocket (4000) | ✅ 2000/min | ⚠️ Possible | ✅ Yes |
| **Zerodha** | ✅ WebSocket (3000) | ✅ 180/min | ✅ Possible | ⚠️ Limited |
| **Dhan** | ✅ WebSocket | ✅ Liberal | ✅ Possible | ✅ Yes |

### 6.2 Data Source Strategy

```
LIVE TRADING:
├── Primary: Fyers WebSocket (instruments in active positions)
└── Scanning: Upstox Batch API (all 180 stocks, every 1 min)

HISTORICAL DATA:
├── Primary: Upstox (2000/min - bulk download)
├── Fallback: Fyers (if Upstox unavailable)
└── Expired: Upstox (dedicated API)

ORDER EXECUTION:
└── Fyers (trading account)
```

### 6.3 Symbol Normalization

#### Internal Symbol Format

```
TYPE:UNDERLYING[EXPIRY][STRIKE][OPTION_TYPE]

Examples:
- NSE:RELIANCE           (Equity)
- NSE:NIFTY50           (Index)
- NSE:RELIANCE24DECFUT  (Future)
- NSE:NIFTY24DEC19000CE (Option)
```

#### Broker Mapping Examples

| Internal | Fyers | Upstox | Zerodha |
|----------|-------|--------|---------|
| `NSE:RELIANCE` | `NSE:RELIANCE-EQ` | `NSE_EQ\|INE002A01018` | `RELIANCE` |
| `NSE:NIFTY50` | `NSE:NIFTY50-INDEX` | `NSE_INDEX\|Nifty 50` | `NIFTY 50` |
| `NSE:NIFTY24DEC19000CE` | `NSE:NIFTY24DEC19000CE` | `NSE_FO\|NIFTY24DEC19000CE` | `NIFTY24DEC19000CE` |

### 6.4 Rate Limit Distribution

#### Bulk Historical Download Strategy

```
Task: Download 180 stocks × 6 months × 1m data = 2,160 API calls

Distribution:
┌────────────────────────────────────────────────────┐
│  Broker    │  Rate Limit  │  Allocation  │  Time  │
├────────────┼──────────────┼──────────────┼────────┤
│  Upstox    │  2000/min    │  2,000 req   │  1 min │
│  Fyers     │  200/min     │  160 req     │  1 min │
│  Total     │              │  2,160 req   │  1 min │
└────────────────────────────────────────────────────┘

Result: Complete in ~1 minute (vs 11 minutes with single source)
```

---

## 7. Market Calendar System

### 7.1 Expiry Schedule (Current as of 2025)

| Index/Stock | Expiry Type | Day | Notes |
|-------------|-------------|-----|-------|
| **NIFTY** | Weekly + Monthly | Tuesday | Changed from Thursday |
| **BANKNIFTY** | Weekly + Monthly | Tuesday | Changed from Thursday |
| **MIDCAP NIFTY** | Weekly + Monthly | Tuesday | New weekly expiry |
| **FINNIFTY** | Monthly | Tuesday | Monthly only |
| **SENSEX** | Weekly + Monthly | Thursday | BSE index |
| **BANKEX** | Monthly | Thursday | BSE index |
| **Stock F&O** | Monthly | Last Thursday | All F&O stocks |

### 7.2 Holiday Adjustment Rules

```
IF scheduled_expiry IS IN holiday_calendar THEN
    actual_expiry = PREVIOUS_TRADING_DAY(scheduled_expiry)
    is_holiday_adjusted = TRUE
ELSE
    actual_expiry = scheduled_expiry
    is_holiday_adjusted = FALSE
END
```

### 7.3 Expiry Calendar Generation

#### Monthly Process
1. Calculate all expiries for next 3 months
2. Check holiday calendar
3. Adjust dates if needed
4. Store in `expiry_calendar` table
5. Alert on SEBI rule changes

#### Pre-Market Daily Check
1. Load today's expiries
2. Identify expiring contracts
3. Pre-calculate max pain, PCR
4. Prepare option subscription list

### 7.4 Market Hours

| Exchange | Regular Hours | Muhurat Trading |
|----------|---------------|-----------------|
| **NSE/BSE** | 09:15 - 15:30 | 18:15 - 19:15 (Diwali) |
| **Currency** | 09:00 - 17:00 | - |
| **Commodity** | 09:00 - 23:30 | - |

---

## 8. Risk Management

### 8.1 Risk Limits

#### Position Limits

| Limit Type | Value | Enforcement |
|------------|-------|-------------|
| Max Positions | 5 | Per strategy |
| Max Order Value | ₹2,00,000 | Per order |
| Max Position Value | ₹10,00,000 | Total across all |
| Max Quantity per Order | Based on lot size | Pre-trade check |

#### Loss Limits

| Limit Type | Value | Action |
|------------|-------|--------|
| Max Daily Loss | ₹10,000 | Halt all trading |
| Max Weekly Loss | ₹30,000 | Review + reduce size |
| Max Drawdown | 15% | Stop all algos |
| Consecutive Losses | 5 | Pause strategy |

### 8.2 Circuit Breakers

| Trigger | Action |
|---------|--------|
| Daily loss > ₹10,000 | Auto-halt trading, alert immediately |
| 3 consecutive losses | Reduce position size by 50% |
| 5 consecutive losses | Pause strategy, manual review required |
| Account margin < 20% | Stop new positions, alert |
| Broker disconnect > 1 min | Pause order placement, alert |
| Data feed lag > 30 sec | Pause trading, alert |

### 8.3 Kill Switch Levels

| Level | Trigger | Action |
|-------|---------|--------|
| **Strategy Kill** | Manual | Stop specific strategy, keep positions |
| **System Pause** | Manual | Stop all new orders, monitor existing |
| **Emergency Exit** | Manual/Auto | Market sell all positions immediately |
| **Full Shutdown** | Manual | Exit all, disconnect everything |

### 8.4 Order Validation

#### Pre-Trade Checks

```
Order Validation Pipeline:
1. Symbol Validation
   - Is instrument tradeable?
   - Is it F&O banned?
   
2. Quantity Validation
   - Within lot size multiple?
   - Below freeze quantity?
   
3. Price Validation
   - Within circuit limits?
   - Reasonable vs LTP?
   
4. Risk Validation
   - Within position limits?
   - Within daily loss limit?
   
5. Time Validation
   - Is market open?
   - Is it expiry day?
   
6. Strategy Validation
   - Is strategy active?
   - Is it within allocated capital?
```

---

## 9. Operational Workflows

### 9.1 Daily Startup Sequence

```
08:30 - SYSTEM STARTUP
├── 1. Load configuration
├── 2. Check if trading day (holiday calendar)
├── 3. Connect to databases
├── 4. Initialize Redis event bus
├── 5. Authenticate with brokers
├── 6. Load instrument master
├── 7. Calculate today's expiries
└── 8. Health check all services

08:45 - PRE-MARKET PREP
├── 1. Fetch previous day EOD data (if missing)
├── 2. Load yesterday's OI data for indices
├── 3. Calculate max pain, PCR
├── 4. Prepare subscription list
└── 5. Pre-warm indicator caches

09:00 - DATA FEED START
├── 1. Subscribe to instruments (WebSocket)
├── 2. Start batch polling (Upstox)
├── 3. Verify first tick received
└── 4. Start candle builders

09:15 - MARKET OPEN
├── 1. Strategies activated (after 09:20 for stability)
├── 2. Position manager active
└── 3. Full system operational
```

### 9.2 Market Hours Workflow

```
09:15 - 15:30: MARKET HOURS
│
├── Every Tick:
│   ├── Update candle builders
│   ├── Check position SL/Target
│   └── Publish to event bus
│
├── Every Minute:
│   ├── Complete 1m candle
│   ├── Compute indicators
│   ├── Run strategy scans
│   └── Store to database
│
├── Every 5 Minutes:
│   ├── Batch quote update (Upstox)
│   ├── Full universe scan
│   └── Position reconciliation
│
└── At 15:20:
    ├── Alert: MIS square-off window
    └── Prepare for market close
```

### 9.3 Post-Market Workflow

```
15:30 - MARKET CLOSE
├── 1. Verify all data feed stopped
├── 2. Final candle completion
└── 3. Position reconciliation

15:45 - EOD BATCH
├── 1. Download full option chain (all stocks)
├── 2. Download NSE Bhavcopy
├── 3. Compute EOD indicators
├── 4. Store option chain snapshots
└── 5. Update Greeks

16:30 - DAILY REPORT
├── 1. Generate P&L report
├── 2. Calculate strategy metrics
├── 3. Send daily summary (Telegram)
└── 4. Archive logs
```

### 9.4 Error Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| **Data feed disconnect** | No ticks for 30s | Auto-reconnect, fallback to batch API |
| **Broker disconnect** | Connection error | Retry with backoff, alert |
| **Database down** | Connection failure | Queue writes, alert immediately |
| **Strategy crash** | Process exit | Restart, resume from last state |
| **System restart** | On startup | Reconcile positions with broker |

### 9.5 Master Data Refresh Schedule

| Data Type | Frequency | Trigger | Source | Notes |
|-----------|-----------|---------|--------|-------|
| **F&O Ban List** | Daily | 08:30 pre-market | NSE website / Broker API | Check before any F&O order |
| **Holiday Calendar** | Annually + adhoc | Manual / NSE circular | NSE website | Update when NSE announces |
| **Expiry Calendar** | Monthly | 1st of month | Calculate + holiday adjust | Generate 3 months ahead |
| **Lot Size Changes** | Quarterly | NSE circular | NSE website | Usually effective from new expiry |
| **Index Constituents** | Monthly | Index rebalance | NSE website | NIFTY rebalances semi-annually |
| **Instrument Master** | Weekly | Sunday EOD | Broker symbol master | Add new listings, delist old |
| **Sector Mapping** | Quarterly | Manual review | NSE / BSE | Verify sector classifications |

#### Pre-Market Data Checks (08:30 Daily)

```
DAILY PRE-MARKET REFRESH
├── 1. Fetch today's F&O ban list
│   ├── Query NSE F&O ban page
│   ├── Update fo_ban_list table
│   └── Alert if any held positions are banned
│
├── 2. Verify holiday calendar
│   ├── Check if today is trading day
│   └── Check for partial trading hours
│
├── 3. Check expiring contracts
│   ├── Identify today's expiries
│   ├── Alert on positions in expiring contracts
│   └── Update instrument tradeable status
│
└── 4. Validate lot sizes
    ├── Check if lot size change effective today
    └── Update instrument_master if changed
```

#### Quarterly Lot Size Update Process

```
LOT SIZE UPDATE (When NSE Circular Released)
├── 1. Parse NSE circular for new lot sizes
├── 2. For each changed instrument:
│   ├── Insert new record in lot_size_history
│   ├── Set effective_to on previous record
│   └── Update instrument_master.lot_size
├── 3. Log to master_data_refresh_log
└── 4. Alert: "Lot sizes updated for X instruments"
```

#### Dynamic vs Static Data Strategy

| Data | Storage | Fetch Strategy |
|------|---------|----------------|
| **Lot sizes** | Static (DB) | Update quarterly, use `lot_size_history` for backtesting |
| **F&O ban list** | Static (DB) | Fetch daily pre-market, cache for day |
| **Index constituents** | Static (DB) | Update monthly, temporal validity for backtesting |
| **Margin requirements** | Dynamic | Fetch from broker before order (changes intraday) |
| **Circuit limits** | Dynamic | Fetch from broker before order |
| **Live option chain** | Dynamic | Fetch on-demand (not stored real-time) |

---

## 10. Deployment Architecture

### 10.1 Local Development (Current)

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: timescale/timescaledb:latest-pg14
    volumes:
      - postgres_data:/var/lib/postgresql/data
    
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
  
  backend:
    build: ./backend
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app
    env_file:
      - .env.local
  
  frontend:
    build: ./frontend
    depends_on:
      - backend
    volumes:
      - ./frontend:/app

volumes:
  postgres_data:
  redis_data:
```

### 10.2 Production VPS (Phase 2)

```
Single VPS (4 vCPU, 8GB RAM):
├── Docker Compose (same as local)
├── Nginx (reverse proxy)
├── Let's Encrypt (SSL)
└── Automated backups to S3
```

### 10.3 Kubernetes (Future)

```yaml
# Simplified K8s architecture
apiVersion: apps/v1
kind: Deployment
metadata:
  name: keepgaining-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: keepgaining-backend
  template:
    spec:
      containers:
      - name: backend
        image: keepgaining/backend:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
```

### 10.4 Cloud Migration Path

| Phase | Infrastructure | Cost/Month | Effort |
|-------|----------------|------------|--------|
| **Now** | Local machine | ₹0 | - |
| **Phase 2** | Single VPS (Hetzner) | ₹1,500 | 4 hours |
| **Phase 3** | Managed DB + VPS | ₹4,000 | 2 hours |
| **Phase 4** | Kubernetes cluster | ₹12,000 | 1 week |

---

## 11. Frontend Design

### 11.1 Design Philosophy

| Principle | Description |
|-----------|-------------|
| **Enterprise-Grade** | Professional UI suitable for serious trading |
| **Information Dense** | Maximum data visibility without clutter |
| **Real-Time First** | Live updates via WebSocket, no page refreshes |
| **Keyboard Shortcuts** | Power users can operate without mouse |
| **Dark Mode Default** | Reduces eye strain during market hours |
| **Responsive** | Works on desktop, tablet, and mobile |
| **Configurable** | Layouts, widgets, and defaults can be customized |

### 11.2 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Framework** | Next.js 14 (App Router) | SSR, API routes, modern React |
| **Language** | TypeScript | Type safety, better DX |
| **Styling** | Tailwind CSS + shadcn/ui | Rapid development, consistent design |
| **State Management** | Zustand + React Query | Simple global state + server state |
| **Real-Time** | Socket.io / WebSocket | Live data streaming |
| **Charts** | Lightweight Charts (TradingView) | Professional trading charts |
| **Tables** | TanStack Table | Powerful, sortable, filterable |
| **Forms** | React Hook Form + Zod | Validation, type-safe forms |
| **Icons** | Lucide React | Consistent, modern icons |
| **Notifications** | Sonner | Toast notifications |

### 11.3 Application Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              TOP NAVIGATION BAR                                 │
│  ┌────────┐  ┌────────────────────────────────────────┐  ┌──────┐  ┌────────┐ │
│  │  LOGO  │  │ Dashboard │ Strategies │ Positions │ ... │  │ P&L  │  │ ⚙️ 👤 │ │
│  └────────┘  └────────────────────────────────────────┘  └──────┘  └────────┘ │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                         MAIN CONTENT AREA                                 │  │
│  │                                                                           │  │
│  │  (Page-specific content - Dashboard, Strategies, etc.)                   │  │
│  │                                                                           │  │
│  │                                                                           │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                              STATUS BAR                                         │
│  🟢 System: Running │ 📊 Fyers: Connected │ 📈 Upstox: Connected │ 🕐 15:23:45  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 11.4 Page Designs

#### 11.4.1 Dashboard (Home)

**Purpose:** At-a-glance view of everything important

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  DASHBOARD                                                    [Today ▼] [↻]    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐│
│  │   TODAY'S P&L   │  │  OPEN POSITIONS │  │  ACTIVE ORDERS  │  │  WIN RATE  ││
│  │    +₹4,250      │  │       3         │  │       1         │  │    67%     ││
│  │    ▲ 2.1%       │  │   ₹45,000 exp   │  │   ₹12,000 val   │  │   8/12     ││
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └────────────┘│
│                                                                                 │
│  ┌──────────────────────────────────────┐  ┌────────────────────────────────┐  │
│  │         P&L CURVE (Today)            │  │      STRATEGY PERFORMANCE      │  │
│  │                                      │  │                                │  │
│  │         📈 Chart                     │  │  EMA Crossover    +₹2,100  ▲  │  │
│  │                                      │  │  VWMA Strategy    +₹1,800  ▲  │  │
│  │                                      │  │  Gamma Blast       +₹350   ▲  │  │
│  └──────────────────────────────────────┘  └────────────────────────────────┘  │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        OPEN POSITIONS                                     │  │
│  ├──────────────────────────────────────────────────────────────────────────┤  │
│  │  Symbol          │ Qty │ Avg Price │ LTP    │ P&L     │ SL    │ Target  │  │
│  │  NIFTY 24000CE   │ 50  │ 125.50    │ 142.30 │ +₹840   │ 110   │ 160     │  │
│  │  RELIANCE 2500CE │ 250 │ 45.20     │ 48.50  │ +₹825   │ 40    │ 55      │  │
│  │  BANKNIFTY PE    │ 15  │ 180.00    │ 165.00 │ -₹225   │ 200   │ 140     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌────────────────────────────────┐  ┌────────────────────────────────────────┐│
│  │      RECENT TRADES (Today)     │  │           SYSTEM ALERTS               ││
│  ├────────────────────────────────┤  ├────────────────────────────────────────┤│
│  │ 14:32 SELL NIFTY CE   +₹1,200 │  │ ⚠️ 15:20 - MIS square-off in 10 mins  ││
│  │ 13:15 BUY  RELIANCE CE  Entry │  │ ✅ 09:15 - All strategies activated    ││
│  │ 11:45 SELL HDFC PE    +₹850   │  │ 📊 09:00 - Data feed connected         ││
│  └────────────────────────────────┘  └────────────────────────────────────────┘│
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 11.4.2 Strategy Builder / Manager

**Purpose:** Create, edit, and manage trading strategies visually

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  STRATEGIES                                            [+ New Strategy] [📥]   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  STRATEGY LIST                                                          │   │
│  ├────────────────────────────────────────────────────────────────────────┤   │
│  │  Name              │ Status  │ Today P&L │ Win Rate │ Trades │ Actions │   │
│  │  ───────────────────────────────────────────────────────────────────── │   │
│  │  EMA Crossover v2  │ 🟢 LIVE │ +₹2,100   │ 72%      │ 5      │ ✏️ ⏸️ 📊 │   │
│  │  VWMA 22/31 Trend  │ 🟢 LIVE │ +₹1,800   │ 65%      │ 3      │ ✏️ ⏸️ 📊 │   │
│  │  Gamma Blast       │ 🟡 PAPER│ +₹350     │ 58%      │ 8      │ ✏️ ▶️ 📊 │   │
│  │  RSI Divergence    │ ⚪ DRAFT│ -         │ -        │ -      │ ✏️ 🗑️    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

STRATEGY BUILDER (Modal/Page):
┌─────────────────────────────────────────────────────────────────────────────────┐
│  EDIT STRATEGY: EMA Crossover v2                              [Save] [Cancel]  │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────────────────────────────────────────────────┐ │
│  │   BASICS    │  │                                                          │ │
│  │   ─────     │  │  Strategy Name: [EMA Crossover v2                    ]  │ │
│  │ ▶ Entry     │  │  Description:   [Trend following with EMA crossover  ]  │ │
│  │   Exit      │  │  Version:       [2.0                                  ]  │ │
│  │   Position  │  │  Status:        [LIVE ▼]                                │ │
│  │   Filters   │  │                                                          │ │
│  │   Risk      │  └──────────────────────────────────────────────────────────┘ │
│  │   Backtest  │                                                               │
│  └─────────────┘                                                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ENTRY CONDITIONS                                           [+ Add Condition]  │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  IF ALL of these conditions are met:                                     │  │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │  │ 1. [EMA 21 ▼] [crosses above ▼] [EMA 50 ▼] on [5m ▼]   [🗑️]      │ │  │
│  │  └────────────────────────────────────────────────────────────────────┘ │  │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │  │ 2. [RSI 14 ▼] [is greater than ▼] [50        ] on [5m ▼]   [🗑️]  │ │  │
│  │  └────────────────────────────────────────────────────────────────────┘ │  │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │  │ 3. [Supertrend ▼] [equals ▼] [Bullish ▼] on [15m ▼]   [🗑️]       │ │  │
│  │  └────────────────────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  EXIT CONDITIONS                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  Stop Loss:    [ATR Based ▼]  Value: [1.5    ] ATR                      │  │
│  │  Target:       [R:R Ratio ▼]  Value: [2.0    ] x Risk                   │  │
│  │  Trailing SL:  [✓] Enabled   Trigger: [1.0 R ] Step: [0.5 ATR]         │  │
│  │  Time Exit:    [✓] Square off at [15:15]                                │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 11.4.3 Positions & Orders

**Purpose:** Real-time position monitoring and order management

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  POSITIONS & ORDERS                    [Open Positions] [Pending Orders] [All] │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  OPEN POSITIONS (3)                                    Total P&L: +₹1,440│  │
│  ├──────────────────────────────────────────────────────────────────────────┤  │
│  │  │ Symbol         │Strategy    │ Side│ Qty│ Entry │ LTP   │ P&L    │ Act│  │
│  │  ├────────────────┼────────────┼─────┼────┼───────┼───────┼────────┼────┤  │
│  │  │ NIFTY 24000CE  │EMA Cross   │ BUY │ 50 │125.50 │142.30 │+₹840 ▲│ ✕ │  │
│  │  │ RELIANCE 2500CE│VWMA Trend  │ BUY │250 │ 45.20 │ 48.50 │+₹825 ▲│ ✕ │  │
│  │  │ BANKNIFTY 52PE │Gamma Blast │ BUY │ 15 │180.00 │165.00 │-₹225 ▼│ ✕ │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  Position Detail (Click to expand):                                             │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  NIFTY 24000CE                                              [Modify SL]  │  │
│  │  ─────────────────────────────────────────────────────────────────────── │  │
│  │  Entry: 125.50 @ 11:32:15    │  SL: 110.00 (12.4% risk)                  │  │
│  │  Current: 142.30 (+13.4%)    │  Target: 160.00 (27.5% from entry)        │  │
│  │  High since entry: 145.20    │  Trailing SL: Active (moved to 118.00)   │  │
│  │  Strategy: EMA Crossover v2  │  Product: MIS                             │  │
│  │  ──────────────────────────────────────────────────────────────────────  │  │
│  │  [Close @ Market] [Close @ Limit: ______] [Modify SL/Target]            │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  PENDING ORDERS (1)                                                      │  │
│  ├──────────────────────────────────────────────────────────────────────────┤  │
│  │  │ Symbol       │ Type    │ Side │ Qty │ Price  │ Status  │ Actions     │  │
│  │  │ INFY 1900CE  │ LIMIT   │ BUY  │ 400 │  32.50 │ PENDING │ ✏️ ✕        │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 11.4.4 Market Scanner

**Purpose:** Scan 180+ F&O stocks for opportunities

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  MARKET SCANNER                               [Custom Scan ▼] [Run Scan] [⚙️]  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  Quick Filters: [All F&O ▼] [NIFTY 50] [BANK NIFTY] [High Volume] [Trending]  │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  SCAN RESULTS (23 matches)                          Last scan: 10:32:15  │  │
│  ├──────────────────────────────────────────────────────────────────────────┤  │
│  │  Symbol    │ LTP    │ Chg%   │ Vol    │ Signal     │ Strength │ Action  │  │
│  │  ──────────┼────────┼────────┼────────┼────────────┼──────────┼──────── │  │
│  │  RELIANCE  │2,458.50│ +2.3%  │ 12.5M  │ EMA Cross ▲│ ████████░│ [Trade] │  │
│  │  HDFC      │1,678.20│ +1.8%  │ 8.2M   │ VWMA Bull ▲│ ███████░░│ [Trade] │  │
│  │  INFY      │1,542.30│ +1.5%  │ 6.1M   │ RSI Bounce │ ██████░░░│ [Trade] │  │
│  │  TCS       │3,890.00│ +1.2%  │ 4.8M   │ Supertrend │ █████░░░░│ [Trade] │  │
│  │  ICICI     │  985.40│ +0.9%  │ 15.2M  │ EMA Cross ▲│ ████░░░░░│ [Trade] │  │
│  │  ...                                                                     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌────────────────────────────────────────┐  ┌────────────────────────────────┐│
│  │  MARKET BREADTH                        │  │  SECTOR HEATMAP                ││
│  │  Advances: 124  Declines: 56           │  │  ┌────┬────┬────┬────┐        ││
│  │  [████████████████░░░░░░░░]            │  │  │ IT │BANK│AUTO│PHAR│        ││
│  │  A/D Ratio: 2.21                       │  │  │+2.1│+1.5│+0.8│-0.3│        ││
│  └────────────────────────────────────────┘  │  └────┴────┴────┴────┘        ││
│                                              └────────────────────────────────┘│
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 11.4.5 Analytics & Reports

**Purpose:** Historical performance analysis

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ANALYTICS                              [This Week ▼] [Export CSV] [Export PDF]│
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐│
│  │  TOTAL P&L      │  │    WIN RATE     │  │  PROFIT FACTOR  │  │  SHARPE    ││
│  │   +₹24,500      │  │      67%        │  │      2.4        │  │    1.8     ││
│  │   ▲ from ₹2L    │  │    34/51        │  │                 │  │            ││
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └────────────┘│
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                         EQUITY CURVE                                      │  │
│  │                                                                           │  │
│  │  ₹2.5L ─                                                    ╱────        │  │
│  │         │                                              ╱────            │  │
│  │  ₹2.2L ─│                              ╱──────────────                   │  │
│  │         │                    ╱────────                                   │  │
│  │  ₹2.0L ─│────────────────────                                            │  │
│  │         ├────┬────┬────┬────┬────┬────┬────┬────┬────┬────              │  │
│  │         Mon  Tue  Wed  Thu  Fri  Mon  Tue  Wed  Thu  Fri                 │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌─────────────────────────────────┐  ┌────────────────────────────────────┐  │
│  │  BY STRATEGY                    │  │  BY INSTRUMENT                      │  │
│  │  EMA Crossover    +₹12,500 52%  │  │  NIFTY Options   +₹15,000  61%     │  │
│  │  VWMA Trend       +₹8,200  28%  │  │  BANKNIFTY Opts  +₹6,500   27%     │  │
│  │  Gamma Blast      +₹3,800  16%  │  │  Stock Options   +₹3,000   12%     │  │
│  └─────────────────────────────────┘  └────────────────────────────────────┘  │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  TRADE LOG                                                    [Filter ▼] │  │
│  ├──────────────────────────────────────────────────────────────────────────┤  │
│  │  Date     │ Symbol       │ Strategy   │ Entry │ Exit  │ P&L    │ R:R    │  │
│  │  Nov 28   │ NIFTY 24CE   │ EMA Cross  │125.50 │142.30 │+₹840   │ 1.8R   │  │
│  │  Nov 28   │ RELIANCE CE  │ VWMA Trend │ 45.20 │ 52.80 │+₹1,900 │ 2.1R   │  │
│  │  Nov 27   │ HDFC PE      │ Gamma Blast│ 85.00 │ 72.00 │-₹650   │ -1.0R  │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 11.4.6 Settings & Configuration

**Purpose:** System configuration and overrides

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  SETTINGS                                                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────────────────────────────────────────┐  │
│  │   CATEGORIES    │  │                                                     │  │
│  │   ────────────  │  │  RISK MANAGEMENT                                    │  │
│  │ ▶ Risk Mgmt     │  │  ─────────────────                                  │  │
│  │   Brokers       │  │                                                     │  │
│  │   Trading       │  │  Position Limits                                    │  │
│  │   Alerts        │  │  ┌─────────────────────────────────────────────┐   │  │
│  │   UI Prefs      │  │  │ Max Positions:        [5         ]          │   │  │
│  │   Data          │  │  │ Max Order Value:      [₹2,00,000 ]          │   │  │
│  │   System        │  │  │ Max Position Value:   [₹10,00,000]          │   │  │
│  │                 │  │  └─────────────────────────────────────────────┘   │  │
│  │                 │  │                                                     │  │
│  │                 │  │  Loss Limits                                        │  │
│  │                 │  │  ┌─────────────────────────────────────────────┐   │  │
│  │                 │  │  │ Max Daily Loss:       [₹10,000  ]           │   │  │
│  │                 │  │  │ Max Weekly Loss:      [₹30,000  ]           │   │  │
│  │                 │  │  │ Max Drawdown %:       [15       ] %         │   │  │
│  │                 │  │  │ Consecutive Loss Limit:[5       ]           │   │  │
│  │                 │  │  └─────────────────────────────────────────────┘   │  │
│  │                 │  │                                                     │  │
│  │                 │  │  Circuit Breakers                                   │  │
│  │                 │  │  ┌─────────────────────────────────────────────┐   │  │
│  │                 │  │  │ [✓] Auto-halt on daily loss limit           │   │  │
│  │                 │  │  │ [✓] Reduce size after 3 consecutive losses  │   │  │
│  │                 │  │  │ [✓] Pause on broker disconnect > 1 min      │   │  │
│  │                 │  │  │ [✓] Alert on data feed lag > 30 sec         │   │  │
│  │                 │  │  └─────────────────────────────────────────────┘   │  │
│  │                 │  │                                                     │  │
│  │                 │  │  [Reset to Defaults]                    [Save]     │  │
│  └─────────────────┘  └─────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 11.5 UI Components Library

#### 11.5.1 Core Components

| Component | Description | Usage |
|-----------|-------------|-------|
| **StatCard** | Metric display with label, value, change | Dashboard KPIs |
| **DataTable** | Sortable, filterable table | Positions, Trades, Scans |
| **PriceDisplay** | Real-time price with color coding | LTP, P&L |
| **StatusBadge** | Colored status indicator | Strategy status, Order status |
| **SparkChart** | Mini inline chart | Intraday trend |
| **ProgressRing** | Circular progress | Win rate, usage limits |
| **AlertToast** | Notification popup | Trade alerts, errors |

#### 11.5.2 Trading Components

| Component | Description |
|-----------|-------------|
| **TradingChart** | Full TradingView-style chart with indicators |
| **OrderPanel** | Quick order entry form |
| **PositionCard** | Position details with actions |
| **OptionChain** | Interactive option chain display |
| **StrategyBuilder** | Visual rule builder for strategies |
| **RiskGauge** | Visual risk level indicator |

### 11.6 Real-Time Features

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         REAL-TIME DATA FLOW                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  Backend                    WebSocket                      Frontend             │
│  ────────                   ─────────                      ────────             │
│                                                                                 │
│  Redis Streams ──────────►  Socket.io  ──────────────►  React State            │
│      │                         │                             │                  │
│      │                         │                             ▼                  │
│      │  Events:                │  Channels:              Components:            │
│      │  • TICK                 │  • ticks:{symbol}       • PriceDisplay         │
│      │  • CANDLE               │  • positions            • TradingChart         │
│      │  • SIGNAL               │  • orders               • PositionCard         │
│      │  • ORDER_UPDATE         │  • signals              • AlertToast           │
│      │  • POSITION_UPDATE      │  • alerts               • Dashboard KPIs       │
│      │  • ALERT                │  • system               • StatusBar            │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 11.7 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + D` | Go to Dashboard |
| `Ctrl + S` | Go to Strategies |
| `Ctrl + P` | Go to Positions |
| `Ctrl + M` | Go to Market Scanner |
| `Ctrl + K` | Open Command Palette |
| `Esc` | Close modal / Clear selection |
| `Space` | Toggle selected strategy |
| `E` | Edit selected item |
| `Delete` | Cancel selected order |
| `Ctrl + Shift + K` | Emergency Kill Switch |

### 11.8 Mobile Responsive Design

```
MOBILE VIEW (< 768px):
┌─────────────────────┐
│  ☰  KeepGaining  ⚙️ │
├─────────────────────┤
│  TODAY'S P&L        │
│     +₹4,250         │
│  ┌───┐ ┌───┐ ┌───┐  │
│  │ 3 │ │ 1 │ │67%│  │
│  │Pos│ │Ord│ │Win│  │
│  └───┘ └───┘ └───┘  │
├─────────────────────┤
│  POSITIONS          │
│  ┌─────────────────┐│
│  │NIFTY 24000CE    ││
│  │+₹840  ▲ 13.4%  ││
│  │SL: 110 | T: 160 ││
│  └─────────────────┘│
│  ┌─────────────────┐│
│  │RELIANCE 2500CE  ││
│  │+₹825  ▲ 7.3%   ││
│  └─────────────────┘│
├─────────────────────┤
│ [Dashboard][Pos][⋮] │
└─────────────────────┘
```

---

## 12. Implementation Phases

### Phase 1: Foundation (Months 1-2) - CURRENT FOCUS

**Goal:** Options buying intraday with 180 F&O stocks

#### Week 1-2: Core Infrastructure
- [x] Event bus (Redis Streams)
- [x] Database schema (PostgreSQL + TimescaleDB)
- [x] Master data (instruments, sectors)
- [x] Symbol mapping system
- [ ] Calendar system (expiry, holidays)

#### Week 3-4: Data Pipeline
- [ ] Upstox batch quote integration
- [ ] Fyers WebSocket integration
- [ ] Candle builder (1m base)
- [ ] Multi-timeframe aggregation
- [ ] Historical data download

#### Week 5-6: Trading Core
- [ ] Strategy engine framework
- [ ] Simple EMA crossover strategy
- [ ] OMS with risk checks
- [ ] Broker gateway (Fyers)
- [ ] Position manager (basic)

#### Week 7-8: Production Ready
- [ ] Telegram alerts
- [ ] EOD data download
- [ ] Daily reconciliation
- [ ] Kill switch
- [ ] Basic monitoring

**Deliverables:**
- ✅ Live intraday options trading
- ✅ 180 F&O stock scanning
- ✅ Basic risk management
- ✅ EOD reporting

---

### Phase 2: Enhancement (Months 3-4)

**Goal:** Advanced position management and multiple strategies

#### Features
- [ ] Trailing stop loss (automated)
- [ ] Multiple strategy support
- [ ] Paper trading mode
- [ ] Advanced backtesting
- [ ] Option Greeks computation
- [ ] Gamma blast detection
- [ ] Performance analytics

**Deliverables:**
- ✅ 3-5 working strategies
- ✅ Automated SL/Target management
- ✅ Historical performance tracking

---

### Phase 3: Scale (Months 5-6)

**Goal:** Futures, swing trading, multi-timeframe

#### Features
- [ ] Futures trading support
- [ ] Swing/positional strategies
- [ ] Multi-day position tracking
- [ ] Portfolio-level risk
- [ ] Advanced analytics dashboard
- [ ] Strategy optimization tools

**Deliverables:**
- ✅ Support all asset types
- ✅ Intraday to positional
- ✅ Portfolio-level management

---

### Phase 4: Production Hardening (Months 7-9)

**Goal:** Enterprise-grade reliability

#### Features
- [ ] Comprehensive testing (80% coverage)
- [ ] Disaster recovery
- [ ] Multi-region backup
- [ ] Advanced monitoring
- [ ] Performance optimization
- [ ] Cloud deployment (K8s)

**Deliverables:**
- ✅ 99.9% uptime
- ✅ Full disaster recovery
- ✅ Production-ready cloud deployment

---

## 13. Technology Stack

### 13.1 Backend

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| **Runtime** | Python | 3.12+ | Core language |
| **API Framework** | FastAPI | 0.104+ | REST API |
| **Async Runtime** | asyncio | Built-in | Concurrency |
| **Database** | PostgreSQL | 15+ | Primary storage |
| **Time-Series** | TimescaleDB | 2.13+ | Extension for PostgreSQL |
| **Cache/Event Bus** | Redis | 7+ | Caching + Streams |
| **WebSocket** | fyers-apiv3, websockets | Latest | Real-time data |
| **Data Processing** | Pandas, NumPy | Latest | Indicators, analysis |
| **Logging** | Loguru | 0.7+ | Structured logging |

### 13.2 Frontend (Optional)

| Component | Technology | Version |
|-----------|------------|---------|
| **Framework** | Next.js | 14+ |
| **Language** | TypeScript | 5+ |
| **UI Library** | React | 18+ |
| **Styling** | Tailwind CSS | 3+ |
| **Charts** | Recharts | 2+ |
| **State** | React Context | Built-in |

### 13.3 Infrastructure

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Containerization** | Docker | Packaging |
| **Orchestration** | Docker Compose (now), K8s (future) | Deployment |
| **Reverse Proxy** | Nginx | Production routing |
| **SSL** | Let's Encrypt | Security |
| **Monitoring** | Prometheus + Grafana (future) | Metrics |
| **Alerting** | Telegram Bot | Notifications |

### 13.4 Development Tools

| Tool | Purpose |
|------|---------|
| **Poetry** | Python dependency management |
| **Black** | Code formatting |
| **isort** | Import sorting |
| **pytest** | Testing framework |
| **VSCode** | IDE |

---

## 14. Non-Functional Requirements

### 14.1 Performance

| Metric | Target | Method |
|--------|--------|--------|
| **Tick Processing** | <100ms | Event-driven architecture |
| **Signal Generation** | <500ms | Pre-computed indicators |
| **Order Placement** | <2s | Direct broker API |
| **EOD Batch** | <10 min | Parallel processing |
| **Backtest (1 year)** | <5 min | Vectorized operations |

### 14.2 Reliability

| Aspect | Target | Implementation |
|--------|--------|----------------|
| **Uptime (market hours)** | >99% | Auto-reconnect, fallback sources |
| **Data Loss** | Zero | Redis persistence, DB transactions |
| **Order Loss** | Zero | Order log, reconciliation |
| **Broker Disconnect** | <30s recovery | Exponential backoff reconnect |

### 14.3 Scalability

| Dimension | Current | Scale Target |
|-----------|---------|--------------|
| **Instruments** | 500 | 5,000 |
| **Strategies** | 5 | 50 |
| **Orders/Day** | 100 | 10,000 |
| **Data Storage** | 50 GB/year | 500 GB/year |

### 14.4 Security

| Aspect | Implementation |
|--------|----------------|
| **API Keys** | Environment variables, Secrets Manager (future) |
| **Database** | Password auth, connection encryption |
| **API Endpoints** | API key auth (optional for personal use) |
| **Broker Credentials** | Encrypted at rest |
| **Audit Trail** | All trades logged (7-year retention) |

### 14.5 Maintainability

| Aspect | Standard |
|--------|----------|
| **Code Coverage** | >70% for critical paths |
| **Documentation** | All public interfaces documented |
| **Logging** | Structured JSON logs |
| **Monitoring** | Health endpoints, metrics |

## 16. MCP Automation Extension

### 16.1 Browser Automation Core
System utilizes Playwright and DevTools connected via MCP protocols to run headless browsers.

#### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    MCP AUTOMATION EXTENSION                  │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────┐    ┌────────────┐    ┌────────────┐          │
│  │ Broker     │───▶│ Screener   │───▶│ Sentiment  │          │
│  │ Login Auth │    │ Evaluator  │    │ NLP Agg    │          │
│  └────────────┘    └────────────┘    └────────────┘          │
│        │                 │                 │                 │
│        ▼                 ▼                 ▼                 │
│  • Headless TOTP   • Chartink HTML   • Trendlyne NLP         │
│  • Persisted Auth  • Web Scrape      • DOM Extract           │
└──────────────────────────────────────────────────────────────┘
```

#### Event Handling & Capabilities
- **DevTools Protocol**: Directly maps component IDs on complex websites for automated navigation.
- **Playwright Profiles**: Runs cached sessions mimicking human latency/timing intervals.
- **Auto-Login**: Automated retrieval of OAuth tokens behind multi-factor authentication, solving daily connection resets without user intervention.

---

## 17. Appendices

### Appendix A: Event Schema Reference

#### TICK Event
```json
{
  "event_type": "TICK",
  "timestamp": "2025-11-28T10:30:00.123+05:30",
  "data": {
    "instrument_id": "uuid",
    "symbol": "NSE:RELIANCE",
    "ltp": 2450.50,
    "bid": 2450.25,
    "ask": 2450.75,
    "volume": 1234567,
    "oi": 987654,
    "source": "fyers_websocket"
  }
}
```

#### CANDLE Event
```json
{
  "event_type": "CANDLE",
  "data": {
    "instrument_id": "uuid",
    "timeframe": "1m",
    "open": 2450.00,
    "high": 2455.00,
    "low": 2449.00,
    "close": 2452.00,
    "volume": 12345,
    "oi": 987654,
    "timestamp": "2025-11-28T10:30:00+05:30"
  }
}
```

#### SIGNAL Event
```json
{
  "event_type": "SIGNAL",
  "data": {
    "strategy_id": "ema_crossover",
    "symbol": "NSE:RELIANCE24DEC2500CE",
    "direction": "BUY",
    "strength": 0.85,
    "sl_price": 45.50,
    "target_price": 55.00,
    "metadata": {
      "setup": "ema_crossover",
      "timeframe": "5m"
    },
    "timestamp": "2025-11-28T10:30:00+05:30"
  }
}
```

### Appendix B: Configuration Examples

#### broker_config.yaml
```yaml
brokers:
  fyers:
    enabled: true
    priority: 1
    use_for_live_feed: true
    use_for_historical: true
    use_for_trading: true
    
  upstox:
    enabled: true
    priority: 2
    use_for_live_feed: false
    use_for_historical: true
    use_for_trading: false
```

#### risk_limits.yaml
```yaml
risk:
  position_limits:
    max_positions: 5
    max_order_value: 200000
    max_position_value: 1000000
  
  loss_limits:
    max_daily_loss: 10000
    max_weekly_loss: 30000
    max_drawdown_percent: 15
    consecutive_loss_limit: 5
  
  circuit_breakers:
    - trigger: daily_loss
      threshold: 10000
      action: halt_trading
    - trigger: consecutive_losses
      threshold: 3
      action: reduce_size_50_percent
```

### Appendix C: Glossary

| Term | Definition |
|------|------------|
| **ATM** | At The Money - option strike nearest to spot price |
| **CE** | Call Option |
| **F&O** | Futures & Options |
| **OI** | Open Interest |
| **IV** | Implied Volatility |
| **PCR** | Put-Call Ratio |
| **Max Pain** | Strike price where option writers lose least |
| **VWAP** | Volume Weighted Average Price |
| **SL** | Stop Loss |
| **MIS** | Margin Intraday Square-off |
| **NRML** | Normal (overnight positions) |

### Appendix D: Contact & Escalation

| Issue Type | Contact | Response Time |
|------------|---------|---------------|
| **System Down** | Telegram Alert | Immediate |
| **Data Feed Issue** | Automatic fallback | <30 seconds |
| **Order Failure** | Telegram Alert | Immediate |
| **Daily Loss Limit** | Telegram Alert | Immediate |

### Appendix E: File Structure

```
keepgaining/
├── docker-compose.yml
├── docker-compose.prod.yml
├── Dockerfile.backend
├── README.md
├── HIGH_LEVEL_DESIGN.md
├── docs/
│   ├── HIGH_LEVEL_DESIGN.md (this document)
│   ├── API.md
│   └── DEPLOYMENT.md
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── event_bus.py
│   │   │   └── logging.py
│   │   ├── adapters/
│   │   │   ├── base_data_source.py
│   │   │   ├── fyers_websocket.py
│   │   │   ├── upstox_batch.py
│   │   │   └── file_replay.py
│   │   ├── brokers/
│   │   │   ├── base.py
│   │   │   ├── fyers.py
│   │   │   ├── fyers_client.py
│   │   │   └── paper.py
│   │   ├── services/
│   │   │   ├── data_feed.py
│   │   │   ├── candle_builder.py
│   │   │   ├── indicator_engine.py
│   │   │   ├── storage.py
│   │   │   └── calendar.py
│   │   ├── strategies/
│   │   │   ├── base.py
│   │   │   ├── engine.py
│   │   │   └── implementations/
│   │   │       └── ema_option_buyer.py
│   │   ├── execution/
│   │   │   ├── oms.py
│   │   │   ├── risk.py
│   │   │   └── position_manager.py
│   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── session.py
│   │   │   └── migrations/
│   │   ├── api/
│   │   │   └── routes/
│   │   ├── schemas/
│   │   └── utils/
│   ├── tests/
│   └── scripts/
├── frontend/
│   ├── package.json
│   ├── next.config.mjs
│   ├── app/
│   ├── components/
│   └── lib/
└── config/
    ├── base.yaml
    ├── local.yaml
    └── production.yaml
```

### Appendix F: Technology Choices Rationale

| Choice | Alternatives Considered | Reason |
|--------|-------------------------|--------|
| **Python** | Go, Rust, Java | Rapid development, library ecosystem, ML/data science support |
| **FastAPI** | Flask, Django | Async support, auto-docs, high performance |
| **PostgreSQL** | MySQL, MongoDB | Reliability, JSON support, TimescaleDB upgrade path |
| **Redis Streams** | RabbitMQ, Kafka | Simplicity, already using Redis, sufficient scale for personal use |
| **Docker** | VMs, bare metal | Consistency, easy deployment, cloud portability |
| **TimescaleDB** | InfluxDB, QuestDB | PostgreSQL extension (no new DB), excellent time-series performance |
| **scikit-learn/XGBoost** | TensorFlow, PyTorch | Simpler for tabular financial data, interpretable models |
| **cvxpy** | scipy.optimize | Convex optimization, portfolio-specific constraints |

---

## 15. Advanced Analytics

### 15.1 ML Signal Enhancement

Machine learning powered signal enhancement for improved trade predictions.

#### Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ML SIGNAL ENHANCEMENT                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                   │
│  │   Feature   │───▶│   Model     │───▶│   Signal    │                   │
│  │ Extraction  │    │  Ensemble   │    │ Enhancement │                   │
│  └─────────────┘    └─────────────┘    └─────────────┘                   │
│        │                  │                  │                           │
│        ▼                  ▼                  ▼                           │
│  • Price features    • RandomForest    • Probability scores              │
│  • Volume features   • XGBoost         • Confidence levels               │
│  • Technical ind.    • Ensemble avg    • Enhanced signals                │
│  • Momentum          • Cross-val       • Model version                   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

#### Features Extracted

| Category | Features |
|----------|----------|
| **Price** | Returns (1d-20d), price vs SMA (5,10,20,50), high/low ratios |
| **Volume** | Volume ratios, volume SMA ratio, volume change |
| **Technical** | RSI, MACD signal, Bollinger position, ATR normalized |
| **Momentum** | ROC periods, momentum indicators |

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/advanced-analytics/ml/enhance-signal` | POST | Enhance trading signal with ML |
| `/advanced-analytics/ml/train` | POST | Train new model for symbol |
| `/advanced-analytics/ml/models` | GET | List all trained models |
| `/advanced-analytics/ml/predict/{symbol}` | GET | Get prediction for symbol |

### 15.2 Sentiment Analysis

Multi-source sentiment aggregation for market mood analysis.

#### Data Sources

| Source | Data Type | Update Frequency |
|--------|-----------|------------------|
| **News API** | Financial news headlines | Real-time |
| **Twitter** | Social mentions, trending | Real-time |
| **Reddit** | r/IndianStreetBets, r/IndiaInvestments | 15-min |
| **FinBERT** | NLP sentiment classification | On-demand |

#### Sentiment Scoring

```
Overall Sentiment = w1*News + w2*Social + w3*Technical

Where:
- News weight (w1) = 0.4
- Social weight (w2) = 0.3  
- Technical weight (w3) = 0.3

Sentiment Labels:
- very_bearish: < 0.2
- bearish: 0.2 - 0.4
- neutral: 0.4 - 0.6
- bullish: 0.6 - 0.8
- very_bullish: > 0.8
```

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/advanced-analytics/sentiment/{symbol}` | GET | Get aggregated sentiment |
| `/advanced-analytics/sentiment/{symbol}/sources` | GET | Get per-source sentiment |
| `/advanced-analytics/sentiment/{symbol}/trend` | GET | Get sentiment trend |

### 15.3 Portfolio Optimization

Modern portfolio theory implementations for optimal allocation.

#### Optimization Methods

| Method | Description | Use Case |
|--------|-------------|----------|
| **Mean-Variance (Markowitz)** | Classic efficient frontier | Target return with min volatility |
| **Risk Parity** | Equal risk contribution | Balanced risk allocation |
| **Maximum Sharpe** | Optimal risk-adjusted return | Best Sharpe ratio portfolio |
| **Minimum Volatility** | Lowest possible volatility | Conservative portfolios |
| **Black-Litterman** | Combines views with market equilibrium | Incorporating opinions |

#### Risk Metrics Calculated

| Metric | Description |
|--------|-------------|
| **VaR (95%, 99%)** | Value at Risk at confidence levels |
| **CVaR / Expected Shortfall** | Average loss beyond VaR |
| **Portfolio Beta** | Sensitivity to market |
| **Correlation Matrix** | Asset correlations |
| **Sector Exposure** | Concentration by sector |
| **Diversification Ratio** | Weighted avg vol / portfolio vol |

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/advanced-analytics/portfolio/optimize` | POST | Run portfolio optimization |
| `/advanced-analytics/portfolio/risk-metrics` | POST | Calculate risk metrics |
| `/advanced-analytics/portfolio/efficient-frontier` | POST | Generate efficient frontier |

### 15.4 Multi-Broker Support

Unified order management across multiple brokers.

#### Supported Brokers

| Broker | Status | Capabilities |
|--------|--------|--------------|
| **Fyers** | ✅ Production | Orders, Positions, Streaming, Historical |
| **Upstox** | ✅ Production | Orders, Positions, Streaming, Historical |
| **Zerodha** | ✅ Implemented | Orders, Positions, Streaming, Historical |
| **Angel One** | ✅ Implemented | Orders, Positions, GTT Orders, Margins |

#### Unified Order Manager

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      UNIFIED ORDER MANAGER                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌─────────────────────┐    ┌─────────────────────┐  │
│  │   Order     │───▶│    Broker Router    │───▶│   Broker Adapter    │  │
│  │  Request    │    │  (Smart Routing)    │    │  (Fyers/Upstox/...) │  │
│  └─────────────┘    └─────────────────────┘    └─────────────────────┘  │
│                              │                           │               │
│                              ▼                           ▼               │
│                     ┌─────────────────┐        ┌─────────────────┐      │
│                     │ Position Agg.   │        │  Order Tracker  │      │
│                     │ (Unified View)  │        │  (All Brokers)  │      │
│                     └─────────────────┘        └─────────────────┘      │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

#### Features

- **Smart Order Routing**: Route orders to broker with best margin/liquidity
- **Position Aggregation**: Unified view across all brokers
- **Order Tracking**: Central tracking of all broker orders
- **Position Reconciliation**: Auto-reconcile positions with brokers
- **Portfolio Summary**: Combined portfolio metrics

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/multi-broker/brokers/status` | GET | Get all broker statuses |
| `/multi-broker/brokers/connect` | POST | Connect to a broker |
| `/multi-broker/positions` | GET | Get unified positions |
| `/multi-broker/orders` | GET | Get all orders |
| `/multi-broker/orders/place` | POST | Place order via unified manager |
| `/multi-broker/portfolio/summary` | GET | Get portfolio summary |
| `/multi-broker/positions/reconcile` | POST | Reconcile positions |

### 15.5 Frontend Components

New UI components for advanced analytics:

| Component | Location | Description |
|-----------|----------|-------------|
| `MLDashboard` | `/advanced-analytics` | ML signal prediction and model management |
| `SentimentPanel` | `/advanced-analytics` | Multi-source sentiment display |
| `PortfolioOptimizer` | `/advanced-analytics` | Portfolio allocation optimization |
| `MultiBrokerManager` | `/advanced-analytics` | Unified broker management UI |

---

### Appendix G: Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-11-28 | Redis Streams over Kafka | Simpler, sufficient for personal use, already have Redis |
| 2025-11-28 | Upstox for historical data | 2000 req/min, expired contracts, batch quote API (500/call) |
| 2025-11-28 | EOD option chain download | Avoid real-time complexity, sufficient for backtesting |
| 2025-11-28 | Phase 1 focus on options intraday | Lower capital requirement, defined risk |
| 2025-11-28 | PostgreSQL over TimescaleDB initially | Simpler setup, upgrade path exists when needed |
| 2025-11-28 | Fyers for trading, Upstox for data | Leverage rate limits across brokers, existing Fyers account |
| 2025-11-28 | Separate future_master & option_master tables | Cleaner normalization, type-specific fields |
| 2025-11-28 | 1-minute base candles | Sufficient for all strategies, aggregate to higher timeframes |
| 2025-11-28 | Event-driven with Redis Streams | Decoupling, replay capability, persistence |

### Appendix H: API Rate Limits Reference

| Broker | Endpoint | Limit | Notes |
|--------|----------|-------|-------|
| **Fyers** | All APIs | 10/sec, 200/min | Combined limit |
| **Fyers** | WebSocket | 200 instruments | Per connection |
| **Upstox** | Order APIs | 25/sec | Higher for orders |
| **Upstox** | Other APIs | 1000/30sec | ~2000/min effective |
| **Upstox** | Batch Quote | 500 instruments/call | Best for scanning |
| **Upstox** | WebSocket | 4000 instruments | Very generous |
| **Upstox** | Historical | 2000/min | Best for backfill |

---

## Document Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **System Architect** | | | |
| **Developer** | | | |
| **Trader** | | | |

---

**END OF DOCUMENT**

*This is a living document and will be updated as the system evolves.*
