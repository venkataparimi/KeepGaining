"""
Analyze technical indicators for HINDZINC and HEROMOTOCO on Dec 1, 2025
Check RSI, MACD, Moving Averages, Bollinger Bands, etc. at 14:00
"""
import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dt_time

def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD"""
    exp1 = pd.Series(prices).ewm(span=fast, adjust=False).mean()
    exp2 = pd.Series(prices).ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """Calculate Bollinger Bands"""
    sma = np.mean(prices[-period:])
    std = np.std(prices[-period:])
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return upper, sma, lower

async def analyze_indicators():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    print("=" * 80)
    print("📊 TECHNICAL INDICATOR ANALYSIS - DECEMBER 1, 2025")
    print("=" * 80)
    print("\nAnalyzing indicators at 14:00 entry time")
    print()
    
    stocks = ['HINDZINC', 'HEROMOTOCO']
    
    for stock in stocks:
        print("\n" + "=" * 80)
        print(f"📈 {stock} - TECHNICAL INDICATORS")
        print("=" * 80)
        print()
        
        # Get full day data
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
            AND DATE(cd.timestamp) = '2025-12-01'
            ORDER BY cd.timestamp
        """
        
        data = await conn.fetch(query, stock)
        
        if not data:
            print(f"❌ No data for {stock}")
            continue
        
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp']) + pd.Timedelta(hours=5, minutes=30)
        df['time'] = df['timestamp'].dt.time
        
        # Find 14:00
        entry_time = dt_time(14, 0)
        entry_idx = df[df['time'] >= entry_time].index[0] if len(df[df['time'] >= entry_time]) > 0 else None
        
        if entry_idx is None:
            continue
        
        # Get data up to 14:00
        data_till_entry = df.loc[:entry_idx]
        prices = data_till_entry['close'].values.astype(float)
        entry_price = float(df.loc[entry_idx, 'close'])
        
        print(f"📊 PRICE AT 14:00: ₹{entry_price:.2f}")
        print()
        
        # 1. RSI
        if len(prices) >= 14:
            rsi = calculate_rsi(prices, 14)
            print(f"📈 RSI (14):")
            print(f"   Value: {rsi:.2f}")
            if rsi > 70:
                print(f"   Status: OVERBOUGHT ⚠️")
            elif rsi < 30:
                print(f"   Status: OVERSOLD 🟢")
            elif 45 <= rsi <= 55:
                print(f"   Status: NEUTRAL (Middle zone)")
            else:
                print(f"   Status: Normal range")
            print()
        
        # 2. Moving Averages
        if len(prices) >= 50:
            sma_9 = np.mean(prices[-9:])
            sma_20 = np.mean(prices[-20:])
            sma_50 = np.mean(prices[-50:])
            
            print(f"📊 MOVING AVERAGES:")
            print(f"   SMA 9:  ₹{sma_9:.2f}")
            print(f"   SMA 20: ₹{sma_20:.2f}")
            print(f"   SMA 50: ₹{sma_50:.2f}")
            print(f"   Price vs SMA 9:  {((entry_price - sma_9) / sma_9 * 100):+.2f}%")
            print(f"   Price vs SMA 20: {((entry_price - sma_20) / sma_20 * 100):+.2f}%")
            print(f"   Price vs SMA 50: {((entry_price - sma_50) / sma_50 * 100):+.2f}%")
            
            # Check crossovers
            if sma_9 > sma_20 > sma_50:
                print(f"   Trend: BULLISH (9>20>50) ✅")
            elif sma_9 < sma_20 < sma_50:
                print(f"   Trend: BEARISH (9<20<50) ⚠️")
            else:
                print(f"   Trend: MIXED")
            print()
        
        # 3. MACD
        if len(prices) >= 26:
            macd, signal, histogram = calculate_macd(prices)
            print(f"📈 MACD:")
            print(f"   MACD Line:   {macd:.2f}")
            print(f"   Signal Line: {signal:.2f}")
            print(f"   Histogram:   {histogram:.2f}")
            
            if macd > signal:
                print(f"   Status: BULLISH (MACD > Signal) ✅")
            else:
                print(f"   Status: BEARISH (MACD < Signal) ⚠️")
            
            if histogram > 0:
                print(f"   Momentum: POSITIVE")
            else:
                print(f"   Momentum: NEGATIVE")
            print()
        
        # 4. Bollinger Bands
        if len(prices) >= 20:
            upper, middle, lower = calculate_bollinger_bands(prices, 20, 2)
            bb_position = ((entry_price - lower) / (upper - lower)) * 100
            
            print(f"📊 BOLLINGER BANDS (20, 2):")
            print(f"   Upper:  ₹{upper:.2f}")
            print(f"   Middle: ₹{middle:.2f}")
            print(f"   Lower:  ₹{lower:.2f}")
            print(f"   Price Position: {bb_position:.1f}%")
            
            if entry_price > upper:
                print(f"   Status: ABOVE UPPER BAND (Overbought) ⚠️")
            elif entry_price < lower:
                print(f"   Status: BELOW LOWER BAND (Oversold) 🟢")
            elif 40 <= bb_position <= 60:
                print(f"   Status: MIDDLE ZONE (Neutral)")
            else:
                print(f"   Status: Normal range")
            print()
        
        # 5. Volume indicators
        avg_volume = np.mean(data_till_entry['volume'].values[-20:].astype(float))
        current_volume = float(df.loc[entry_idx, 'volume'])
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        print(f"📊 VOLUME:")
        print(f"   Current: {current_volume:,.0f}")
        print(f"   Avg (20): {avg_volume:,.0f}")
        print(f"   Ratio: {volume_ratio:.2f}x")
        if volume_ratio > 2.0:
            print(f"   Status: VERY HIGH VOLUME ✅")
        elif volume_ratio > 1.5:
            print(f"   Status: HIGH VOLUME ✅")
        elif volume_ratio < 0.5:
            print(f"   Status: LOW VOLUME ⚠️")
        else:
            print(f"   Status: NORMAL")
        print()
        
        # 6. Price action
        morning_df = data_till_entry
        morning_high = float(morning_df['high'].max())
        morning_low = float(morning_df['low'].min())
        
        print(f"📈 PRICE ACTION:")
        print(f"   Distance from High: {((entry_price - morning_high) / morning_high * 100):+.2f}%")
        print(f"   Distance from Low:  {((entry_price - morning_low) / morning_low * 100):+.2f}%")
        
        if entry_price > morning_high:
            print(f"   Status: BREAKOUT ABOVE HIGH ✅")
        elif entry_price < morning_low:
            print(f"   Status: BREAKDOWN BELOW LOW ⚠️")
        else:
            range_position = ((entry_price - morning_low) / (morning_high - morning_low)) * 100
            print(f"   Status: IN RANGE ({range_position:.1f}% position)")
        print()
    
    await conn.close()
    
    # Summary
    print("\n" + "=" * 80)
    print("🎯 INDICATOR-BASED ENTRY CRITERIA")
    print("=" * 80)
    print()
    print("Based on the indicator analysis, possible entry rules:")
    print()
    print("1️⃣  RSI-BASED:")
    print("   • RSI in neutral zone (45-55)")
    print("   • Not overbought/oversold")
    print("   • Room to move in either direction")
    print()
    print("2️⃣  MA-BASED:")
    print("   • Price above key MAs (bullish)")
    print("   • Or MA crossover happening")
    print("   • Trend alignment")
    print()
    print("3️⃣  MACD-BASED:")
    print("   • MACD crossing above signal")
    print("   • Or positive histogram")
    print("   • Momentum building")
    print()
    print("4️⃣  BOLLINGER-BASED:")
    print("   • Price in middle zone")
    print("   • Squeeze setup")
    print("   • Expansion expected")
    print()
    print("5️⃣  MULTI-INDICATOR:")
    print("   • Combination of above")
    print("   • Confluence of signals")
    print("   • Higher probability setup")
    print()

if __name__ == "__main__":
    asyncio.run(analyze_indicators())
