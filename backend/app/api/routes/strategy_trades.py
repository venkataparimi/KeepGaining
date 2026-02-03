"""
Strategy Trades API

Endpoints for querying, filtering, and analyzing strategy trade data.
Supports dynamic filtering and aggregations for dashboards and reports.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel
from enum import Enum
import asyncpg
from loguru import logger

router = APIRouter(prefix="/strategy-trades", tags=["Strategy Trades"])

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'


# ============================================================================
# Pydantic Models
# ============================================================================

class TradeSource(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"
    ALL = "all"


class TradeResponse(BaseModel):
    trade_id: int
    strategy_id: str
    strategy_name: str
    symbol: str
    option_symbol: Optional[str]
    option_type: Optional[str]
    strike_price: Optional[float]
    expiry_date: Optional[date] = None
    sector: Optional[str]
    trade_date: date
    entry_time: datetime
    exit_time: Optional[datetime]
    hold_duration_minutes: Optional[int]
    spot_open: Optional[float]
    spot_at_entry: Optional[float]
    entry_premium: float
    exit_premium: Optional[float]
    momentum_pct: Optional[float]
    distance_to_atm_pct: Optional[float]
    signal_type: str
    exit_reason: Optional[str]
    pnl_pct: Optional[float]
    pnl_amount: Optional[float] = None  # P&L in rupees
    is_winner: Optional[bool]
    signal_strength: Optional[str]
    trade_source: str
    quantity: Optional[int] = None


class TradesSummary(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl_pct: float
    avg_pnl_pct: float
    avg_win_pct: Optional[float]
    avg_loss_pct: Optional[float]
    avg_hold_minutes: Optional[float]
    best_trade_pct: Optional[float]
    worst_trade_pct: Optional[float]
    # Money amounts
    total_pnl_amount: Optional[float] = None
    avg_pnl_amount: Optional[float] = None
    total_gross_profit: Optional[float] = None
    total_gross_loss: Optional[float] = None


class SectorPerformance(BaseModel):
    sector: str
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl_pct: float
    avg_pnl_pct: float


class SymbolPerformance(BaseModel):
    symbol: str
    sector: Optional[str]
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl_pct: float
    avg_pnl_pct: float
    best_trade_pct: Optional[float]
    worst_trade_pct: Optional[float]


class DailyPerformance(BaseModel):
    trade_date: date
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl_pct: float


class ExitReasonAnalysis(BaseModel):
    exit_reason: str
    total_trades: int
    winning_trades: int
    win_rate: float
    avg_pnl_pct: float
    avg_hold_minutes: Optional[float]


# ============================================================================
# Database Connection
# ============================================================================

async def get_pool():
    return await asyncpg.create_pool(DB_URL)


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/trades", response_model=List[TradeResponse])
async def get_trades(
    strategy_id: Optional[str] = Query(None, description="Filter by strategy ID"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
    option_type: Optional[str] = Query(None, description="Filter by option type (CE/PE)"),
    exit_reason: Optional[str] = Query(None, description="Filter by exit reason"),
    is_winner: Optional[bool] = Query(None, description="Filter by win/loss"),
    trade_source: TradeSource = Query(TradeSource.ALL, description="Filter by trade source"),
    start_date: Optional[date] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    Get filtered list of strategy trades.
    
    Supports filtering by:
    - Strategy, Symbol, Sector
    - Option type (CE/PE)
    - Exit reason (Target, Stop Loss, Time Stop)
    - Win/Loss status
    - Date range
    - Trade source (backtest, paper, live)
    """
    pool = await get_pool()
    
    try:
        async with pool.acquire() as conn:
            # Build dynamic query
            conditions = []
            params = []
            param_num = 1
            
            if strategy_id:
                conditions.append(f"strategy_id = ${param_num}")
                params.append(strategy_id)
                param_num += 1
            
            if symbol:
                conditions.append(f"symbol = ${param_num}")
                params.append(symbol.upper())
                param_num += 1
            
            if sector:
                conditions.append(f"sector = ${param_num}")
                params.append(sector)
                param_num += 1
            
            if option_type:
                conditions.append(f"option_type = ${param_num}")
                params.append(option_type.upper())
                param_num += 1
            
            if exit_reason:
                conditions.append(f"exit_reason ILIKE ${param_num}")
                params.append(f"%{exit_reason}%")
                param_num += 1
            
            if is_winner is not None:
                conditions.append(f"is_winner = ${param_num}")
                params.append(is_winner)
                param_num += 1
            
            if trade_source != TradeSource.ALL:
                conditions.append(f"trade_source = ${param_num}")
                params.append(trade_source.value)
                param_num += 1
            
            if start_date:
                conditions.append(f"trade_date >= ${param_num}")
                params.append(start_date)
                param_num += 1
            
            if end_date:
                conditions.append(f"trade_date <= ${param_num}")
                params.append(end_date)
                param_num += 1
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT trade_id, strategy_id, strategy_name, symbol, option_symbol,
                       option_type, strike_price, expiry_date, sector, trade_date, entry_time,
                       exit_time, hold_duration_minutes, spot_open, spot_at_entry,
                       entry_premium, exit_premium, momentum_pct, distance_to_atm_pct,
                       signal_type, exit_reason, pnl_pct, pnl_amount, quantity, is_winner, signal_strength,
                       trade_source
                FROM strategy_trades
                WHERE {where_clause}
                ORDER BY trade_date DESC, entry_time DESC
                LIMIT ${param_num} OFFSET ${param_num + 1}
            """
            params.extend([limit, offset])
            
            rows = await conn.fetch(query, *params)
            
            return [TradeResponse(**dict(row)) for row in rows]
    
    finally:
        await pool.close()


@router.get("/summary", response_model=TradesSummary)
async def get_trades_summary(
    strategy_id: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    option_type: Optional[str] = Query(None),
    trade_source: TradeSource = Query(TradeSource.ALL),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    """Get summary statistics for filtered trades."""
    pool = await get_pool()
    
    try:
        async with pool.acquire() as conn:
            conditions = []
            params = []
            param_num = 1
            
            if strategy_id:
                conditions.append(f"strategy_id = ${param_num}")
                params.append(strategy_id)
                param_num += 1
            
            if symbol:
                conditions.append(f"symbol = ${param_num}")
                params.append(symbol.upper())
                param_num += 1
            
            if sector:
                conditions.append(f"sector = ${param_num}")
                params.append(sector)
                param_num += 1
            
            if option_type:
                conditions.append(f"option_type = ${param_num}")
                params.append(option_type.upper())
                param_num += 1
            
            if trade_source != TradeSource.ALL:
                conditions.append(f"trade_source = ${param_num}")
                params.append(trade_source.value)
                param_num += 1
            
            if start_date:
                conditions.append(f"trade_date >= ${param_num}")
                params.append(start_date)
                param_num += 1
            
            if end_date:
                conditions.append(f"trade_date <= ${param_num}")
                params.append(end_date)
                param_num += 1
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            row = await conn.fetchrow(f"""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN NOT is_winner THEN 1 ELSE 0 END) as losing_trades,
                    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(COALESCE(SUM(pnl_pct), 0), 2) as total_pnl_pct,
                    ROUND(COALESCE(AVG(pnl_pct), 0), 2) as avg_pnl_pct,
                    ROUND(AVG(CASE WHEN is_winner THEN pnl_pct END), 2) as avg_win_pct,
                    ROUND(AVG(CASE WHEN NOT is_winner THEN pnl_pct END), 2) as avg_loss_pct,
                    ROUND(AVG(hold_duration_minutes), 0) as avg_hold_minutes,
                    ROUND(MAX(pnl_pct), 2) as best_trade_pct,
                    ROUND(MIN(pnl_pct), 2) as worst_trade_pct
                FROM strategy_trades
                WHERE {where_clause}
            """, *params)
            
            return TradesSummary(
                total_trades=row['total_trades'] or 0,
                winning_trades=row['winning_trades'] or 0,
                losing_trades=row['losing_trades'] or 0,
                win_rate=float(row['win_rate'] or 0),
                total_pnl_pct=float(row['total_pnl_pct'] or 0),
                avg_pnl_pct=float(row['avg_pnl_pct'] or 0),
                avg_win_pct=float(row['avg_win_pct']) if row['avg_win_pct'] else None,
                avg_loss_pct=float(row['avg_loss_pct']) if row['avg_loss_pct'] else None,
                avg_hold_minutes=float(row['avg_hold_minutes']) if row['avg_hold_minutes'] else None,
                best_trade_pct=float(row['best_trade_pct']) if row['best_trade_pct'] else None,
                worst_trade_pct=float(row['worst_trade_pct']) if row['worst_trade_pct'] else None,
            )
    
    finally:
        await pool.close()


@router.get("/by-sector", response_model=List[SectorPerformance])
async def get_sector_performance(
    strategy_id: Optional[str] = Query(None),
    trade_source: TradeSource = Query(TradeSource.ALL),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    """Get performance breakdown by sector (for pie charts)."""
    pool = await get_pool()
    
    try:
        async with pool.acquire() as conn:
            conditions = ["sector IS NOT NULL"]
            params = []
            param_num = 1
            
            if strategy_id:
                conditions.append(f"strategy_id = ${param_num}")
                params.append(strategy_id)
                param_num += 1
            
            if trade_source != TradeSource.ALL:
                conditions.append(f"trade_source = ${param_num}")
                params.append(trade_source.value)
                param_num += 1
            
            if start_date:
                conditions.append(f"trade_date >= ${param_num}")
                params.append(start_date)
                param_num += 1
            
            if end_date:
                conditions.append(f"trade_date <= ${param_num}")
                params.append(end_date)
                param_num += 1
            
            where_clause = " AND ".join(conditions)
            
            rows = await conn.fetch(f"""
                SELECT 
                    sector,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
                    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(COALESCE(SUM(pnl_pct), 0), 2) as total_pnl_pct,
                    ROUND(COALESCE(AVG(pnl_pct), 0), 2) as avg_pnl_pct
                FROM strategy_trades
                WHERE {where_clause}
                GROUP BY sector
                ORDER BY total_pnl_pct DESC
            """, *params)
            
            return [SectorPerformance(
                sector=row['sector'],
                total_trades=row['total_trades'],
                winning_trades=row['winning_trades'],
                win_rate=float(row['win_rate'] or 0),
                total_pnl_pct=float(row['total_pnl_pct'] or 0),
                avg_pnl_pct=float(row['avg_pnl_pct'] or 0),
            ) for row in rows]
    
    finally:
        await pool.close()


@router.get("/by-symbol", response_model=List[SymbolPerformance])
async def get_symbol_performance(
    strategy_id: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    trade_source: TradeSource = Query(TradeSource.ALL),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(20, ge=1, le=100, description="Top N symbols"),
    sort_by: str = Query("total_pnl_pct", description="Sort field")
):
    """Get top performing symbols (for leaderboard)."""
    pool = await get_pool()
    
    try:
        async with pool.acquire() as conn:
            conditions = []
            params = []
            param_num = 1
            
            if strategy_id:
                conditions.append(f"strategy_id = ${param_num}")
                params.append(strategy_id)
                param_num += 1
            
            if sector:
                conditions.append(f"sector = ${param_num}")
                params.append(sector)
                param_num += 1
            
            if trade_source != TradeSource.ALL:
                conditions.append(f"trade_source = ${param_num}")
                params.append(trade_source.value)
                param_num += 1
            
            if start_date:
                conditions.append(f"trade_date >= ${param_num}")
                params.append(start_date)
                param_num += 1
            
            if end_date:
                conditions.append(f"trade_date <= ${param_num}")
                params.append(end_date)
                param_num += 1
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # Validate sort_by
            valid_sorts = ['total_pnl_pct', 'win_rate', 'total_trades', 'avg_pnl_pct']
            if sort_by not in valid_sorts:
                sort_by = 'total_pnl_pct'
            
            rows = await conn.fetch(f"""
                SELECT 
                    symbol,
                    MAX(sector) as sector,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
                    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(COALESCE(SUM(pnl_pct), 0), 2) as total_pnl_pct,
                    ROUND(COALESCE(AVG(pnl_pct), 0), 2) as avg_pnl_pct,
                    ROUND(MAX(pnl_pct), 2) as best_trade_pct,
                    ROUND(MIN(pnl_pct), 2) as worst_trade_pct
                FROM strategy_trades
                WHERE {where_clause}
                GROUP BY symbol
                HAVING COUNT(*) >= 2
                ORDER BY {sort_by} DESC
                LIMIT ${param_num}
            """, *params, limit)
            
            return [SymbolPerformance(
                symbol=row['symbol'],
                sector=row['sector'],
                total_trades=row['total_trades'],
                winning_trades=row['winning_trades'],
                win_rate=float(row['win_rate'] or 0),
                total_pnl_pct=float(row['total_pnl_pct'] or 0),
                avg_pnl_pct=float(row['avg_pnl_pct'] or 0),
                best_trade_pct=float(row['best_trade_pct']) if row['best_trade_pct'] else None,
                worst_trade_pct=float(row['worst_trade_pct']) if row['worst_trade_pct'] else None,
            ) for row in rows]
    
    finally:
        await pool.close()


@router.get("/daily", response_model=List[DailyPerformance])
async def get_daily_performance(
    strategy_id: Optional[str] = Query(None),
    trade_source: TradeSource = Query(TradeSource.ALL),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(30, ge=1, le=365)
):
    """Get daily performance (for charts)."""
    pool = await get_pool()
    
    try:
        async with pool.acquire() as conn:
            conditions = []
            params = []
            param_num = 1
            
            if strategy_id:
                conditions.append(f"strategy_id = ${param_num}")
                params.append(strategy_id)
                param_num += 1
            
            if trade_source != TradeSource.ALL:
                conditions.append(f"trade_source = ${param_num}")
                params.append(trade_source.value)
                param_num += 1
            
            if start_date:
                conditions.append(f"trade_date >= ${param_num}")
                params.append(start_date)
                param_num += 1
            
            if end_date:
                conditions.append(f"trade_date <= ${param_num}")
                params.append(end_date)
                param_num += 1
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            rows = await conn.fetch(f"""
                SELECT 
                    trade_date,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
                    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(COALESCE(SUM(pnl_pct), 0), 2) as total_pnl_pct
                FROM strategy_trades
                WHERE {where_clause}
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT ${param_num}
            """, *params, limit)
            
            return [DailyPerformance(
                trade_date=row['trade_date'],
                total_trades=row['total_trades'],
                winning_trades=row['winning_trades'],
                win_rate=float(row['win_rate'] or 0),
                total_pnl_pct=float(row['total_pnl_pct'] or 0),
            ) for row in rows]
    
    finally:
        await pool.close()


@router.get("/exit-reasons", response_model=List[ExitReasonAnalysis])
async def get_exit_reason_analysis(
    strategy_id: Optional[str] = Query(None),
    trade_source: TradeSource = Query(TradeSource.ALL),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    """Get performance by exit reason."""
    pool = await get_pool()
    
    try:
        async with pool.acquire() as conn:
            conditions = ["exit_reason IS NOT NULL"]
            params = []
            param_num = 1
            
            if strategy_id:
                conditions.append(f"strategy_id = ${param_num}")
                params.append(strategy_id)
                param_num += 1
            
            if trade_source != TradeSource.ALL:
                conditions.append(f"trade_source = ${param_num}")
                params.append(trade_source.value)
                param_num += 1
            
            if start_date:
                conditions.append(f"trade_date >= ${param_num}")
                params.append(start_date)
                param_num += 1
            
            if end_date:
                conditions.append(f"trade_date <= ${param_num}")
                params.append(end_date)
                param_num += 1
            
            where_clause = " AND ".join(conditions)
            
            rows = await conn.fetch(f"""
                SELECT 
                    exit_reason,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winning_trades,
                    ROUND(100.0 * SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(COALESCE(AVG(pnl_pct), 0), 2) as avg_pnl_pct,
                    ROUND(AVG(hold_duration_minutes), 0) as avg_hold_minutes
                FROM strategy_trades
                WHERE {where_clause}
                GROUP BY exit_reason
                ORDER BY total_trades DESC
            """, *params)
            
            return [ExitReasonAnalysis(
                exit_reason=row['exit_reason'],
                total_trades=row['total_trades'],
                winning_trades=row['winning_trades'],
                win_rate=float(row['win_rate'] or 0),
                avg_pnl_pct=float(row['avg_pnl_pct'] or 0),
                avg_hold_minutes=float(row['avg_hold_minutes']) if row['avg_hold_minutes'] else None,
            ) for row in rows]
    
    finally:
        await pool.close()


@router.get("/filters")
async def get_available_filters():
    """Get available filter options (for dropdowns)."""
    pool = await get_pool()
    
    try:
        async with pool.acquire() as conn:
            strategies = await conn.fetch("""
                SELECT DISTINCT strategy_id, strategy_name 
                FROM strategy_trades 
                ORDER BY strategy_id
            """)
            
            symbols = await conn.fetch("""
                SELECT DISTINCT symbol 
                FROM strategy_trades 
                ORDER BY symbol
            """)
            
            sectors = await conn.fetch("""
                SELECT DISTINCT sector 
                FROM strategy_trades 
                WHERE sector IS NOT NULL 
                ORDER BY sector
            """)
            
            exit_reasons = await conn.fetch("""
                SELECT DISTINCT exit_reason 
                FROM strategy_trades 
                WHERE exit_reason IS NOT NULL 
                ORDER BY exit_reason
            """)
            
            date_range = await conn.fetchrow("""
                SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date
                FROM strategy_trades
            """)
            
            return {
                "strategies": [{"id": r['strategy_id'], "name": r['strategy_name']} for r in strategies],
                "symbols": [r['symbol'] for r in symbols],
                "sectors": [r['sector'] for r in sectors],
                "exit_reasons": [r['exit_reason'] for r in exit_reasons],
                "option_types": ["CE", "PE"],
                "trade_sources": ["backtest", "paper", "live"],
                "date_range": {
                    "min": date_range['min_date'].isoformat() if date_range['min_date'] else None,
                    "max": date_range['max_date'].isoformat() if date_range['max_date'] else None
                }
            }
    
    finally:
        await pool.close()


class EquityCurvePoint(BaseModel):
    trade_number: int
    trade_date: date
    symbol: str
    pnl_pct: float
    pnl_amount: float
    cumulative_pnl_pct: float
    cumulative_pnl_amount: float
    drawdown_pct: float


@router.get("/equity-curve", response_model=List[EquityCurvePoint])
async def get_equity_curve(
    strategy_id: Optional[str] = Query(None),
    trade_source: TradeSource = Query(TradeSource.ALL),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    lot_size: int = Query(25, description="Standard lot size for P&L calculation"),
):
    """Get equity curve data for cumulative P&L visualization."""
    pool = await get_pool()
    
    try:
        async with pool.acquire() as conn:
            conditions = []
            params = []
            param_num = 1
            
            if strategy_id:
                conditions.append(f"strategy_id = ${param_num}")
                params.append(strategy_id)
                param_num += 1
            
            if trade_source != TradeSource.ALL:
                conditions.append(f"trade_source = ${param_num}")
                params.append(trade_source.value)
                param_num += 1
            
            if start_date:
                conditions.append(f"trade_date >= ${param_num}")
                params.append(start_date)
                param_num += 1
            
            if end_date:
                conditions.append(f"trade_date <= ${param_num}")
                params.append(end_date)
                param_num += 1
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            rows = await conn.fetch(f"""
                SELECT 
                    trade_date,
                    symbol,
                    pnl_pct,
                    pnl_amount,
                    quantity
                FROM strategy_trades
                WHERE {where_clause}
                ORDER BY trade_date, entry_time
            """, *params)
            
            # Calculate cumulative values and drawdown
            curve = []
            cumulative_pnl_pct = 0.0
            cumulative_pnl_amount = 0.0
            peak_pnl = 0.0
            
            for i, row in enumerate(rows):
                pnl_pct = float(row['pnl_pct'] or 0)
                pnl_amount = float(row['pnl_amount'] or 0)
                
                cumulative_pnl_pct += pnl_pct
                cumulative_pnl_amount += pnl_amount
                
                # Track peak for drawdown
                if cumulative_pnl_amount > peak_pnl:
                    peak_pnl = cumulative_pnl_amount
                
                # Drawdown from peak
                drawdown = 0.0 if peak_pnl == 0 else ((peak_pnl - cumulative_pnl_amount) / peak_pnl) * 100
                
                curve.append(EquityCurvePoint(
                    trade_number=i + 1,
                    trade_date=row['trade_date'],
                    symbol=row['symbol'],
                    pnl_pct=pnl_pct,
                    pnl_amount=round(pnl_amount, 2),
                    cumulative_pnl_pct=round(cumulative_pnl_pct, 2),
                    cumulative_pnl_amount=round(cumulative_pnl_amount, 2),
                    drawdown_pct=round(drawdown, 2),
                ))
            
            return curve
    
    finally:
        await pool.close()

