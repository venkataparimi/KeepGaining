#!/usr/bin/env python3
"""
Analyze Open Interest and Max Pain during Gap-Up trades

Check:
1. ATM OI levels during gap-up
2. Max Pain vs current price
3. Put-Call Ratio at ATM
4. Evidence of call seller suppression
"""

import asyncio
import asyncpg
from datetime import datetime, date, timedelta
import pandas as pd

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

async def analyze_oi_on_gapup(symbol: str, trade_date: date, gap_price: float):
    """Analyze OI structure during gap-up"""
    
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Get option chain at 9:15 AM (first candle after gap)
        gap_time = datetime.combine(trade_date, datetime.min.time()).replace(hour=9, minute=15)
        
        # Find ATM strike (closest to gap price)
        atm_strike = round(gap_price / 50) * 50  # Round to nearest 50
        
        # Get OI data for strikes around ATM
        strikes = [atm_strike - 100, atm_strike - 50, atm_strike, atm_strike + 50, atm_strike + 100]
        
        print(f"\n{'='*100}")
        print(f"OI ANALYSIS: {symbol} on {trade_date}")
        print(f"Gap Price: Rs {gap_price:.2f} | ATM Strike: {atm_strike}")
        print(f"{'='*100}")
        
        # Get option data for these strikes
        option_data = await conn.fetch("""
            SELECT 
                om.strike,
                om.option_type,
                om.trading_symbol,
                od.timestamp,
                od.open_interest,
                od.volume,
                od.close as premium,
                od.implied_volatility
            FROM option_metadata om
            JOIN option_data od ON om.option_id = od.option_id
            JOIN instrument_master im ON om.instrument_id = im.instrument_id
            WHERE im.trading_symbol = $1
              AND DATE(od.timestamp) = $2
              AND om.strike = ANY($3::numeric[])
              AND od.timestamp::time >= '03:45:00'
              AND od.timestamp::time <= '04:00:00'
            ORDER BY om.strike, om.option_type, od.timestamp
        """, symbol, trade_date, strikes)
        
        if not option_data:
            print(f"No option data found for {symbol} on {trade_date}")
            return None
        
        # Organize by strike
        strike_data = {}
        for row in option_data:
            strike = float(row['strike'])
            if strike not in strike_data:
                strike_data[strike] = {'CE': [], 'PE': []}
            strike_data[strike][row['option_type']].append(dict(row))
        
        # Calculate Put-Call Ratio and analyze
        print(f"\n{'Strike':<10} {'Type':<6} {'OI':<12} {'Volume':<10} {'Premium':<10} {'IV':<8}")
        print(f"{'-'*100}")
        
        total_ce_oi = 0
        total_pe_oi = 0
        atm_ce_oi = 0
        atm_pe_oi = 0
        
        for strike in sorted(strike_data.keys()):
            for opt_type in ['CE', 'PE']:
                if strike_data[strike][opt_type]:
                    latest = strike_data[strike][opt_type][-1]  # Latest data point
                    oi = latest['open_interest']
                    volume = latest['volume']
                    premium = latest['premium']
                    iv = latest['implied_volatility']
                    
                    marker = " <-- ATM" if strike == atm_strike else ""
                    print(f"{strike:<10.0f} {opt_type:<6} {oi:<12,} {volume:<10,} {premium:<10.2f} {iv:<8.2f}{marker}")
                    
                    if opt_type == 'CE':
                        total_ce_oi += oi
                        if strike == atm_strike:
                            atm_ce_oi = oi
                    else:
                        total_pe_oi += oi
                        if strike == atm_strike:
                            atm_pe_oi = oi
        
        # Calculate ratios
        pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
        atm_pcr = atm_pe_oi / atm_ce_oi if atm_ce_oi > 0 else 0
        
        print(f"\n{'-'*100}")
        print(f"PUT-CALL RATIO ANALYSIS:")
        print(f"  Overall PCR: {pcr:.2f}")
        print(f"  ATM PCR: {atm_pcr:.2f}")
        print(f"  Total CE OI: {total_ce_oi:,}")
        print(f"  Total PE OI: {total_pe_oi:,}")
        print(f"  ATM CE OI: {atm_ce_oi:,}")
        print(f"  ATM PE OI: {atm_pe_oi:,}")
        
        # Calculate Max Pain
        max_pain = await calculate_max_pain(conn, symbol, trade_date, strikes)
        if max_pain:
            distance_from_max_pain = ((gap_price - max_pain) / max_pain) * 100
            print(f"\nMAX PAIN ANALYSIS:")
            print(f"  Max Pain: Rs {max_pain:.0f}")
            print(f"  Current Price: Rs {gap_price:.2f}")
            print(f"  Distance: {distance_from_max_pain:+.2f}%")
            
            if distance_from_max_pain > 2:
                print(f"  ⚠️  Price is {distance_from_max_pain:.1f}% ABOVE max pain!")
                print(f"  ⚠️  Call sellers have incentive to suppress premiums")
        
        # Check for unusual call writing
        if atm_ce_oi > atm_pe_oi * 1.5:
            print(f"\n🚨 HEAVY CALL WRITING DETECTED!")
            print(f"   ATM CE OI ({atm_ce_oi:,}) is {atm_ce_oi/atm_pe_oi:.1f}x ATM PE OI")
            print(f"   This suggests call sellers are defending the strike")
        
        return {
            'pcr': pcr,
            'atm_pcr': atm_pcr,
            'max_pain': max_pain,
            'distance_from_max_pain': distance_from_max_pain if max_pain else None,
            'atm_ce_oi': atm_ce_oi,
            'atm_pe_oi': atm_pe_oi
        }
        
    finally:
        await conn.close()

async def calculate_max_pain(conn, symbol: str, trade_date: date, strikes: list) -> float:
    """Calculate max pain level"""
    
    # Get OI for all strikes
    oi_data = await conn.fetch("""
        SELECT 
            om.strike,
            om.option_type,
            MAX(od.open_interest) as oi
        FROM option_metadata om
        JOIN option_data od ON om.option_id = od.option_id
        JOIN instrument_master im ON om.instrument_id = im.instrument_id
        WHERE im.trading_symbol = $1
          AND DATE(od.timestamp) = $2
          AND od.timestamp::time >= '03:45:00'
          AND od.timestamp::time <= '04:00:00'
        GROUP BY om.strike, om.option_type
    """, symbol, trade_date)
    
    if not oi_data:
        return None
    
    # Build OI structure
    oi_by_strike = {}
    all_strikes = set()
    
    for row in oi_data:
        strike = float(row['strike'])
        all_strikes.add(strike)
        if strike not in oi_by_strike:
            oi_by_strike[strike] = {'CE': 0, 'PE': 0}
        oi_by_strike[strike][row['option_type']] = row['oi']
    
    # Calculate pain for each strike
    min_pain = float('inf')
    max_pain_strike = None
    
    for test_strike in sorted(all_strikes):
        total_pain = 0
        
        for strike in all_strikes:
            # Call pain: (test_strike - strike) * CE_OI if test_strike > strike
            if test_strike > strike:
                total_pain += (test_strike - strike) * oi_by_strike.get(strike, {}).get('CE', 0)
            
            # Put pain: (strike - test_strike) * PE_OI if test_strike < strike
            if test_strike < strike:
                total_pain += (strike - test_strike) * oi_by_strike.get(strike, {}).get('PE', 0)
        
        if total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = test_strike
    
    return max_pain_strike

async def main():
    # Analyze the gap-up trades
    trades = [
        ('LTTS', date(2025, 12, 1), 4453),
        ('HINDZINC', date(2025, 12, 11), 519),
        ('KEC', date(2025, 12, 15), 719),  # Biggest gap
        ('PVRINOX', date(2025, 12, 15), 1090),
    ]
    
    for symbol, trade_date, gap_price in trades:
        await analyze_oi_on_gapup(symbol, trade_date, gap_price)
        print("\n")

if __name__ == "__main__":
    asyncio.run(main())
