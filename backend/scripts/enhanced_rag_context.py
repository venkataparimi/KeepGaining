"""
Enhanced RAG Context Builder
Provides rich market context for LLM analysis

Includes:
- Multi-day price history (5-10 days before trade)
- Market-wide indicators (NIFTY, VIX proxy)
- Sector performance
- Volume profile
- Intraday patterns
"""
import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta, time as dt_time
from typing import Dict, List, Any, Optional
import json


class EnhancedRAGContextBuilder:
    """Builds rich market context for LLM prompts"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_multi_day_history(self, stock: str, trade_date: date, days: int = 5) -> Dict:
        """Get price history for days before the trade"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT 
                    DATE(cd.timestamp) as trade_day,
                    MIN(cd.open) as day_open,
                    MAX(cd.high) as day_high,
                    MIN(cd.low) as day_low,
                    MAX(cd.close) as day_close,
                    SUM(cd.volume) as day_volume
                FROM candle_data cd
                JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                WHERE im.underlying = $1
                AND im.instrument_type = 'FUTURES'
                AND DATE(cd.timestamp) < $2
                AND DATE(cd.timestamp) >= $3
                GROUP BY DATE(cd.timestamp)
                ORDER BY DATE(cd.timestamp) DESC
            """
            
            start_date = trade_date - timedelta(days=days + 5)  # Extra buffer for weekends
            rows = await conn.fetch(query, stock, trade_date, start_date)
            
            if not rows:
                return {}
            
            history = []
            for row in rows[:days]:
                pct_change = 0
                if len(history) > 0:
                    prev_close = history[-1].get('close', row['day_close'])
                    pct_change = ((float(row['day_close']) - float(prev_close)) / float(prev_close)) * 100
                
                history.append({
                    'date': str(row['trade_day']),
                    'open': float(row['day_open']),
                    'high': float(row['day_high']),
                    'low': float(row['day_low']),
                    'close': float(row['day_close']),
                    'volume': int(row['day_volume']),
                    'change_pct': pct_change
                })
            
            # Calculate trend
            if len(history) >= 3:
                closes = [h['close'] for h in history]
                trend = "UPTREND" if closes[0] > closes[-1] else "DOWNTREND" if closes[0] < closes[-1] else "SIDEWAYS"
            else:
                trend = "UNKNOWN"
            
            return {
                'days': history,
                'trend': trend,
                'avg_daily_range': np.mean([h['high'] - h['low'] for h in history]) if history else 0,
                'avg_volume': np.mean([h['volume'] for h in history]) if history else 0
            }
    
    async def get_market_context(self, trade_date: date) -> Dict:
        """Get NIFTY/BANKNIFTY performance for market context"""
        async with self.pool.acquire() as conn:
            context = {}
            
            for index in ['NIFTY', 'BANKNIFTY']:
                query = """
                    SELECT 
                        MIN(cd.open) as day_open,
                        MAX(cd.high) as day_high,
                        MIN(cd.low) as day_low,
                        MAX(cd.close) as day_close
                    FROM candle_data cd
                    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                    WHERE im.underlying = $1
                    AND im.instrument_type = 'FUTURES'
                    AND DATE(cd.timestamp) = $2
                """
                
                row = await conn.fetchrow(query, index, trade_date)
                
                if row and row['day_open']:
                    change = ((float(row['day_close']) - float(row['day_open'])) / float(row['day_open'])) * 100
                    context[index] = {
                        'open': float(row['day_open']),
                        'high': float(row['day_high']),
                        'low': float(row['day_low']),
                        'close': float(row['day_close']),
                        'change_pct': change,
                        'sentiment': 'BULLISH' if change > 0.3 else 'BEARISH' if change < -0.3 else 'NEUTRAL'
                    }
            
            return context
    
    async def get_intraday_pattern(self, stock: str, trade_date: date, entry_time: dt_time) -> Dict:
        """Analyze intraday pattern up to entry time"""
        async with self.pool.acquire() as conn:
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
            
            rows = await conn.fetch(query, stock, trade_date)
            
            if not rows:
                return {}
            
            df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp']) + pd.Timedelta(hours=5, minutes=30)
            df['time'] = df['timestamp'].dt.time
            
            # Split into sessions
            morning = df[df['time'] < dt_time(12, 0)]
            lunch = df[(df['time'] >= dt_time(12, 0)) & (df['time'] < dt_time(13, 0))]
            afternoon = df[(df['time'] >= dt_time(13, 0)) & (df['time'] < entry_time)]
            
            pattern = {}
            
            if len(morning) > 0:
                morning_open = float(morning.iloc[0]['close'])
                morning_close = float(morning.iloc[-1]['close'])
                pattern['morning_session'] = {
                    'change_pct': ((morning_close - morning_open) / morning_open) * 100,
                    'high': float(morning['high'].max()),
                    'low': float(morning['low'].min()),
                    'volume': int(morning['volume'].sum())
                }
            
            if len(lunch) > 0:
                pattern['lunch_session'] = {
                    'volume': int(lunch['volume'].sum()),
                    'range': float(lunch['high'].max() - lunch['low'].min())
                }
            
            if len(afternoon) > 0:
                afternoon_open = float(afternoon.iloc[0]['close'])
                afternoon_close = float(afternoon.iloc[-1]['close'])
                pattern['pre_entry_session'] = {
                    'change_pct': ((afternoon_close - afternoon_open) / afternoon_open) * 100,
                    'momentum': 'UP' if afternoon_close > afternoon_open else 'DOWN'
                }
            
            # Overall pattern classification
            if pattern.get('morning_session', {}).get('change_pct', 0) > 0.5:
                pattern['pattern_type'] = 'MORNING_RALLY'
            elif pattern.get('morning_session', {}).get('change_pct', 0) < -0.5:
                pattern['pattern_type'] = 'MORNING_SELLOFF'
            else:
                pattern['pattern_type'] = 'CONSOLIDATION'
            
            return pattern
    
    async def get_volume_profile(self, stock: str, trade_date: date) -> Dict:
        """Analyze volume distribution"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT 
                    EXTRACT(HOUR FROM cd.timestamp + interval '5 hours 30 minutes') as hour,
                    SUM(cd.volume) as hourly_volume
                FROM candle_data cd
                JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                WHERE im.underlying = $1
                AND im.instrument_type = 'FUTURES'
                AND DATE(cd.timestamp) = $2
                GROUP BY EXTRACT(HOUR FROM cd.timestamp + interval '5 hours 30 minutes')
                ORDER BY hour
            """
            
            rows = await conn.fetch(query, stock, trade_date)
            
            if not rows:
                return {}
            
            hourly = {int(r['hour']): int(r['hourly_volume']) for r in rows}
            total_volume = sum(hourly.values())
            
            return {
                'hourly_distribution': hourly,
                'peak_hour': max(hourly, key=hourly.get) if hourly else None,
                'morning_volume_pct': sum(hourly.get(h, 0) for h in [9, 10, 11]) / total_volume * 100 if total_volume else 0,
                'afternoon_volume_pct': sum(hourly.get(h, 0) for h in [14, 15]) / total_volume * 100 if total_volume else 0
            }
    
    async def build_full_context(self, stock: str, trade_date: date, entry_time: dt_time = dt_time(14, 0)) -> Dict:
        """Build comprehensive context for LLM"""
        
        multi_day = await self.get_multi_day_history(stock, trade_date, days=5)
        market = await self.get_market_context(trade_date)
        intraday = await self.get_intraday_pattern(stock, trade_date, entry_time)
        volume = await self.get_volume_profile(stock, trade_date)
        
        return {
            'stock': stock,
            'trade_date': str(trade_date),
            'entry_time': str(entry_time),
            'multi_day_history': multi_day,
            'market_context': market,
            'intraday_pattern': intraday,
            'volume_profile': volume
        }
    
    def format_context_for_llm(self, context: Dict) -> str:
        """Format context as readable text for LLM"""
        lines = []
        
        lines.append(f"=== MARKET CONTEXT FOR {context['stock']} ON {context['trade_date']} ===")
        lines.append("")
        
        # Multi-day history
        if context.get('multi_day_history', {}).get('days'):
            lines.append("📅 RECENT HISTORY (Last 5 Days):")
            trend = context['multi_day_history'].get('trend', 'UNKNOWN')
            lines.append(f"   Overall Trend: {trend}")
            for day in context['multi_day_history']['days'][:5]:
                lines.append(f"   {day['date']}: Close ₹{day['close']:.2f}, Change {day['change_pct']:+.2f}%")
            lines.append("")
        
        # Market context
        if context.get('market_context'):
            lines.append("📊 MARKET CONTEXT:")
            for index, data in context['market_context'].items():
                lines.append(f"   {index}: {data['change_pct']:+.2f}% ({data['sentiment']})")
            lines.append("")
        
        # Intraday pattern
        if context.get('intraday_pattern'):
            lines.append("⏰ INTRADAY PATTERN:")
            pattern = context['intraday_pattern']
            if pattern.get('morning_session'):
                lines.append(f"   Morning: {pattern['morning_session']['change_pct']:+.2f}%")
            if pattern.get('pre_entry_session'):
                lines.append(f"   Pre-Entry (13:00-14:00): {pattern['pre_entry_session']['momentum']}")
            if pattern.get('pattern_type'):
                lines.append(f"   Pattern: {pattern['pattern_type']}")
            lines.append("")
        
        # Volume profile
        if context.get('volume_profile'):
            vol = context['volume_profile']
            lines.append("📈 VOLUME PROFILE:")
            if vol.get('peak_hour'):
                lines.append(f"   Peak Hour: {vol['peak_hour']}:00")
            lines.append(f"   Morning Volume: {vol.get('morning_volume_pct', 0):.1f}%")
            lines.append(f"   Afternoon Volume: {vol.get('afternoon_volume_pct', 0):.1f}%")
        
        return "\n".join(lines)


async def main():
    """Test the enhanced RAG context builder"""
    
    print("=" * 80)
    print("🔍 ENHANCED RAG CONTEXT BUILDER TEST")
    print("=" * 80)
    
    builder = EnhancedRAGContextBuilder('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await builder.connect()
    
    # Test with HINDZINC trade
    trade_date = date(2025, 12, 1)
    entry_time = dt_time(14, 0)
    
    for stock in ['HINDZINC', 'HEROMOTOCO']:
        print(f"\n📊 Building context for {stock}...")
        context = await builder.build_full_context(stock, trade_date, entry_time)
        
        print("\n" + builder.format_context_for_llm(context))
        print("-" * 80)
    
    await builder.close()
    print("\n✅ Complete!")


if __name__ == "__main__":
    asyncio.run(main())
