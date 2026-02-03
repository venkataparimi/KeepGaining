"""
Strategy Trades Table and Repository

Stores all strategy trades (backtested and live) for analysis and reporting.
Designed for fast queries and flexible reporting.
"""

from sqlalchemy import text
from datetime import datetime
from typing import Optional

# SQL to create the strategy_trades table
CREATE_STRATEGY_TRADES_TABLE = """
-- Strategy Trades Master Table
-- Stores all trades from backtests and live execution for analysis

CREATE TABLE IF NOT EXISTS strategy_trades (
    trade_id SERIAL PRIMARY KEY,
    
    -- Strategy identification
    strategy_id VARCHAR(50) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    
    -- Instrument details
    symbol VARCHAR(50) NOT NULL,           -- Underlying symbol (e.g., RELIANCE)
    option_symbol VARCHAR(100),            -- Full option symbol (e.g., RELIANCE24DEC1300CE)
    option_type VARCHAR(2),                -- CE or PE
    strike_price DECIMAL(12, 2),
    expiry_date DATE,
    
    -- Stock classification (for sector analysis)
    sector VARCHAR(50),
    industry VARCHAR(100),
    market_cap_category VARCHAR(20),       -- LARGECAP, MIDCAP, SMALLCAP
    
    -- Trade timing
    trade_date DATE NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
    exit_time TIMESTAMP WITH TIME ZONE,
    hold_duration_minutes INTEGER,
    
    -- Price data
    spot_open DECIMAL(12, 2),              -- Stock open price
    spot_at_entry DECIMAL(12, 2),          -- Stock price at entry
    spot_at_exit DECIMAL(12, 2),           -- Stock price at exit
    entry_premium DECIMAL(12, 2) NOT NULL, -- Option premium at entry
    exit_premium DECIMAL(12, 2),           -- Option premium at exit
    
    -- Momentum data
    momentum_pct DECIMAL(8, 4),            -- Early momentum %
    distance_to_atm_pct DECIMAL(8, 4),     -- Distance from ATM %
    
    -- Trade outcome
    signal_type VARCHAR(20) NOT NULL,      -- long_entry, short_entry
    exit_reason VARCHAR(50),               -- Target, Stop Loss, Time Stop
    pnl_amount DECIMAL(12, 2),             -- Absolute P&L
    pnl_pct DECIMAL(8, 4),                 -- P&L %
    is_winner BOOLEAN,
    
    -- Position details
    quantity INTEGER,
    position_value DECIMAL(14, 2),
    
    -- Metadata
    signal_strength VARCHAR(20),           -- strong, moderate, weak
    trade_source VARCHAR(20) NOT NULL DEFAULT 'backtest',  -- backtest, paper, live
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes for fast queries
    CONSTRAINT uk_strategy_trades UNIQUE (strategy_id, symbol, trade_date, entry_time)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_st_strategy ON strategy_trades(strategy_id);
CREATE INDEX IF NOT EXISTS idx_st_symbol ON strategy_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_st_trade_date ON strategy_trades(trade_date);
CREATE INDEX IF NOT EXISTS idx_st_sector ON strategy_trades(sector);
CREATE INDEX IF NOT EXISTS idx_st_is_winner ON strategy_trades(is_winner);
CREATE INDEX IF NOT EXISTS idx_st_option_type ON strategy_trades(option_type);
CREATE INDEX IF NOT EXISTS idx_st_exit_reason ON strategy_trades(exit_reason);
CREATE INDEX IF NOT EXISTS idx_st_trade_source ON strategy_trades(trade_source);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_st_strategy_date ON strategy_trades(strategy_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_st_symbol_date ON strategy_trades(symbol, trade_date);
CREATE INDEX IF NOT EXISTS idx_st_sector_winner ON strategy_trades(sector, is_winner);

-- Comment
COMMENT ON TABLE strategy_trades IS 'Stores all strategy trades for analysis and reporting. Supports backtest, paper, and live trades.';
"""

# SQL for summary views
CREATE_SUMMARY_VIEWS = """
-- Daily Performance Summary
CREATE OR REPLACE VIEW v_daily_strategy_performance AS
SELECT 
    trade_date,
    strategy_id,
    strategy_name,
    COUNT(*) as total_trades,
    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
    SUM(CASE WHEN NOT is_winner THEN 1 ELSE 0 END) as losing_trades,
    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(SUM(pnl_pct), 2) as total_pnl_pct,
    ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
    ROUND(AVG(CASE WHEN is_winner THEN pnl_pct END), 2) as avg_win_pct,
    ROUND(AVG(CASE WHEN NOT is_winner THEN pnl_pct END), 2) as avg_loss_pct
FROM strategy_trades
GROUP BY trade_date, strategy_id, strategy_name
ORDER BY trade_date DESC;

-- Sector Performance
CREATE OR REPLACE VIEW v_sector_performance AS
SELECT 
    sector,
    strategy_id,
    COUNT(*) as total_trades,
    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(SUM(pnl_pct), 2) as total_pnl_pct,
    ROUND(AVG(pnl_pct), 2) as avg_pnl_pct
FROM strategy_trades
WHERE sector IS NOT NULL
GROUP BY sector, strategy_id
ORDER BY win_rate DESC;

-- Top Performing Symbols
CREATE OR REPLACE VIEW v_symbol_performance AS
SELECT 
    symbol,
    sector,
    strategy_id,
    COUNT(*) as total_trades,
    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(SUM(pnl_pct), 2) as total_pnl_pct,
    ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
    ROUND(MAX(pnl_pct), 2) as best_trade_pct,
    ROUND(MIN(pnl_pct), 2) as worst_trade_pct
FROM strategy_trades
GROUP BY symbol, sector, strategy_id
HAVING COUNT(*) >= 3
ORDER BY total_pnl_pct DESC;

-- Option Type Analysis
CREATE OR REPLACE VIEW v_option_type_performance AS
SELECT 
    option_type,
    strategy_id,
    COUNT(*) as total_trades,
    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(SUM(pnl_pct), 2) as total_pnl_pct,
    ROUND(AVG(pnl_pct), 2) as avg_pnl_pct
FROM strategy_trades
WHERE option_type IS NOT NULL
GROUP BY option_type, strategy_id;

-- Exit Reason Analysis
CREATE OR REPLACE VIEW v_exit_reason_analysis AS
SELECT 
    exit_reason,
    strategy_id,
    COUNT(*) as total_trades,
    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(AVG(pnl_pct), 2) as avg_pnl_pct,
    ROUND(AVG(hold_duration_minutes), 0) as avg_hold_minutes
FROM strategy_trades
WHERE exit_reason IS NOT NULL
GROUP BY exit_reason, strategy_id;
"""

async def create_strategy_trades_table(pool):
    """Create the strategy trades table and views."""
    async with pool.acquire() as conn:
        await conn.execute(CREATE_STRATEGY_TRADES_TABLE)
        await conn.execute(CREATE_SUMMARY_VIEWS)
        print("✅ Created strategy_trades table and summary views")
