"""
Multi-Strategy Discovery Engine
Approach: Stock-level analysis → Option trade trigger

Key Principles:
1. Multiple strategies may exist - don't force one
2. Analyze STOCK first, then decide CE/PE
3. Cluster trades that share similar characteristics
4. Each cluster = potential strategy
"""
import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dt_time, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import json
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')


class StockLevelAnalyzer:
    """Analyze stocks to find trading opportunities, then decide option type"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def analyze_stock(self, stock: str, trade_date: date, entry_time: dt_time = dt_time(14, 0)) -> Optional[Dict]:
        """Complete stock-level analysis"""
        
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
            
            entry_candles = df[df['time'] >= entry_time]
            if len(entry_candles) == 0:
                return None
            
            entry_idx = entry_candles.index[0]
            data_till_entry = df.loc[:entry_idx]
            
            o = data_till_entry['open'].values.astype(float)
            h = data_till_entry['high'].values.astype(float)
            l = data_till_entry['low'].values.astype(float)
            c = data_till_entry['close'].values.astype(float)
            v = data_till_entry['volume'].values.astype(float)
            
            entry_price = float(c[-1])
            morning_open = float(o[0])
            morning_high = float(h.max())  # HIGH only up to entry time (no lookahead)
            morning_low = float(l.min())   # LOW only up to entry time (no lookahead)
            
            # === STOCK-LEVEL FEATURES ===
            features = {
                'stock': stock,
                'date': str(trade_date),
                'entry_price': entry_price,
            }
            
            # 1. MORNING MOVE (9:15 to entry time)
            features['morning_change_pct'] = ((entry_price - morning_open) / morning_open) * 100
            features['morning_direction'] = 'UP' if entry_price > morning_open else 'DOWN'
            
            # 2. MORNING RANGE ANALYSIS (no lookahead - only data up to 14:00)
            morning_range = morning_high - morning_low
            features['morning_range_pct'] = (morning_range / morning_open) * 100 if morning_open > 0 else 0
            features['position_in_morning_range'] = ((entry_price - morning_low) / morning_range) * 100 if morning_range > 0 else 50
            
            # 3. MOMENTUM (Price)
            if len(c) >= 11:
                features['momentum_10'] = ((c[-1] - c[-11]) / c[-11]) * 100
            
            # 4. SHORT-TERM TREND
            if len(c) >= 5:
                features['last_5_trend'] = ((c[-1] - c[-5]) / c[-5]) * 100
            
            # 5. RSI
            if len(c) >= 15:
                deltas = np.diff(c)
                gains = np.where(deltas > 0, deltas, 0)
                losses = np.where(deltas < 0, -deltas, 0)
                avg_gain = np.mean(gains[-14:])
                avg_loss = np.mean(losses[-14:])
                if avg_loss > 0:
                    rs = avg_gain / avg_loss
                    features['rsi'] = 100 - (100 / (1 + rs))
                else:
                    features['rsi'] = 100
            
            # 6. WILLIAMS %R
            if len(c) >= 14:
                hh = max(h[-14:])
                ll = min(l[-14:])
                if hh > ll:
                    features['williams_r'] = -100 * (hh - c[-1]) / (hh - ll)
                else:
                    features['williams_r'] = -50
            
            # 7. STOCHASTIC
            if len(c) >= 14:
                hh = max(h[-14:])
                ll = min(l[-14:])
                if hh > ll:
                    features['stochastic_k'] = 100 * (c[-1] - ll) / (hh - ll)
                else:
                    features['stochastic_k'] = 50
            
            # 8. VOLUME
            if len(v) >= 20:
                avg_vol = np.mean(v[-20:])
                features['volume_ratio'] = v[-1] / avg_vol if avg_vol > 0 else 1
                features['volume_spike'] = v[-1] > avg_vol * 2
            
            # 9. PRICE VS VWAP
            if len(v) > 0 and np.sum(v) > 0:
                typical_price = (h + l + c) / 3
                vwap = np.sum(typical_price * v) / np.sum(v)
                features['vs_vwap'] = ((c[-1] - vwap) / vwap) * 100
                features['above_vwap'] = c[-1] > vwap
            
            # 10. CANDLE PATTERN AT ENTRY
            body = c[-1] - o[-1]
            range_at_entry = h[-1] - l[-1]
            features['candle_bullish'] = body > 0
            features['candle_body_pct'] = (abs(body) / range_at_entry * 100) if range_at_entry > 0 else 0
            
            # 11. GAP FROM PREVIOUS DAY
            # (Would need previous day data - skip for now)
            
            # 12. EMA CROSSOVER STATUS
            if len(c) >= 20:
                ema9 = pd.Series(c).ewm(span=9).mean().iloc[-1]
                ema20 = pd.Series(c).ewm(span=20).mean().iloc[-1]
                features['ema_crossover'] = 'BULLISH' if ema9 > ema20 else 'BEARISH'
                features['ema_diff_pct'] = ((ema9 - ema20) / ema20) * 100
            
            # 13. MACD
            if len(c) >= 26:
                ema12 = pd.Series(c).ewm(span=12).mean()
                ema26 = pd.Series(c).ewm(span=26).mean()
                macd = ema12 - ema26
                signal = macd.ewm(span=9).mean()
                features['macd_bullish'] = macd.iloc[-1] > signal.iloc[-1]
                features['macd_histogram'] = float(macd.iloc[-1] - signal.iloc[-1])
            
            return features


class MultiStrategyDiscovery:
    """Discover multiple strategies from trade clusters"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.analyzer = StockLevelAnalyzer(db_url)
    
    async def connect(self):
        await self.analyzer.connect()
    
    async def close(self):
        await self.analyzer.close()
    
    async def analyze_trades(self, trades: List[Dict]) -> List[Dict]:
        """Analyze all trades at stock level"""
        results = []
        
        for trade in trades:
            trade_date = datetime.strptime(trade['date'], '%Y-%m-%d').date()
            stock = trade['stock']
            option_type = trade['optionType']
            
            analysis = await self.analyzer.analyze_stock(stock, trade_date)
            
            if analysis:
                analysis['option_type'] = option_type
                analysis['original_trade'] = trade
                results.append(analysis)
        
        return results
    
    def cluster_trades(self, analyses: List[Dict], n_clusters: int = 3) -> Dict:
        """Cluster trades by their characteristics"""
        
        # Select numeric features for clustering
        feature_cols = ['morning_change_pct', 'position_in_morning_range', 'rsi', 'williams_r', 
                        'stochastic_k', 'volume_ratio', 'vs_vwap']
        
        # Build feature matrix
        feature_data = []
        valid_indices = []
        
        for i, a in enumerate(analyses):
            row = []
            valid = True
            for col in feature_cols:
                if col in a and a[col] is not None:
                    row.append(a[col])
                else:
                    valid = False
                    break
            
            if valid:
                feature_data.append(row)
                valid_indices.append(i)
        
        if len(feature_data) < n_clusters:
            return {'error': f'Not enough valid trades for {n_clusters} clusters'}
        
        # Normalize and cluster
        scaler = StandardScaler()
        X = scaler.fit_transform(feature_data)
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)
        
        # Assign clusters
        clusters = defaultdict(list)
        for idx, label in zip(valid_indices, labels):
            clusters[label].append(analyses[idx])
        
        return dict(clusters)
    
    def analyze_cluster(self, cluster_trades: List[Dict]) -> Dict:
        """Analyze characteristics of a cluster"""
        
        if not cluster_trades:
            return {}
        
        # Count option types
        ce_count = sum(1 for t in cluster_trades if t.get('option_type') == 'CE')
        pe_count = sum(1 for t in cluster_trades if t.get('option_type') == 'PE')
        
        # Calculate averages
        def avg(key):
            vals = [t[key] for t in cluster_trades if key in t and t[key] is not None]
            return np.mean(vals) if vals else None
        
        return {
            'trade_count': len(cluster_trades),
            'ce_trades': ce_count,
            'pe_trades': pe_count,
            'dominant_type': 'CE' if ce_count > pe_count else 'PE' if pe_count > ce_count else 'MIXED',
            'avg_morning_change': avg('morning_change_pct'),
            'avg_morning_range_position': avg('position_in_morning_range'),
            'avg_rsi': avg('rsi'),
            'avg_williams_r': avg('williams_r'),
            'avg_stochastic': avg('stochastic_k'),
            'avg_volume_ratio': avg('volume_ratio'),
            'avg_vs_vwap': avg('vs_vwap'),
            'stocks': list(set(t['stock'] for t in cluster_trades)),
            'dates': list(set(t['date'] for t in cluster_trades))
        }
    
    def generate_strategy_rules(self, cluster_analysis: Dict, cluster_id: int) -> Dict:
        """Generate strategy rules from cluster analysis"""
        
        rules = {
            'strategy_id': f'STRATEGY_{cluster_id + 1}',
            'trade_type': cluster_analysis['dominant_type'],
            'conditions': {}
        }
        
        # Generate conditions based on averages
        if cluster_analysis.get('avg_rsi') is not None:
            rsi = cluster_analysis['avg_rsi']
            if rsi < 40:
                rules['conditions']['rsi'] = f'< 45 (oversold)'
            elif rsi > 60:
                rules['conditions']['rsi'] = f'> 55 (overbought)'
            else:
                rules['conditions']['rsi'] = f'{rsi-10:.0f} - {rsi+10:.0f}'
        
        if cluster_analysis.get('avg_williams_r') is not None:
            wr = cluster_analysis['avg_williams_r']
            if wr < -80:
                rules['conditions']['williams_r'] = f'< -75 (extreme oversold)'
            elif wr > -20:
                rules['conditions']['williams_r'] = f'> -25 (extreme overbought)'
        
        if cluster_analysis.get('avg_morning_range_position') is not None:
            pos = cluster_analysis['avg_morning_range_position']
            if pos < 30:
                rules['conditions']['morning_range_position'] = f'< 35% (near morning low - reversal)'
            elif pos > 70:
                rules['conditions']['morning_range_position'] = f'> 65% (near morning high - momentum)'
        
        if cluster_analysis.get('avg_volume_ratio') is not None:
            vol = cluster_analysis['avg_volume_ratio']
            if vol > 2:
                rules['conditions']['volume'] = f'> 2x average (high volume)'
        
        rules['description'] = self.generate_strategy_description(rules)
        
        return rules
    
    def generate_strategy_description(self, rules: Dict) -> str:
        """Generate human-readable strategy description"""
        
        trade_type = rules.get('trade_type', 'MIXED')
        conditions = rules.get('conditions', {})
        
        desc_parts = []
        
        if trade_type == 'CE':
            desc_parts.append("Buy CALL option when")
        elif trade_type == 'PE':
            desc_parts.append("Buy PUT option when")
        else:
            desc_parts.append("Trade when")
        
        for key, val in conditions.items():
            desc_parts.append(f"  - {key.upper()}: {val}")
        
        return '\n'.join(desc_parts)


async def main():
    """Run multi-strategy discovery on user's trades"""
    
    # Stock name mapping
    stock_mapping = {
        'IEX': 'IEX', 'Hind Zinc': 'HINDZINC', 'Hero Motors': 'HEROMOTOCO',
        'TVS Motor': 'TVSMOTOR', 'Idea': 'IDEA', 'Paytm': 'PAYTM',
        'GMR': 'GMRAIRPORT', 'Asian Paints': 'ASIANPAINT', 'Can Bank': 'CANBK',
        'Delhivery': 'DELHIVERY', 'Angel One': 'ANGELONE', 'Kaynes': 'KAYNES',
        'Indigo': 'INDIGO', 'Petronet': 'PETRONET', 'Power India': 'POWERINDIA',
        'Shriram Fin': 'SHRIRAMFIN', 'Oberoi Realty': 'OBEROIRLTY', 'Vedl': 'VEDL',
        'Supreme': 'SUPREMEIND', 'Axis': 'AXISBANK', 'RBL': 'RBLBANK',
        'Max Health': 'MAXHEALTH'
    }
    
    # Load user trades
    with open('backend/data/user_trades.json', 'r') as f:
        raw_trades = json.load(f)
    
    # Normalize stock names
    trades = []
    for t in raw_trades:
        stock_name = t['stockName']
        normalized = stock_mapping.get(stock_name) or stock_name.upper().replace(' ', '')
        trades.append({
            'date': t['date'],
            'stock': normalized,
            'optionType': t['optionType'],
            'strike': t['strike'],
            'premium': t['entryPremium']
        })
    
    print("=" * 100)
    print("🎯 MULTI-STRATEGY DISCOVERY ENGINE")
    print("=" * 100)
    print("\nApproach: Stock-level analysis → Discover multiple strategies")
    print(f"Analyzing {len(trades)} trades...")
    
    discovery = MultiStrategyDiscovery('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await discovery.connect()
    
    # Analyze all trades
    print("\n📊 Step 1: Analyzing trades at STOCK level...")
    analyses = await discovery.analyze_trades(trades)
    print(f"   Successfully analyzed: {len(analyses)}/{len(trades)} trades")
    
    # Show individual trade characteristics
    print("\n📋 Step 2: Individual Trade Characteristics:")
    print("-" * 100)
    
    for a in analyses[:10]:  # Show first 10
        print(f"\n   {a['date']} | {a['stock']} | {a['option_type']}")
        print(f"      Morning: {a.get('morning_direction', 'N/A')} {a.get('morning_change_pct', 0):+.2f}%")
        print(f"      Range Pos: {a.get('position_in_morning_range', 0):.1f}% | RSI: {a.get('rsi', 0):.1f}")
        print(f"      Williams %R: {a.get('williams_r', 0):.1f} | Stoch: {a.get('stochastic_k', 0):.1f}")
    
    # Cluster trades
    print("\n\n📊 Step 3: Clustering trades into strategy groups...")
    clusters = discovery.cluster_trades(analyses, n_clusters=3)
    
    if 'error' in clusters:
        print(f"   ⚠️ {clusters['error']}")
    else:
        strategies = []
        
        for cluster_id, cluster_trades in clusters.items():
            print(f"\n{'=' * 80}")
            print(f"📌 CLUSTER {cluster_id + 1}: {len(cluster_trades)} trades")
            print("=" * 80)
            
            # Analyze cluster
            cluster_analysis = discovery.analyze_cluster(cluster_trades)
            
            print(f"   Trade Types: {cluster_analysis['ce_trades']} CE, {cluster_analysis['pe_trades']} PE")
            print(f"   Dominant: {cluster_analysis['dominant_type']}")
            print(f"   Stocks: {', '.join(cluster_analysis['stocks'][:5])}{'...' if len(cluster_analysis['stocks']) > 5 else ''}")
            
            print(f"\n   Average Characteristics (up to entry time):")
            print(f"      Morning Change: {cluster_analysis.get('avg_morning_change', 0):+.2f}%")
            print(f"      Morning Range Position: {cluster_analysis.get('avg_morning_range_position', 0):.1f}%")
            print(f"      RSI: {cluster_analysis.get('avg_rsi', 0):.1f}")
            print(f"      Williams %R: {cluster_analysis.get('avg_williams_r', 0):.1f}")
            print(f"      Volume Ratio: {cluster_analysis.get('avg_volume_ratio', 0):.2f}x")
            
            # Generate rules
            rules = discovery.generate_strategy_rules(cluster_analysis, cluster_id)
            strategies.append({
                'cluster': cluster_id,
                'analysis': cluster_analysis,
                'rules': rules,
                'trades': [{'stock': t['stock'], 'date': t['date'], 'type': t['option_type']} for t in cluster_trades]
            })
            
            print(f"\n   📝 SUGGESTED STRATEGY:")
            print(f"      {rules['description']}")
        
        # Save results
        with open('backend/data/multi_strategy_discovery.json', 'w') as f:
            json.dump(strategies, f, indent=2, default=str)
        
        print(f"\n\n📄 Results saved to: backend/data/multi_strategy_discovery.json")
    
    await discovery.close()
    print("\n✅ Complete!")


if __name__ == "__main__":
    asyncio.run(main())
