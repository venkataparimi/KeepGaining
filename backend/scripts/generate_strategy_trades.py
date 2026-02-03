#!/usr/bin/env python3
"""
Morning Momentum Alpha - Historical Backtest & Data Generator

Backtests the strategy for the past 3 months and stores results in the database
for frontend display and analysis.

Usage:
    python generate_strategy_trades.py
    python generate_strategy_trades.py --months 6
    python generate_strategy_trades.py --start 2024-09-01 --end 2024-12-19
"""

import asyncio
import asyncpg
import argparse
from datetime import datetime, date, time as dt_time, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

# Sector mapping for F&O stocks
SECTOR_MAP = {
    # Banks
    'HDFCBANK': 'Banking', 'ICICIBANK': 'Banking', 'SBIN': 'Banking', 'KOTAKBANK': 'Banking',
    'AXISBANK': 'Banking', 'INDUSINDBK': 'Banking', 'BANDHANBNK': 'Banking', 'FEDERALBNK': 'Banking',
    'IDFCFIRSTB': 'Banking', 'PNB': 'Banking', 'AUBANK': 'Banking', 'BANKBARODA': 'Banking',
    # IT
    'TCS': 'IT', 'INFY': 'IT', 'WIPRO': 'IT', 'HCLTECH': 'IT', 'TECHM': 'IT',
    'LTIM': 'IT', 'MPHASIS': 'IT', 'COFORGE': 'IT', 'PERSISTENT': 'IT',
    # Auto
    'MARUTI': 'Auto', 'TATAMOTORS': 'Auto', 'M&M': 'Auto', 'BAJAJ-AUTO': 'Auto',
    'HEROMOTOCO': 'Auto', 'EICHERMOT': 'Auto', 'ASHOKLEY': 'Auto', 'TVSMOTOR': 'Auto',
    # NBFC
    'BAJFINANCE': 'NBFC', 'BAJAJFINSV': 'NBFC', 'CHOLAFIN': 'NBFC', 'SHRIRAMFIN': 'NBFC',
    'MUTHOOTFIN': 'NBFC', 'LICHSGFIN': 'NBFC', 'MANAPPURAM': 'NBFC', 'ABCAPITAL': 'NBFC',
    # Pharma
    'SUNPHARMA': 'Pharma', 'DRREDDY': 'Pharma', 'CIPLA': 'Pharma', 'DIVISLAB': 'Pharma',
    'APOLLOHOSP': 'Pharma', 'BIOCON': 'Pharma', 'LAURUSLABS': 'Pharma', 'ALKEM': 'Pharma',
    # Energy
    'RELIANCE': 'Energy', 'ONGC': 'Energy', 'BPCL': 'Energy', 'IOC': 'Energy',
    'GAIL': 'Energy', 'ADANIGREEN': 'Energy', 'TATAPOWER': 'Energy', 'NTPC': 'Energy',
    'POWERGRID': 'Energy', 'ADANIPORTS': 'Energy',
    # Metals
    'TATASTEEL': 'Metals', 'JSWSTEEL': 'Metals', 'HINDALCO': 'Metals', 'VEDL': 'Metals',
    'COALINDIA': 'Metals', 'NMDC': 'Metals', 'JINDALSTEL': 'Metals', 'SAIL': 'Metals',
    # FMCG
    'HINDUNILVR': 'FMCG', 'ITC': 'FMCG', 'NESTLEIND': 'FMCG', 'BRITANNIA': 'FMCG',
    'DABUR': 'FMCG', 'MARICO': 'FMCG', 'GODREJCP': 'FMCG', 'TATACONSUM': 'FMCG',
    # Cement
    'ULTRACEMCO': 'Cement', 'SHREECEM': 'Cement', 'AMBUJACEM': 'Cement', 'ACC': 'Cement',
    'DALBHARAT': 'Cement', 'RAMCOCEM': 'Cement',
    # Telecom
    'BHARTIARTL': 'Telecom', 'IDEA': 'Telecom',
    # Conglomerate
    'LT': 'Infra', 'ADANIENT': 'Conglomerate', 'ADANIPORTS': 'Conglomerate',
    # Others
    'TITAN': 'Consumer', 'ASIANPAINT': 'Consumer', 'PIDILITIND': 'Consumer',
    'HAVELLS': 'Consumer', 'VOLTAS': 'Consumer', 'WHIRLPOOL': 'Consumer',
    'ABB': 'Industrial', 'SIEMENS': 'Industrial', 'CUMMINSIND': 'Industrial',
    'BHARATFORG': 'Industrial', 'BEL': 'Defence', 'HAL': 'Defence',
}


@dataclass
class Trade:
    """Trade result from backtest."""
    symbol: str
    option_symbol: str
    option_type: str
    strike_price: int
    expiry_date: date
    trade_date: date
    entry_time: datetime
    exit_time: datetime
    spot_open: float
    spot_at_entry: float
    spot_at_exit: float
    entry_premium: float
    exit_premium: float
    momentum_pct: float
    distance_to_atm_pct: float
    signal_type: str
    exit_reason: str
    pnl_pct: float
    is_winner: bool
    hold_duration_minutes: int
    signal_strength: str


class MorningMomentumBacktest:
    """Backtester for Morning Momentum Alpha strategy."""
    
    # Strategy parameters
    MIN_MOMENTUM_PCT = 0.5
    MAX_ATM_DISTANCE_PCT = 2.0
    ENTRY_WINDOW_START = dt_time(9, 25)
    ENTRY_WINDOW_END = dt_time(9, 35)
    TARGET_PCT = 50.0
    STOPLOSS_PCT = 40.0
    TIME_EXIT = dt_time(14, 30)
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self.pool = None
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
        logger.info("Connected to database")
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def create_tables(self):
        """Create strategy_trades table if not exists."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_trades (
                    trade_id SERIAL PRIMARY KEY,
                    strategy_id VARCHAR(50) NOT NULL,
                    strategy_name VARCHAR(100) NOT NULL,
                    symbol VARCHAR(50) NOT NULL,
                    option_symbol VARCHAR(100),
                    option_type VARCHAR(2),
                    strike_price DECIMAL(12, 2),
                    expiry_date DATE,
                    sector VARCHAR(50),
                    industry VARCHAR(100),
                    market_cap_category VARCHAR(20),
                    trade_date DATE NOT NULL,
                    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
                    exit_time TIMESTAMP WITH TIME ZONE,
                    hold_duration_minutes INTEGER,
                    spot_open DECIMAL(12, 2),
                    spot_at_entry DECIMAL(12, 2),
                    spot_at_exit DECIMAL(12, 2),
                    entry_premium DECIMAL(12, 2) NOT NULL,
                    exit_premium DECIMAL(12, 2),
                    momentum_pct DECIMAL(8, 4),
                    distance_to_atm_pct DECIMAL(8, 4),
                    signal_type VARCHAR(20) NOT NULL,
                    exit_reason VARCHAR(50),
                    pnl_amount DECIMAL(12, 2),
                    pnl_pct DECIMAL(8, 4),
                    is_winner BOOLEAN,
                    quantity INTEGER,
                    position_value DECIMAL(14, 2),
                    signal_strength VARCHAR(20),
                    trade_source VARCHAR(20) NOT NULL DEFAULT 'backtest',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            # Create indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_st_strategy ON strategy_trades(strategy_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_st_symbol ON strategy_trades(symbol)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_st_trade_date ON strategy_trades(trade_date)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_st_sector ON strategy_trades(sector)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_st_is_winner ON strategy_trades(is_winner)")
            
            logger.info("✅ Created strategy_trades table")
    
    async def get_trading_days(self, start_date: date, end_date: date) -> List[date]:
        """Get list of trading days in the date range."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT DATE(timestamp) as trade_date
                FROM candle_data
                WHERE DATE(timestamp) BETWEEN $1 AND $2
                ORDER BY trade_date
            """, start_date, end_date)
            return [row['trade_date'] for row in rows]
    
    async def get_fno_stocks(self) -> List[str]:
        """Get list of F&O stocks with available data."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT im.trading_symbol
                FROM instrument_master im
                WHERE im.instrument_type = 'EQUITY'
                  AND im.segment = 'EQ'
                  AND EXISTS (
                      SELECT 1 FROM candle_data cd 
                      WHERE cd.instrument_id = im.instrument_id
                  )
                ORDER BY im.trading_symbol
            """)
            return [row['trading_symbol'] for row in rows]
    
    async def get_morning_candles(self, symbol: str, trade_date: date) -> Dict:
        """Get opening candles for momentum calculation."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1 
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp::time >= '03:45:00'  -- 9:15 IST in UTC
                  AND c.timestamp::time <= '04:10:00'  -- 9:40 IST in UTC
                ORDER BY c.timestamp
            """, symbol, trade_date)
            
            if not rows:
                return {}
            
            # First candle is 9:15 open
            spot_open = float(rows[0]['open'])
            
            # Find candle closest to 9:30 AM (04:00 UTC) for entry
            entry_idx = 0
            target_time = dt_time(4, 0)
            
            for i, row in enumerate(rows):
                # We want the candle closest to 9:30
                if row['timestamp'].time() >= target_time:
                    entry_idx = i
                    break
            
            # If we didn't reach 9:30, use the last one
            if entry_idx == 0 and len(rows) > 0:
                entry_idx = len(rows) - 1
                
            spot_at_entry = float(rows[entry_idx]['close'])
            entry_time = rows[entry_idx]['timestamp']
            
            return {
                'spot_open': spot_open,
                'spot_at_entry': spot_at_entry,
                'entry_time': entry_time,
                'momentum_pct': ((spot_at_entry - spot_open) / spot_open) * 100
            }
    
    async def get_atm_option_data(
        self, 
        symbol: str, 
        spot_price: float, 
        option_type: str, 
        trade_date: date,
        entry_time: datetime
    ) -> Optional[Dict]:
        """Get ATM option entry and intraday data for P&L simulation."""
        
        # Calculate ATM strike
        if spot_price < 500:
            strike_step = 10
        elif spot_price < 1000:
            strike_step = 50
        elif spot_price < 5000:
            strike_step = 100
        else:
            strike_step = 500
        
        atm_strike = round(spot_price / strike_step) * strike_step
        distance_pct = abs((spot_price - atm_strike) / atm_strike) * 100
        
        async with self.pool.acquire() as conn:
            # Get option candles for the day
            rows = await conn.fetch("""
                SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume, om.expiry_date
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                JOIN option_master om ON im.instrument_id = om.instrument_id
                WHERE im.underlying = $1 
                  AND im.instrument_type = $2
                  AND om.strike_price = $3
                  AND om.expiry_date >= $4
                  AND DATE(c.timestamp) = $4
                ORDER BY om.expiry_date, c.timestamp
            """, symbol, option_type, atm_strike, trade_date)
            
            if not rows or len(rows) < 5:
                return None
            
            # Find entry candle (around 9:30)
            entry_candle = None
            for row in rows:
                if row['timestamp'].time() >= dt_time(4, 0):  # 9:30 IST
                    entry_candle = row
                    break
            
            if not entry_candle:
                entry_candle = rows[0]
            
            entry_premium = float(entry_candle['close'])
            expiry_date = rows[0]['expiry_date']

            if entry_premium <= 0:
                return None
            
            # Simulate intraday P&L tracking
            target_premium = entry_premium * (1 + self.TARGET_PCT / 100)
            stoploss_premium = entry_premium * (1 - self.STOPLOSS_PCT / 100)
            
            exit_premium = None
            exit_time = None
            exit_reason = None
            
            for row in rows:
                candle_time = row['timestamp'].time()
                
                # Skip candles before entry
                if candle_time < dt_time(4, 0):  # Before 9:30 IST
                    continue
                
                # Use CLOSE price for exits (matches backtest_comparison.py logic)
                # This ignores intraday wicks and waits for candle close confirmation
                current_price = float(row['close'])
                
                # Check target hit (on Close)
                if current_price >= target_premium:
                    exit_premium = current_price # Or target_premium if limit order? 
                    # Backtest comparison uses close, so we use close to match results exactly.
                    exit_time = row['timestamp']
                    exit_reason = 'Target (50%)'
                    break
                
                # Check stop loss hit (on Close)
                if current_price <= stoploss_premium:
                    exit_premium = current_price
                    exit_time = row['timestamp']
                    exit_reason = 'Stop Loss (40%)'
                    break
                
                # Check time exit
                if candle_time >= dt_time(9, 0):  # 2:30 PM IST
                    exit_premium = close
                    exit_time = row['timestamp']
                    exit_reason = 'Time Stop (14:30)'
                    break
            
            # If no exit found, use last candle
            if exit_premium is None:
                exit_premium = float(rows[-1]['close'])
                exit_time = rows[-1]['timestamp']
                exit_reason = 'End of Day'
            
            pnl_pct = ((exit_premium - entry_premium) / entry_premium) * 100
            
            return {
                'strike': atm_strike,
                'distance_pct': distance_pct,
                'entry_premium': entry_premium,
                'exit_premium': exit_premium,
                'exit_time': exit_time,
                'exit_reason': exit_reason,
                'pnl_pct': pnl_pct,
                'is_winner': pnl_pct > 0,
                'expiry_date': expiry_date
            }
    
    async def backtest_day(self, trade_date: date, stocks: List[str]) -> List[Trade]:
        """Run backtest for a single day."""
        trades = []
        
        for symbol in stocks:
            try:
                # Get morning data
                morning_data = await self.get_morning_candles(symbol, trade_date)
                if not morning_data:
                    continue
                
                momentum_pct = morning_data['momentum_pct']
                
                # Check momentum threshold
                if abs(momentum_pct) < self.MIN_MOMENTUM_PCT:
                    continue
                
                # Determine option type
                option_type = 'CE' if momentum_pct > 0 else 'PE'
                signal_type = 'long_entry' if momentum_pct > 0 else 'short_entry'
                
                # Get option data
                option_data = await self.get_atm_option_data(
                    symbol,
                    morning_data['spot_at_entry'],
                    option_type,
                    trade_date,
                    morning_data['entry_time']
                )
                
                if not option_data:
                    continue
                
                # Check ATM distance
                if option_data['distance_pct'] > self.MAX_ATM_DISTANCE_PCT:
                    continue
                
                # Calculate signal strength
                abs_momentum = abs(momentum_pct)
                if abs_momentum >= 1.0:
                    strength = 'strong'
                elif abs_momentum >= 0.7:
                    strength = 'moderate'
                else:
                    strength = 'weak'
                
                # Calculate hold duration
                entry_time = morning_data['entry_time']
                exit_time = option_data['exit_time']
                hold_minutes = int((exit_time - entry_time).total_seconds() / 60)
                
                # Create trade record
                trade = Trade(
                    symbol=symbol,
                    option_symbol=f"{symbol}{option_data['strike']}{option_type}",
                    option_type=option_type,
                    strike_price=option_data['strike'],
                    expiry_date=option_data['expiry_date'],
                    trade_date=trade_date,
                    entry_time=entry_time,
                    exit_time=exit_time,
                    spot_open=morning_data['spot_open'],
                    spot_at_entry=morning_data['spot_at_entry'],
                    spot_at_exit=morning_data['spot_at_entry'],  # Approximate
                    entry_premium=option_data['entry_premium'],
                    exit_premium=option_data['exit_premium'],
                    momentum_pct=momentum_pct,
                    distance_to_atm_pct=option_data['distance_pct'],
                    signal_type=signal_type,
                    exit_reason=option_data['exit_reason'],
                    pnl_pct=option_data['pnl_pct'],
                    is_winner=option_data['is_winner'],
                    hold_duration_minutes=hold_minutes,
                    signal_strength=strength
                )
                trades.append(trade)
                
            except Exception as e:
                logger.debug(f"Error processing {symbol} on {trade_date}: {e}")
                continue
        
        return trades
    
    async def save_trades(self, trades: List[Trade]):
        """Save trades to database."""
        if not trades:
            return
        
        async with self.pool.acquire() as conn:
            for trade in trades:
                sector = SECTOR_MAP.get(trade.symbol, 'Other')
                
                await conn.execute("""
                    INSERT INTO strategy_trades (
                        strategy_id, strategy_name, symbol, option_symbol, option_type,
                        strike_price, expiry_date, sector, trade_date, entry_time, exit_time,
                        hold_duration_minutes, spot_open, spot_at_entry, spot_at_exit,
                        entry_premium, exit_premium, momentum_pct, distance_to_atm_pct,
                        signal_type, exit_reason, pnl_pct, is_winner, signal_strength,
                        trade_source
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18,
                        $19, $20, $21, $22, $23, $24, $25
                    )
                    ON CONFLICT DO NOTHING
                """,
                'MMALPHA', 'Morning Momentum Alpha',
                trade.symbol, trade.option_symbol, trade.option_type,
                trade.strike_price, trade.expiry_date, sector, trade.trade_date,
                trade.entry_time, trade.exit_time, trade.hold_duration_minutes,
                trade.spot_open, trade.spot_at_entry, trade.spot_at_exit,
                trade.entry_premium, trade.exit_premium, trade.momentum_pct,
                trade.distance_to_atm_pct, trade.signal_type, trade.exit_reason,
                trade.pnl_pct, trade.is_winner, trade.signal_strength, 'backtest'
                )
    
    async def run(self, start_date: date, end_date: date):
        """Run full backtest."""
        await self.connect()
        
        try:
            # Create tables
            await self.create_tables()
            
            # Clear existing backtest data
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM strategy_trades 
                    WHERE strategy_id = 'MMALPHA' 
                      AND trade_source = 'backtest'
                      AND trade_date BETWEEN $1 AND $2
                """, start_date, end_date)
            
            # Get trading days
            trading_days = await self.get_trading_days(start_date, end_date)
            logger.info(f"Found {len(trading_days)} trading days")
            
            # Get stocks
            stocks = await self.get_fno_stocks()
            logger.info(f"Scanning {len(stocks)} F&O stocks")
            
            # Run backtest
            all_trades = []
            for i, trade_date in enumerate(trading_days):
                trades = await self.backtest_day(trade_date, stocks)
                all_trades.extend(trades)
                
                if trades:
                    await self.save_trades(trades)
                    winners = sum(1 for t in trades if t.is_winner)
                    logger.info(f"{trade_date}: {len(trades)} trades ({winners} winners)")
                
                if (i + 1) % 10 == 0:
                    logger.info(f"Progress: {i+1}/{len(trading_days)} days processed")
            
            # Print summary
            print("\n" + "=" * 60)
            print("  BACKTEST COMPLETE - MORNING MOMENTUM ALPHA")
            print("=" * 60)
            print(f"  Period: {start_date} to {end_date}")
            print(f"  Trading Days: {len(trading_days)}")
            print(f"  Total Trades: {len(all_trades)}")
            
            if all_trades:
                winners = sum(1 for t in all_trades if t.is_winner)
                win_rate = 100 * winners / len(all_trades)
                avg_pnl = sum(t.pnl_pct for t in all_trades) / len(all_trades)
                total_pnl = sum(t.pnl_pct for t in all_trades)
                
                print(f"  Winning Trades: {winners}")
                print(f"  Win Rate: {win_rate:.1f}%")
                print(f"  Avg P&L: {avg_pnl:+.2f}%")
                print(f"  Total P&L: {total_pnl:+.2f}%")
                
                # By option type
                ce_trades = [t for t in all_trades if t.option_type == 'CE']
                pe_trades = [t for t in all_trades if t.option_type == 'PE']
                if ce_trades:
                    ce_win = 100 * sum(1 for t in ce_trades if t.is_winner) / len(ce_trades)
                    print(f"  CE Trades: {len(ce_trades)} ({ce_win:.1f}% win)")
                if pe_trades:
                    pe_win = 100 * sum(1 for t in pe_trades if t.is_winner) / len(pe_trades)
                    print(f"  PE Trades: {len(pe_trades)} ({pe_win:.1f}% win)")
            
            print("=" * 60)
            print("  Data saved to: strategy_trades table")
            print("=" * 60 + "\n")
            
        finally:
            await self.close()


async def main():
    parser = argparse.ArgumentParser(description='Generate Morning Momentum Alpha backtest data')
    parser.add_argument('--months', type=int, default=3, help='Number of months to backtest')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if args.start and args.end:
        start_date = datetime.strptime(args.start, '%Y-%m-%d').date()
        end_date = datetime.strptime(args.end, '%Y-%m-%d').date()
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=args.months * 30)
    
    logger.info(f"Running backtest from {start_date} to {end_date}")
    
    backtest = MorningMomentumBacktest()
    await backtest.run(start_date, end_date)


if __name__ == "__main__":
    asyncio.run(main())
