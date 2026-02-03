"""
Backtest Strategy A: Indicator-Based 14:00 Entry
December 2025

Entry Rules:
- Time: 14:00
- RSI: 45-55 (neutral zone)
- MACD: Bullish (MACD > Signal)
- Volume: >1.5x average
- Price: In middle of morning range (40-60%)
- Action: Enter ATM CE

Exit Rules:
- Target: 50%
- Stop: -40%
- Time: 15:30 or EOD
"""
import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from collections import defaultdict

class StrategyABacktest:
    def __init__(self, db_url):
        self.db_url = db_url
        self.pool = None
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    def calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period]) if len(gains) >= period else 0
        avg_loss = np.mean(losses[:period]) if len(losses) >= period else 0
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, prices):
        """Calculate MACD"""
        if len(prices) < 26:
            return 0, 0, 0
            
        exp1 = pd.Series(prices).ewm(span=12, adjust=False).mean()
        exp2 = pd.Series(prices).ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal_line
        return float(macd.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])
    
    async def get_fo_stocks(self):
        """Get list of F&O stocks"""
        async with self.pool.acquire() as conn:
            result = await conn.fetch("""
                SELECT DISTINCT underlying
                FROM instrument_master
                WHERE instrument_type = 'FUTURES'
                AND underlying NOT IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY')
                ORDER BY underlying
            """)
            return [r['underlying'] for r in result]
    
    async def check_entry_signal(self, stock, trade_date):
        """Check if entry signal exists at 14:00"""
        
        async with self.pool.acquire() as conn:
            # Get candle data for the day
            query = """
                SELECT 
                    cd.timestamp,
                    cd.open,
                    cd.high,
                    cd.low,
                    cd.close,
                    cd.volume
                FROM candle_data cd
                JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                WHERE im.underlying = $1
                AND im.instrument_type = 'FUTURES'
                AND DATE(cd.timestamp) = $2
                ORDER BY cd.timestamp
            """
            
            data = await conn.fetch(query, stock, trade_date)
            
            if not data or len(data) < 50:
                return None
            
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp']) + pd.Timedelta(hours=5, minutes=30)
            df['time'] = df['timestamp'].dt.time
            
            # Find 14:00
            from datetime import time as dt_time
            entry_time = dt_time(14, 0)
            entry_candles = df[df['time'] >= entry_time]
            
            if len(entry_candles) == 0:
                return None
            
            entry_idx = entry_candles.index[0]
            entry_candle = df.loc[entry_idx]
            
            # Get data till entry
            data_till_entry = df.loc[:entry_idx]
            prices = data_till_entry['close'].values.astype(float)
            
            # Calculate indicators
            rsi = self.calculate_rsi(prices, 14) if len(prices) >= 14 else 50
            macd, signal, histogram = self.calculate_macd(prices)
            
            # Volume check
            avg_volume = np.mean(data_till_entry['volume'].values[-20:].astype(float))
            current_volume = float(entry_candle['volume'])
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            # Morning range
            morning_df = data_till_entry
            morning_high = float(morning_df['high'].max())
            morning_low = float(morning_df['low'].min())
            entry_price = float(entry_candle['close'])
            
            # Range position
            if morning_high > morning_low:
                range_position = ((entry_price - morning_low) / (morning_high - morning_low)) * 100
            else:
                range_position = 50
            
            # Check entry conditions
            conditions = {
                'rsi_ok': 45 <= rsi <= 55,
                'macd_ok': macd > signal,
                'volume_ok': volume_ratio > 1.5,
                'range_ok': 40 <= range_position <= 60
            }
            
            all_conditions_met = all(conditions.values())
            
            if all_conditions_met:
                return {
                    'stock': stock,
                    'date': trade_date,
                    'entry_price': entry_price,
                    'entry_idx': entry_idx,
                    'rsi': rsi,
                    'macd': macd,
                    'signal': signal,
                    'volume_ratio': volume_ratio,
                    'range_position': range_position,
                    'morning_high': morning_high,
                    'morning_low': morning_low
                }
            
            return None
    
    async def simulate_trade(self, signal, df):
        """Simulate the option trade"""
        entry_idx = signal['entry_idx']
        entry_price = signal['entry_price']
        
        # Post-entry data
        post_entry = df.loc[entry_idx+1:]
        
        if len(post_entry) == 0:
            return None
        
        # Simulate option movement (rough approximation)
        # Option moves ~2x the underlying percentage move
        max_price = float(post_entry['high'].max())
        min_price = float(post_entry['low'].min())
        close_price = float(post_entry.iloc[-1]['close'])
        
        max_gain_pct = ((max_price - entry_price) / entry_price) * 100 * 2  # 2x leverage
        max_loss_pct = ((min_price - entry_price) / entry_price) * 100 * 2
        final_pct = ((close_price - entry_price) / entry_price) * 100 * 2
        
        # Check exit conditions
        target = 50  # 50% target
        stop = -40  # -40% stop
        
        if max_gain_pct >= target:
            exit_pct = target
            exit_reason = "Target"
        elif max_loss_pct <= stop:
            exit_pct = stop
            exit_reason = "Stop Loss"
        else:
            exit_pct = final_pct
            exit_reason = "EOD"
        
        # Estimate P&L (assuming ₹20K capital per trade)
        capital = 20000
        pnl = capital * (exit_pct / 100)
        
        return {
            'exit_pct': exit_pct,
            'exit_reason': exit_reason,
            'pnl': pnl,
            'max_gain_pct': max_gain_pct,
            'max_loss_pct': max_loss_pct
        }
    
    async def backtest_december(self):
        """Backtest Strategy A for December 2025"""
        
        print("=" * 80)
        print("🧪 BACKTESTING STRATEGY A - DECEMBER 2025")
        print("=" * 80)
        print()
        print("Strategy Rules:")
        print("  Entry Time: 14:00")
        print("  RSI: 45-55 (neutral)")
        print("  MACD: Bullish (MACD > Signal)")
        print("  Volume: >1.5x average")
        print("  Range Position: 40-60%")
        print("  Exit: 50% target / -40% stop / EOD")
        print()
        print("-" * 80)
        print()
        
        # Get F&O stocks
        stocks = await self.get_fo_stocks()
        print(f"Testing on {len(stocks)} F&O stocks")
        print()
        
        # December 2025 trading days
        start_date = date(2025, 12, 1)
        end_date = date(2025, 12, 15)  # Up to available data
        
        current_date = start_date
        all_trades = []
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            print(f"📅 Testing {current_date.strftime('%Y-%m-%d')}...")
            
            day_signals = []
            
            # Check each stock
            for stock in stocks[:20]:  # Limit to first 20 for speed
                signal = await self.check_entry_signal(stock, current_date)
                if signal:
                    day_signals.append(signal)
            
            print(f"   Found {len(day_signals)} entry signals")
            
            # Simulate trades
            for signal in day_signals:
                # Get full day data for simulation
                async with self.pool.acquire() as conn:
                    query = """
                        SELECT timestamp, open, high, low, close, volume
                        FROM candle_data cd
                        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                        WHERE im.underlying = $1
                        AND im.instrument_type = 'FUTURES'
                        AND DATE(cd.timestamp) = $2
                        ORDER BY cd.timestamp
                    """
                    data = await conn.fetch(query, signal['stock'], current_date)
                    
                    if data:
                        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        df['timestamp'] = pd.to_datetime(df['timestamp']) + pd.Timedelta(hours=5, minutes=30)
                        
                        trade_result = await self.simulate_trade(signal, df)
                        
                        if trade_result:
                            trade = {**signal, **trade_result}
                            all_trades.append(trade)
                            
                            status = "✅" if trade['pnl'] > 0 else "❌"
                            print(f"   {status} {signal['stock']}: {trade['exit_pct']:+.1f}% ({trade['exit_reason']}) = ₹{trade['pnl']:+,.0f}")
            
            print()
            current_date += timedelta(days=1)
        
        # Calculate results
        print("=" * 80)
        print("📊 BACKTEST RESULTS")
        print("=" * 80)
        print()
        
        if len(all_trades) == 0:
            print("❌ No trades found matching criteria")
            return
        
        df_trades = pd.DataFrame(all_trades)
        
        total_trades = len(df_trades)
        winning_trades = len(df_trades[df_trades['pnl'] > 0])
        losing_trades = len(df_trades[df_trades['pnl'] <= 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = df_trades['pnl'].sum()
        avg_win = df_trades[df_trades['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_loss = df_trades[df_trades['pnl'] <= 0]['pnl'].mean() if losing_trades > 0 else 0
        
        print(f"Total Trades:        {total_trades}")
        print(f"Winning Trades:      {winning_trades}")
        print(f"Losing Trades:       {losing_trades}")
        print(f"Win Rate:            {win_rate:.1f}%")
        print()
        print(f"Total P&L:           ₹{total_pnl:+,.0f}")
        print(f"Avg Win:             ₹{avg_win:+,.0f}")
        print(f"Avg Loss:            ₹{avg_loss:+,.0f}")
        print(f"Avg P&L per Trade:   ₹{total_pnl/total_trades:+,.0f}")
        print()
        
        # Best and worst trades
        best_trade = df_trades.loc[df_trades['pnl'].idxmax()]
        worst_trade = df_trades.loc[df_trades['pnl'].idxmin()]
        
        print(f"Best Trade:          {best_trade['stock']} on {best_trade['date']} = ₹{best_trade['pnl']:+,.0f}")
        print(f"Worst Trade:         {worst_trade['stock']} on {worst_trade['date']} = ₹{worst_trade['pnl']:+,.0f}")
        print()
        
        # Save results
        df_trades.to_csv('strategy_a_backtest_dec2025.csv', index=False)
        print("📄 Results saved to: strategy_a_backtest_dec2025.csv")
        print()

async def main():
    backtest = StrategyABacktest('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await backtest.connect()
    await backtest.backtest_december()
    await backtest.close()

if __name__ == "__main__":
    asyncio.run(main())
