import asyncio
import asyncpg
import pandas as pd
from datetime import datetime, date

async def analyze_trade():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    symbol = 'LAURUSLABS'
    trade_date = date(2025, 12, 9)
    
    print("=" * 100)
    print(f"FORENSIC ANALYSIS: {symbol} on {trade_date}")
    print("=" * 100)
    
    # Get the trade details from strategy_trades
    trade = await pool.fetchrow('''
        SELECT * FROM strategy_trades
        WHERE symbol = $1 AND trade_date = $2
    ''', symbol, trade_date)
    
    if trade:
        print(f"\nTrade Details:")
        print(f"  Option: {trade['option_type']} {trade['strike_price']}")
        print(f"  Entry Time: {trade['entry_time']}")
        print(f"  Exit Time: {trade['exit_time']}")
        print(f"  Exit Reason: {trade['exit_reason']}")
        print(f"  Entry Premium: Rs {trade['entry_premium']:.2f}")
        print(f"  Exit Premium: Rs {trade['exit_premium']:.2f}")
        print(f"  P&L: {trade['pnl_pct']:.1f}% (Rs {trade['pnl_amount']:,.0f})")
        print(f"  Spot at Entry: Rs {trade['spot_at_entry']:.2f}")
        print(f"  Spot at Exit: Rs {trade['spot_at_exit']:.2f}")
        print(f"  Morning Momentum: {trade['momentum_pct']:.2f}%")
    
    # Get equity candle data for the whole day
    equity_candles = await pool.fetch('''
        SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume
        FROM candle_data c
        JOIN instrument_master im ON c.instrument_id = im.instrument_id
        WHERE im.trading_symbol = $1 
          AND im.instrument_type = 'EQUITY'
          AND DATE(c.timestamp) = $2
          AND c.timestamp::time >= '03:45:00'  -- 9:15 IST
          AND c.timestamp::time <= '09:30:00'  -- 3:00 PM IST
        ORDER BY c.timestamp
    ''', symbol, trade_date)
    
    if equity_candles:
        df = pd.DataFrame([dict(r) for r in equity_candles])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Calculate IST time
        df['ist_time'] = df['timestamp'].dt.time
        
        print("\n" + "=" * 100)
        print("EQUITY PRICE MOVEMENT (Every 15 minutes):")
        print("=" * 100)
        
        # Show key timepoints
        key_times = ['03:45:00', '04:00:00', '04:15:00', '04:30:00', '05:00:00', 
                     '06:00:00', '07:00:00', '08:00:00', '09:00:00', '09:30:00']
        
        for kt in key_times:
            candle = df[df['timestamp'].dt.time == pd.to_datetime(kt).time()]
            if not candle.empty:
                row = candle.iloc[0]
                hour_ist = (pd.to_datetime(kt).hour + 5) + (pd.to_datetime(kt).minute + 30) // 60
                min_ist = (pd.to_datetime(kt).minute + 30) % 60
                change_from_open = ((row['close'] - df.iloc[0]['open']) / df.iloc[0]['open']) * 100
                print(f"  {hour_ist:02d}:{min_ist:02d} IST | Open: {row['open']:7.2f} | High: {row['high']:7.2f} | Low: {row['low']:7.2f} | Close: {row['close']:7.2f} | Change: {change_from_open:+6.2f}%")
        
        # Calculate volatility metrics
        day_open = df.iloc[0]['open']
        morning_930 = df[df['timestamp'].dt.time == pd.to_datetime('04:00:00').time()].iloc[0]['close'] if not df[df['timestamp'].dt.time == pd.to_datetime('04:00:00').time()].empty else None
        
        if morning_930:
            morning_momentum = ((morning_930 - day_open) / day_open) * 100
            print(f"\n  📊 Morning Momentum (9:15 to 9:30): {morning_momentum:+.2f}%")
            
            # What happened after 9:30?
            post_930 = df[df['timestamp'] > df[df['timestamp'].dt.time == pd.to_datetime('04:00:00').time()].iloc[0]['timestamp']]
            if not post_930.empty:
                max_gain = ((post_930['high'].max() - morning_930) / morning_930) * 100
                max_drop = ((post_930['low'].min() - morning_930) / morning_930) * 100
                print(f"  📈 Max Gain After Entry: {max_gain:+.2f}%")
                print(f"  📉 Max Drop After Entry: {max_drop:+.2f}%")
    
    # Get option premium data
    print("\n" + "=" * 100)
    print("OPTION PREMIUM MOVEMENT:")
    print("=" * 100)
    
    if trade:
        option_candles = await pool.fetch('''
            SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume
            FROM candle_data c
            JOIN instrument_master im ON c.instrument_id = im.instrument_id
            JOIN option_master om ON im.instrument_id = om.instrument_id
            WHERE im.underlying = $1
              AND im.instrument_type = $2
              AND om.strike_price = $3
              AND DATE(c.timestamp) = $4
              AND c.timestamp >= $5
            ORDER BY c.timestamp
            LIMIT 20
        ''', symbol, trade['option_type'], trade['strike_price'], trade_date, trade['entry_time'])
        
        if option_candles:
            print(f"\nFirst 20 candles after entry ({trade['entry_time']}):")
            for i, oc in enumerate(option_candles):
                pnl = ((oc['close'] - trade['entry_premium']) / trade['entry_premium']) * 100
                marker = "❌ STOP LOSS!" if pnl <= -40 else ("✅ TARGET!" if pnl >= 50 else "")
                print(f"  {oc['timestamp']} | Close: {oc['close']:7.2f} | P&L: {pnl:+6.2f}% {marker}")
    
    await pool.close()

asyncio.run(analyze_trade())
