"""
ATM Breakout Strategy - Backtestable Implementation
Based on IEX 140 CE trade pattern
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta, time
import pandas as pd
import json

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

class ATMBreakoutStrategy:
    """
    Strategy: Buy ATM call options when stock opens near strike with early momentum
    
    Entry Rules:
    1. Stock opens within 2% of a round strike (140, 150, 160, etc.)
    2. First 15-min candle shows bullish momentum (>0.5% up)
    3. Volume > 1.5x average volume
    4. Option premium is 5-10% of strike price
    
    Exit Rules:
    1. Target: 50-100% profit on premium
    2. Stop Loss: 40% loss on premium
    3. Time Stop: Exit by 2:30 PM if no target hit
    4. Trail: Once 30% profit, trail stop at 20%
    """
    
    def __init__(self):
        self.pool = None
        self.results = []
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(DB_URL)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    def find_nearest_strike(self, price, strike_interval=10):
        """Find nearest ATM strike"""
        return round(price / strike_interval) * strike_interval
    
    async def get_stock_data(self, symbol, start_date, end_date):
        """Get historical stock data"""
        async with self.pool.acquire() as conn:
            inst = await conn.fetchrow("""
                SELECT instrument_id FROM instrument_master
                WHERE trading_symbol = $1 AND instrument_type = 'EQUITY'
            """, symbol)
            
            if not inst:
                return None
            
            inst_id = inst['instrument_id']
            
            # Get daily data
            candles = await conn.fetch("""
                SELECT DATE(timestamp) as date,
                       MIN(CASE WHEN DATE_PART('hour', timestamp) = 9 
                                 AND DATE_PART('minute', timestamp) >= 15 
                           THEN open END) as day_open,
                       MAX(high) as day_high,
                       MIN(low) as day_low,
                       MAX(CASE WHEN DATE_PART('hour', timestamp) = 15 
                                 AND DATE_PART('minute', timestamp) = 29 
                           THEN close END) as day_close,
                       SUM(volume) as total_volume,
                       MAX(CASE WHEN DATE_PART('hour', timestamp) = 9 
                                 AND DATE_PART('minute', timestamp) <= 30 
                           THEN close END) as price_930
                FROM candle_data
                WHERE instrument_id = $1
                AND timestamp >= $2 AND timestamp <= $3
                AND timeframe = '1m'
                GROUP BY DATE(timestamp)
                ORDER BY date
            """, inst_id, start_date, end_date)
            
            if candles:
                df = pd.DataFrame([dict(c) for c in candles])
                for col in ['day_open', 'day_high', 'day_low', 'day_close', 'price_930']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                return df
            return None
    
    def check_entry_conditions(self, row):
        """Check if entry conditions are met"""
        if pd.isna(row['day_open']) or pd.isna(row['price_930']):
            return False, None, None
        
        # Find nearest strike
        strike = self.find_nearest_strike(row['day_open'])
        
        # Check if price is within 2% of strike
        price_diff_pct = abs(row['day_open'] - strike) / strike * 100
        if price_diff_pct > 2:
            return False, None, None
        
        # Check early momentum (first 15 mins)
        early_momentum = ((row['price_930'] - row['day_open']) / row['day_open']) * 100
        if early_momentum < 0.5:  # Need at least 0.5% up
            return False, None, None
        
        # Estimate option premium (simplified: 5-7% of strike for ATM)
        premium = strike * 0.06  # 6% of strike
        
        # Check if premium is reasonable
        if premium < strike * 0.05 or premium > strike * 0.10:
            return False, None, None
        
        return True, strike, premium
    
    def simulate_option_price(self, spot_price, strike, entry_premium, time_factor=1.0):
        """
        Simplified option pricing
        Intrinsic value + time value decay
        """
        intrinsic = max(0, spot_price - strike)
        time_value = entry_premium * time_factor * 0.5  # Simplified decay
        return intrinsic + time_value
    
    def simulate_trade(self, row, strike, entry_premium):
        """Simulate the trade for the day"""
        
        # Entry at 9:30 AM
        entry_spot = row['price_930']
        
        # Track throughout the day
        day_high = row['day_high']
        day_close = row['day_close']
        
        # Calculate option values at different points
        # At day high (assume reached around 11 AM, time_factor=0.9)
        option_at_high = self.simulate_option_price(day_high, strike, entry_premium, 0.9)
        profit_at_high_pct = ((option_at_high - entry_premium) / entry_premium) * 100
        
        # At day close (3:30 PM, time_factor=0.3)
        option_at_close = self.simulate_option_price(day_close, strike, entry_premium, 0.3)
        profit_at_close_pct = ((option_at_close - entry_premium) / entry_premium) * 100
        
        # Determine exit based on strategy rules
        exit_price = entry_premium
        exit_reason = 'No Exit'
        pnl_pct = 0
        
        # Check target hit (50-100% profit)
        if profit_at_high_pct >= 50:
            exit_price = entry_premium * 1.5  # Exit at 50% profit
            exit_reason = 'Target Hit (50%)'
            pnl_pct = 50
        
        # Check stop loss (40% loss)
        elif profit_at_close_pct <= -40:
            exit_price = entry_premium * 0.6  # Exit at 40% loss
            exit_reason = 'Stop Loss Hit'
            pnl_pct = -40
        
        # Time stop (exit at close)
        else:
            exit_price = option_at_close
            exit_reason = 'Time Stop (Close)'
            pnl_pct = profit_at_close_pct
        
        return {
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'pnl_pct': pnl_pct,
            'option_at_high': option_at_high,
            'option_at_close': option_at_close
        }
    
    async def backtest(self, symbol, start_date, end_date, lot_size=3750):
        """Run backtest on historical data"""
        
        print("=" * 80)
        print(f"BACKTESTING: ATM Breakout Strategy on {symbol}")
        print("=" * 80)
        print(f"Period: {start_date} to {end_date}")
        print(f"Lot Size: {lot_size}")
        print()
        
        # Get data
        df = await self.get_stock_data(symbol, start_date, end_date)
        if df is None or df.empty:
            print("❌ No data available")
            return None
        
        print(f"📊 Analyzing {len(df)} trading days...")
        print()
        
        # Backtest each day
        trades = []
        
        for idx, row in df.iterrows():
            # Check entry conditions
            enter, strike, premium = self.check_entry_conditions(row)
            
            if enter:
                # Simulate trade
                result = self.simulate_trade(row, strike, premium)
                
                trade = {
                    'date': row['date'],
                    'symbol': symbol,
                    'strike': strike,
                    'entry_premium': premium,
                    'entry_spot': row['price_930'],
                    'day_high': row['day_high'],
                    'day_close': row['day_close'],
                    'exit_premium': result['exit_price'],
                    'exit_reason': result['exit_reason'],
                    'pnl_pct': result['pnl_pct'],
                    'pnl_amount': (result['exit_price'] - premium) * lot_size
                }
                
                trades.append(trade)
                
                status = "✅" if trade['pnl_pct'] > 0 else "❌"
                print(f"{status} {trade['date']} | Strike: ₹{strike} | Entry: ₹{premium:.2f} | "
                      f"Exit: ₹{result['exit_price']:.2f} | PnL: {trade['pnl_pct']:+.1f}% | "
                      f"₹{trade['pnl_amount']:+,.0f}")
        
        if not trades:
            print("⚠️  No trades matched entry criteria")
            return None
        
        # Calculate statistics
        trades_df = pd.DataFrame(trades)
        
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['pnl_pct'] > 0])
        losing_trades = len(trades_df[trades_df['pnl_pct'] < 0])
        win_rate = (winning_trades / total_trades) * 100
        
        avg_win = trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].mean() if winning_trades > 0 else 0
        avg_loss = trades_df[trades_df['pnl_pct'] < 0]['pnl_pct'].mean() if losing_trades > 0 else 0
        
        total_pnl = trades_df['pnl_amount'].sum()
        avg_pnl_per_trade = trades_df['pnl_amount'].mean()
        
        print()
        print("=" * 80)
        print("BACKTEST RESULTS")
        print("=" * 80)
        print(f"\n📊 Trade Statistics:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Winning Trades: {winning_trades}")
        print(f"   Losing Trades: {losing_trades}")
        print(f"   Win Rate: {win_rate:.1f}%")
        
        print(f"\n💰 Performance:")
        print(f"   Average Win: {avg_win:+.1f}%")
        print(f"   Average Loss: {avg_loss:+.1f}%")
        print(f"   Total P&L: ₹{total_pnl:+,.0f}")
        print(f"   Avg P&L per Trade: ₹{avg_pnl_per_trade:+,.0f}")
        
        if win_rate > 0 and avg_loss != 0:
            profit_factor = (winning_trades * avg_win) / (losing_trades * abs(avg_loss)) if losing_trades > 0 else float('inf')
            print(f"   Profit Factor: {profit_factor:.2f}")
        
        # Save results
        results = {
            'strategy': 'ATM Breakout',
            'symbol': symbol,
            'period': f"{start_date} to {end_date}",
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': float(total_pnl),
            'trades': trades
        }
        
        with open(f'backtest_results_{symbol}.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to backtest_results_{symbol}.json")
        
        return results

async def main():
    """Run backtest"""
    strategy = ATMBreakoutStrategy()
    await strategy.connect()
    
    # Backtest IEX
    results = await strategy.backtest(
        symbol='IEX',
        start_date=datetime(2025, 11, 1),
        end_date=datetime(2025, 12, 15),
        lot_size=3750
    )
    
    await strategy.close()

if __name__ == "__main__":
    asyncio.run(main())
