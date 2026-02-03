"""
Fresh Technical Indicator Analysis
Analyze trades with MANY different indicators to find new patterns

Instead of testing hypotheses, let the data reveal what's special about these trades.
"""
import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dt_time, timedelta
from typing import Dict, List, Optional
import json

class ComprehensiveTechnicalAnalyzer:
    """Analyze trades with comprehensive technical indicators"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    # === MOMENTUM INDICATORS ===
    
    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return None
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def calculate_stochastic(self, high, low, close, k_period=14, d_period=3):
        """Stochastic Oscillator %K and %D"""
        if len(close) < k_period:
            return None, None
        
        lowest_low = pd.Series(low).rolling(k_period).min()
        highest_high = pd.Series(high).rolling(k_period).max()
        
        k = 100 * (close[-1] - lowest_low.iloc[-1]) / (highest_high.iloc[-1] - lowest_low.iloc[-1]) if (highest_high.iloc[-1] - lowest_low.iloc[-1]) > 0 else 50
        d = pd.Series(k).rolling(d_period).mean().iloc[-1] if len([k]) >= d_period else k
        
        return k, d
    
    def calculate_williams_r(self, high, low, close, period=14):
        """Williams %R"""
        if len(close) < period:
            return None
        
        highest_high = max(high[-period:])
        lowest_low = min(low[-period:])
        
        if highest_high == lowest_low:
            return -50
        
        return -100 * (highest_high - close[-1]) / (highest_high - lowest_low)
    
    def calculate_momentum(self, prices, period=10):
        """Price momentum"""
        if len(prices) < period + 1:
            return None
        return ((prices[-1] - prices[-period-1]) / prices[-period-1]) * 100
    
    def calculate_roc(self, prices, period=10):
        """Rate of Change"""
        if len(prices) < period + 1:
            return None
        return ((prices[-1] / prices[-period-1]) - 1) * 100
    
    # === TREND INDICATORS ===
    
    def calculate_macd(self, prices):
        if len(prices) < 26:
            return None, None, None
        exp1 = pd.Series(prices).ewm(span=12, adjust=False).mean()
        exp2 = pd.Series(prices).ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        return float(macd.iloc[-1]), float(signal.iloc[-1]), float(histogram.iloc[-1])
    
    def calculate_adx(self, high, low, close, period=14):
        """Average Directional Index"""
        if len(close) < period + 1:
            return None, None, None
        
        plus_dm = np.diff(high)
        minus_dm = -np.diff(low)
        
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        
        tr = np.maximum(np.diff(high) - np.diff(low), np.abs(np.diff(high) - close[:-1]))
        tr = np.maximum(tr, np.abs(np.diff(low) - close[:-1]))
        
        atr = pd.Series(tr).rolling(period).mean().iloc[-1]
        plus_di = 100 * pd.Series(plus_dm).rolling(period).mean().iloc[-1] / atr if atr > 0 else 0
        minus_di = 100 * pd.Series(minus_dm).rolling(period).mean().iloc[-1] / atr if atr > 0 else 0
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        
        return dx, plus_di, minus_di
    
    def calculate_ema_crossover(self, prices):
        """EMA crossover status"""
        if len(prices) < 20:
            return None
        
        ema9 = pd.Series(prices).ewm(span=9, adjust=False).mean().iloc[-1]
        ema20 = pd.Series(prices).ewm(span=20, adjust=False).mean().iloc[-1]
        
        return {
            'ema9': ema9,
            'ema20': ema20,
            'crossover': 'BULLISH' if ema9 > ema20 else 'BEARISH',
            'distance_pct': ((ema9 - ema20) / ema20) * 100
        }
    
    # === VOLATILITY INDICATORS ===
    
    def calculate_bollinger_bands(self, prices, period=20, std_dev=2):
        if len(prices) < period:
            return None, None, None, None
        
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        upper = sma + (std_dev * std)
        lower = sma - (std_dev * std)
        
        current = prices[-1]
        position = ((current - lower) / (upper - lower)) * 100 if (upper - lower) > 0 else 50
        
        return {
            'upper': upper,
            'middle': sma,
            'lower': lower,
            'position': position,
            'bandwidth': ((upper - lower) / sma) * 100
        }
    
    def calculate_atr(self, high, low, close, period=14):
        """Average True Range"""
        if len(close) < period + 1:
            return None
        
        tr = []
        for i in range(1, len(close)):
            tr.append(max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            ))
        
        return np.mean(tr[-period:])
    
    def calculate_keltner_channel(self, high, low, close, period=20, atr_mult=2):
        """Keltner Channel"""
        if len(close) < period:
            return None
        
        ema = pd.Series(close).ewm(span=period, adjust=False).mean().iloc[-1]
        atr = self.calculate_atr(high, low, close, period)
        
        if atr is None:
            return None
        
        upper = ema + (atr_mult * atr)
        lower = ema - (atr_mult * atr)
        
        position = ((close[-1] - lower) / (upper - lower)) * 100 if (upper - lower) > 0 else 50
        
        return {
            'upper': upper,
            'middle': ema,
            'lower': lower,
            'position': position
        }
    
    # === VOLUME INDICATORS ===
    
    def calculate_obv_trend(self, close, volume, period=10):
        """On Balance Volume trend"""
        if len(close) < period + 1:
            return None
        
        obv = [0]
        for i in range(1, len(close)):
            if close[i] > close[i-1]:
                obv.append(obv[-1] + volume[i])
            elif close[i] < close[i-1]:
                obv.append(obv[-1] - volume[i])
            else:
                obv.append(obv[-1])
        
        obv_change = obv[-1] - obv[-period-1] if len(obv) > period else 0
        
        return {
            'obv': obv[-1],
            'trend': 'UP' if obv_change > 0 else 'DOWN',
            'change': obv_change
        }
    
    def calculate_vwap(self, high, low, close, volume):
        """VWAP"""
        if len(close) < 1:
            return None
        
        typical_price = (high + low + close) / 3
        vwap = np.sum(typical_price * volume) / np.sum(volume) if np.sum(volume) > 0 else close[-1]
        
        return {
            'vwap': vwap,
            'price_vs_vwap': ((close[-1] - vwap) / vwap) * 100,
            'above_vwap': close[-1] > vwap
        }
    
    # === PRICE PATTERN INDICATORS ===
    
    def calculate_candle_patterns(self, open_prices, high, low, close):
        """Basic candle pattern detection"""
        if len(close) < 3:
            return None
        
        body = close[-1] - open_prices[-1]
        upper_wick = high[-1] - max(open_prices[-1], close[-1])
        lower_wick = min(open_prices[-1], close[-1]) - low[-1]
        range_size = high[-1] - low[-1]
        
        patterns = []
        
        # Doji
        if abs(body) < range_size * 0.1:
            patterns.append('DOJI')
        
        # Hammer (bullish)
        if lower_wick > body * 2 and upper_wick < body * 0.5:
            patterns.append('HAMMER')
        
        # Shooting Star (bearish)
        if upper_wick > abs(body) * 2 and lower_wick < abs(body) * 0.5:
            patterns.append('SHOOTING_STAR')
        
        # Strong bullish
        if body > 0 and body > range_size * 0.7:
            patterns.append('STRONG_BULLISH')
        
        # Strong bearish
        if body < 0 and abs(body) > range_size * 0.7:
            patterns.append('STRONG_BEARISH')
        
        return {
            'patterns': patterns,
            'body_pct': (body / range_size * 100) if range_size > 0 else 0,
            'is_bullish': body > 0
        }
    
    def calculate_support_resistance(self, high, low, close, period=20):
        """Simple S/R levels"""
        if len(close) < period:
            return None
        
        recent_high = max(high[-period:])
        recent_low = min(low[-period:])
        
        distance_from_high = ((recent_high - close[-1]) / close[-1]) * 100
        distance_from_low = ((close[-1] - recent_low) / close[-1]) * 100
        
        return {
            'resistance': recent_high,
            'support': recent_low,
            'distance_from_resistance': distance_from_high,
            'distance_from_support': distance_from_low,
            'range_position': ((close[-1] - recent_low) / (recent_high - recent_low)) * 100 if (recent_high - recent_low) > 0 else 50
        }
    
    async def analyze_trade(self, stock: str, trade_date: date, entry_time: dt_time = dt_time(14, 0)):
        """Comprehensive analysis of a trade"""
        
        async with self.pool.acquire() as conn:
            query = """
                SELECT cd.timestamp, cd.open, cd.high, cd.low, cd.close, cd.volume
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
            
            # Find entry candle
            entry_candles = df[df['time'] >= entry_time]
            if len(entry_candles) == 0:
                return None
            
            entry_idx = entry_candles.index[0]
            data_till_entry = df.loc[:entry_idx]
            
            # Extract arrays
            open_arr = data_till_entry['open'].values.astype(float)
            high_arr = data_till_entry['high'].values.astype(float)
            low_arr = data_till_entry['low'].values.astype(float)
            close_arr = data_till_entry['close'].values.astype(float)
            volume_arr = data_till_entry['volume'].values.astype(float)
            
            # Calculate all indicators
            result = {
                'stock': stock,
                'date': str(trade_date),
                'entry_time': str(entry_time),
                'entry_price': float(close_arr[-1]),
            }
            
            # Momentum
            result['rsi_14'] = self.calculate_rsi(close_arr, 14)
            result['rsi_7'] = self.calculate_rsi(close_arr, 7)
            result['stoch_k'], result['stoch_d'] = self.calculate_stochastic(high_arr, low_arr, close_arr)
            result['williams_r'] = self.calculate_williams_r(high_arr, low_arr, close_arr)
            result['momentum_10'] = self.calculate_momentum(close_arr, 10)
            result['roc_10'] = self.calculate_roc(close_arr, 10)
            
            # Trend
            macd, signal, hist = self.calculate_macd(close_arr)
            result['macd'] = macd
            result['macd_signal'] = signal
            result['macd_histogram'] = hist
            result['macd_bullish'] = hist > 0 if hist else None
            
            adx, plus_di, minus_di = self.calculate_adx(high_arr, low_arr, close_arr)
            result['adx'] = adx
            result['plus_di'] = plus_di
            result['minus_di'] = minus_di
            result['di_bullish'] = plus_di > minus_di if plus_di and minus_di else None
            
            ema_cross = self.calculate_ema_crossover(close_arr)
            if ema_cross:
                result['ema_crossover'] = ema_cross['crossover']
                result['ema_distance'] = ema_cross['distance_pct']
            
            # Volatility
            bb = self.calculate_bollinger_bands(close_arr)
            if bb:
                result['bb_position'] = bb['position']
                result['bb_bandwidth'] = bb['bandwidth']
            
            result['atr_14'] = self.calculate_atr(high_arr, low_arr, close_arr, 14)
            
            keltner = self.calculate_keltner_channel(high_arr, low_arr, close_arr)
            if keltner:
                result['keltner_position'] = keltner['position']
            
            # Volume
            obv = self.calculate_obv_trend(close_arr, volume_arr)
            if obv:
                result['obv_trend'] = obv['trend']
            
            vwap = self.calculate_vwap(high_arr, low_arr, close_arr, volume_arr)
            if vwap:
                result['above_vwap'] = vwap['above_vwap']
                result['vwap_distance'] = vwap['price_vs_vwap']
            
            # Patterns
            candle = self.calculate_candle_patterns(open_arr, high_arr, low_arr, close_arr)
            if candle:
                result['candle_patterns'] = candle['patterns']
                result['candle_bullish'] = candle['is_bullish']
            
            sr = self.calculate_support_resistance(high_arr, low_arr, close_arr)
            if sr:
                result['sr_position'] = sr['range_position']
                result['distance_from_resistance'] = sr['distance_from_resistance']
                result['distance_from_support'] = sr['distance_from_support']
            
            # Volume ratio
            if len(volume_arr) >= 20:
                result['volume_ratio'] = float(volume_arr[-1] / np.mean(volume_arr[-20:]))
            
            return result


async def main():
    """Analyze a few sample trades with comprehensive indicators"""
    
    # Stock name mapping
    stock_mapping = {
        'IEX': 'IEX',
        'Hind Zinc': 'HINDZINC',
        'Hero Motors': 'HEROMOTOCO',
        'TVS Motor': 'TVSMOTOR',
        'Vedl': 'VEDL',
        'Idea': 'IDEA',
        'Delhivery': 'DELHIVERY',
        'Angel One': 'ANGELONE',
    }
    
    # Select diverse trades for analysis
    sample_trades = [
        # CE trades
        {'date': '2025-12-01', 'stock': 'HINDZINC', 'type': 'CE'},
        {'date': '2025-12-01', 'stock': 'HEROMOTOCO', 'type': 'CE'},
        {'date': '2025-12-15', 'stock': 'VEDL', 'type': 'CE'},
        # PE trades  
        {'date': '2025-12-03', 'stock': 'DELHIVERY', 'type': 'PE'},
        {'date': '2025-12-03', 'stock': 'ANGELONE', 'type': 'PE'},
    ]
    
    print("=" * 100)
    print("🔬 COMPREHENSIVE TECHNICAL INDICATOR ANALYSIS")
    print("=" * 100)
    print("\nAnalyzing trades with 25+ indicators to find patterns...")
    
    analyzer = ComprehensiveTechnicalAnalyzer('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await analyzer.connect()
    
    results = []
    
    for trade in sample_trades:
        trade_date = datetime.strptime(trade['date'], '%Y-%m-%d').date()
        
        print(f"\n📊 Analyzing {trade['stock']} on {trade['date']} ({trade['type']})...")
        
        analysis = await analyzer.analyze_trade(trade['stock'], trade_date)
        
        if analysis:
            analysis['option_type'] = trade['type']
            results.append(analysis)
            
            print(f"\n   === MOMENTUM ===")
            print(f"   RSI(14): {analysis.get('rsi_14', 'N/A'):.1f}" if analysis.get('rsi_14') else "   RSI(14): N/A")
            print(f"   RSI(7): {analysis.get('rsi_7', 'N/A'):.1f}" if analysis.get('rsi_7') else "   RSI(7): N/A")
            print(f"   Stochastic %K: {analysis.get('stoch_k', 'N/A'):.1f}" if analysis.get('stoch_k') else "   Stochastic: N/A")
            print(f"   Williams %R: {analysis.get('williams_r', 'N/A'):.1f}" if analysis.get('williams_r') else "   Williams %R: N/A")
            print(f"   Momentum(10): {analysis.get('momentum_10', 'N/A'):.2f}%" if analysis.get('momentum_10') else "   Momentum: N/A")
            
            print(f"\n   === TREND ===")
            print(f"   MACD Bullish: {analysis.get('macd_bullish')}")
            print(f"   +DI > -DI: {analysis.get('di_bullish')}")
            print(f"   EMA Crossover: {analysis.get('ema_crossover')}")
            print(f"   ADX: {analysis.get('adx', 'N/A'):.1f}" if analysis.get('adx') else "   ADX: N/A")
            
            print(f"\n   === VOLATILITY ===")
            print(f"   Bollinger Position: {analysis.get('bb_position', 'N/A'):.1f}%" if analysis.get('bb_position') else "   BB: N/A")
            print(f"   Keltner Position: {analysis.get('keltner_position', 'N/A'):.1f}%" if analysis.get('keltner_position') else "   Keltner: N/A")
            
            print(f"\n   === VOLUME ===")
            print(f"   OBV Trend: {analysis.get('obv_trend')}")
            print(f"   Above VWAP: {analysis.get('above_vwap')}")
            print(f"   Volume Ratio: {analysis.get('volume_ratio', 'N/A'):.2f}x" if analysis.get('volume_ratio') else "   Volume: N/A")
            
            print(f"\n   === PATTERNS ===")
            print(f"   Candle Patterns: {analysis.get('candle_patterns', [])}")
            print(f"   S/R Position: {analysis.get('sr_position', 'N/A'):.1f}%" if analysis.get('sr_position') else "   SR: N/A")
        else:
            print(f"   ⚠️ No data available")
    
    await analyzer.close()
    
    # Find common patterns
    if results:
        print("\n" + "=" * 100)
        print("🎯 COMMON PATTERNS ACROSS TRADES")
        print("=" * 100)
        
        ce_trades = [r for r in results if r['option_type'] == 'CE']
        pe_trades = [r for r in results if r['option_type'] == 'PE']
        
        if ce_trades:
            print(f"\n📈 CE TRADES ({len(ce_trades)}):")
            avg_rsi = np.mean([r['rsi_14'] for r in ce_trades if r.get('rsi_14')])
            macd_bullish = sum(1 for r in ce_trades if r.get('macd_bullish'))
            above_vwap = sum(1 for r in ce_trades if r.get('above_vwap'))
            
            print(f"   Avg RSI: {avg_rsi:.1f}")
            print(f"   MACD Bullish: {macd_bullish}/{len(ce_trades)}")
            print(f"   Above VWAP: {above_vwap}/{len(ce_trades)}")
        
        if pe_trades:
            print(f"\n📉 PE TRADES ({len(pe_trades)}):")
            avg_rsi = np.mean([r['rsi_14'] for r in pe_trades if r.get('rsi_14')])
            macd_bullish = sum(1 for r in pe_trades if r.get('macd_bullish'))
            above_vwap = sum(1 for r in pe_trades if r.get('above_vwap'))
            
            print(f"   Avg RSI: {avg_rsi:.1f}")
            print(f"   MACD Bullish: {macd_bullish}/{len(pe_trades)}")
            print(f"   Above VWAP: {above_vwap}/{len(pe_trades)}")
        
        # Save results
        with open('backend/data/comprehensive_indicator_analysis.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Saved to: backend/data/comprehensive_indicator_analysis.json")
    
    print("\n✅ Analysis Complete!")


if __name__ == "__main__":
    asyncio.run(main())
