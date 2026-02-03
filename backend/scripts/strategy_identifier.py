"""
Generic Strategy Identifier - Works for any stock/option trade
Analyzes market data and identifies the strategy used
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta
import pandas as pd
import json

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

class StrategyIdentifier:
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(DB_URL)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_instrument_id(self, symbol, instrument_type='EQUITY'):
        """Get instrument ID for a symbol"""
        async with self.pool.acquire() as conn:
            inst = await conn.fetchrow("""
                SELECT instrument_id, trading_symbol 
                FROM instrument_master 
                WHERE trading_symbol = $1 AND instrument_type = $2
            """, symbol, instrument_type)
            return inst['instrument_id'] if inst else None
    
    async def get_market_data(self, inst_id, date):
        """Get candle data for a specific date"""
        async with self.pool.acquire() as conn:
            start = datetime.combine(date, datetime.min.time())
            end = datetime.combine(date, datetime.max.time())
            
            candles = await conn.fetch("""
                SELECT timestamp, open, high, low, close, volume
                FROM candle_data
                WHERE instrument_id = $1
                AND timestamp >= $2 AND timestamp <= $3
                AND timeframe = '1m'
                ORDER BY timestamp ASC
            """, inst_id, start, end)
            
            if candles:
                df = pd.DataFrame([dict(c) for c in candles])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                return df
            return None
    
    async def get_previous_day_data(self, inst_id, date):
        """Get previous trading day data"""
        async with self.pool.acquire() as conn:
            prev_date = date - timedelta(days=1)
            
            # Try up to 5 days back to find trading day
            for i in range(5):
                check_date = date - timedelta(days=i+1)
                start = datetime.combine(check_date, datetime.min.time())
                end = datetime.combine(check_date, datetime.max.time())
                
                candles = await conn.fetch("""
                    SELECT timestamp, close, high, low
                    FROM candle_data
                    WHERE instrument_id = $1
                    AND timestamp >= $2 AND timestamp <= $3
                    AND timeframe = '1m'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, inst_id, start, end)
                
                if candles:
                    return {
                        'prev_close': float(candles[0]['close']),
                        'prev_high': float(candles[0]['high']),
                        'prev_low': float(candles[0]['low'])
                    }
            return None
    
    async def analyze_trade(self, symbol, trade_date, strike=None, option_type=None, entry_price=None):
        """
        Analyze a trade and identify the strategy
        
        Args:
            symbol: Stock symbol (e.g., 'IEX', 'RELIANCE')
            trade_date: Date of trade (datetime.date)
            strike: Strike price for options (optional)
            option_type: 'CE' or 'PE' (optional)
            entry_price: Entry price/premium (optional)
        """
        
        print("=" * 80)
        print(f"STRATEGY IDENTIFIER - {symbol}")
        print("=" * 80)
        
        # Get instrument data
        inst_id = await self.get_instrument_id(symbol)
        if not inst_id:
            print(f"❌ {symbol} not found in database")
            return None
        
        # Get market data
        df = await self.get_market_data(inst_id, trade_date)
        if df is None or df.empty:
            print(f"❌ No data found for {trade_date}")
            return None
        
        # Get previous day data
        prev_data = await self.get_previous_day_data(inst_id, trade_date)
        
        # Calculate key metrics
        day_open = df['open'].iloc[0]
        day_high = df['high'].max()
        day_low = df['low'].min()
        day_close = df['close'].iloc[-1]
        total_volume = df['volume'].sum()
        
        # Price at 9:30 AM (first 15 mins)
        morning_df = df[df['timestamp'].dt.time <= datetime.strptime('09:45', '%H:%M').time()]
        price_930 = morning_df['close'].iloc[-1] if not morning_df.empty else day_open
        
        # Calculate movements
        intraday_range_pct = ((day_high - day_low) / day_low) * 100
        open_to_close_pct = ((day_close - day_open) / day_open) * 100
        
        # Print market summary
        print(f"\n📊 Market Data for {trade_date}:")
        print(f"   Open: ₹{day_open:.2f}")
        print(f"   High: ₹{day_high:.2f}")
        print(f"   Low: ₹{day_low:.2f}")
        print(f"   Close: ₹{day_close:.2f}")
        print(f"   Volume: {total_volume:,.0f}")
        print(f"   Price at 9:30 AM: ₹{price_930:.2f}")
        
        if prev_data:
            gap_pct = ((day_open - prev_data['prev_close']) / prev_data['prev_close']) * 100
            print(f"\n📈 Previous Day:")
            print(f"   Close: ₹{prev_data['prev_close']:.2f}")
            print(f"   Gap: {gap_pct:+.2f}%")
        
        print(f"\n📊 Intraday Movement:")
        print(f"   Range: {intraday_range_pct:.2f}%")
        print(f"   Open to Close: {open_to_close_pct:+.2f}%")
        
        # Identify strategy patterns
        strategy = self._identify_strategy_pattern(
            day_open, day_high, day_low, day_close, price_930,
            prev_data, strike, option_type, entry_price
        )
        
        print(f"\n🎯 IDENTIFIED STRATEGY: {strategy['name']}")
        print(f"   Type: {strategy['type']}")
        print(f"   Confidence: {strategy['confidence']}")
        print(f"\n📋 Strategy Details:")
        for detail in strategy['details']:
            print(f"   • {detail}")
        
        print(f"\n🔍 Entry Signals Detected:")
        for signal in strategy['signals']:
            print(f"   ✅ {signal}")
        
        if strategy['risk_reward']:
            print(f"\n💰 Risk/Reward Analysis:")
            for key, value in strategy['risk_reward'].items():
                print(f"   {key}: {value}")
        
        return strategy
    
    def _identify_strategy_pattern(self, day_open, day_high, day_low, day_close, 
                                   price_930, prev_data, strike, option_type, entry_price):
        """Identify the strategy pattern based on price action"""
        
        strategy = {
            'name': 'Unknown',
            'type': 'Unknown',
            'confidence': 'Low',
            'details': [],
            'signals': [],
            'risk_reward': {}
        }
        
        # Calculate key metrics
        intraday_range_pct = ((day_high - day_low) / day_low) * 100
        morning_momentum = ((price_930 - day_open) / day_open) * 100
        
        # Pattern 1: ATM Breakout (like IEX trade)
        if strike and abs(day_open - strike) / strike < 0.02:  # Within 2% of strike
            strategy['name'] = 'ATM Breakout Momentum'
            strategy['type'] = 'Directional - Bullish' if option_type == 'CE' else 'Directional - Bearish'
            strategy['confidence'] = 'High'
            strategy['details'] = [
                f'Entered at ATM (Strike: ₹{strike}, Spot: ₹{day_open:.2f})',
                f'Early momentum: {morning_momentum:+.2f}% in first 15 mins',
                f'Intraday range: {intraday_range_pct:.2f}%',
                'Maximum gamma exposure at ATM'
            ]
            strategy['signals'] = [
                'Price at or near strike',
                f'Early momentum ({morning_momentum:+.2f}%)',
                f'High volatility day ({intraday_range_pct:.2f}%)'
            ]
            
            if entry_price:
                breakeven = strike + entry_price if option_type == 'CE' else strike - entry_price
                strategy['risk_reward'] = {
                    'Entry Premium': f'₹{entry_price}',
                    'Break-even': f'₹{breakeven:.2f}',
                    'Max Loss': f'₹{entry_price} (100%)',
                    'Day High': f'₹{day_high:.2f}',
                    'Potential Profit': f'₹{max(0, day_high - strike - entry_price):.2f}'
                }
        
        # Pattern 2: Gap Up/Down Play
        elif prev_data:
            gap_pct = ((day_open - prev_data['prev_close']) / prev_data['prev_close']) * 100
            
            if abs(gap_pct) > 2:
                strategy['name'] = 'Gap and Go' if gap_pct > 0 else 'Gap Fill'
                strategy['type'] = 'Gap Trading'
                strategy['confidence'] = 'Medium'
                strategy['details'] = [
                    f'Gap: {gap_pct:+.2f}%',
                    f'Previous close: ₹{prev_data["prev_close"]:.2f}',
                    f'Open: ₹{day_open:.2f}',
                    'Trading the gap momentum'
                ]
                strategy['signals'] = [
                    f'Significant gap ({gap_pct:+.2f}%)',
                    f'Morning follow-through: {morning_momentum:+.2f}%'
                ]
        
        # Pattern 3: Breakout above previous high
        elif prev_data and day_high > prev_data['prev_high']:
            strategy['name'] = 'Breakout Above Previous High'
            strategy['type'] = 'Breakout Trading'
            strategy['confidence'] = 'High'
            strategy['details'] = [
                f'Previous high: ₹{prev_data["prev_high"]:.2f}',
                f'Today\'s high: ₹{day_high:.2f}',
                f'Breakout: {((day_high - prev_data["prev_high"]) / prev_data["prev_high"] * 100):.2f}%'
            ]
            strategy['signals'] = [
                'Price broke previous day high',
                f'Strong momentum ({intraday_range_pct:.2f}% range)'
            ]
        
        # Pattern 4: Strong Intraday Momentum
        elif intraday_range_pct > 3:
            strategy['name'] = 'Intraday Momentum Trade'
            strategy['type'] = 'Momentum Trading'
            strategy['confidence'] = 'Medium'
            strategy['details'] = [
                f'High volatility: {intraday_range_pct:.2f}%',
                f'Direction: {"Bullish" if day_close > day_open else "Bearish"}',
                'Riding strong intraday move'
            ]
            strategy['signals'] = [
                f'High intraday range ({intraday_range_pct:.2f}%)',
                f'Early momentum: {morning_momentum:+.2f}%'
            ]
        
        # Default: Directional bet
        else:
            strategy['name'] = 'Directional Trade'
            strategy['type'] = 'Bullish' if option_type == 'CE' else 'Bearish'
            strategy['confidence'] = 'Low'
            strategy['details'] = [
                'Standard directional bet',
                f'Intraday move: {open_to_close_pct:+.2f}%'
            ]
        
        return strategy

async def main():
    """Example usage"""
    identifier = StrategyIdentifier()
    await identifier.connect()
    
    # Analyze IEX trade
    strategy = await identifier.analyze_trade(
        symbol='IEX',
        trade_date=datetime(2025, 12, 1).date(),
        strike=140,
        option_type='CE',
        entry_price=9
    )
    
    # Save strategy to JSON
    if strategy:
        with open('identified_strategy.json', 'w') as f:
            json.dump(strategy, f, indent=2)
        print(f"\n💾 Strategy saved to identified_strategy.json")
    
    await identifier.close()

if __name__ == "__main__":
    asyncio.run(main())
