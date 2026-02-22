"""
AI Strategy Discovery Engine - Trade Analyzer
Analyzes individual trades to extract features and market context

Uses existing candle_data from database to build comprehensive trade analysis.
"""
import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dt_time, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import json

@dataclass
class TradeAnalysis:
    """Comprehensive analysis of a single trade"""
    # Trade basics
    trade_date: str
    stock: str
    strike: float
    option_type: str
    entry_time: str
    entry_premium: float
    exit_premium: Optional[float] = None
    pnl: Optional[float] = None
    
    # Price features at entry
    spot_price: Optional[float] = None
    morning_open: Optional[float] = None
    morning_high: Optional[float] = None
    morning_low: Optional[float] = None
    morning_range_pct: Optional[float] = None
    price_vs_morning_high: Optional[float] = None
    price_vs_morning_low: Optional[float] = None
    range_position: Optional[float] = None  # 0-100%
    
    # Technical indicators
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    sma_9: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    price_vs_sma_9: Optional[float] = None
    price_vs_sma_20: Optional[float] = None
    bollinger_position: Optional[float] = None  # 0-100%
    
    # Volume features
    volume_at_entry: Optional[float] = None
    avg_volume_20: Optional[float] = None
    volume_ratio: Optional[float] = None
    
    # Time features
    entry_hour: Optional[int] = None
    entry_minute: Optional[int] = None
    minutes_from_open: Optional[int] = None
    minutes_to_close: Optional[int] = None
    
    # Strike features
    strike_distance: Optional[float] = None  # Distance from spot
    strike_distance_pct: Optional[float] = None
    moneyness: Optional[str] = None  # ITM/ATM/OTM
    
    # Post-entry features (if known)
    max_gain_pct: Optional[float] = None
    max_loss_pct: Optional[float] = None
    exit_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class TradeAnalyzer:
    """Analyzes trades using market data from database"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    def calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def calculate_macd(self, prices: np.ndarray) -> tuple:
        """Calculate MACD, Signal, Histogram"""
        if len(prices) < 26:
            return 0, 0, 0
        exp1 = pd.Series(prices).ewm(span=12, adjust=False).mean()
        exp2 = pd.Series(prices).ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        return float(macd.iloc[-1]), float(signal.iloc[-1]), float(histogram.iloc[-1])
    
    def calculate_bollinger_position(self, prices: np.ndarray, current_price: float, period: int = 20) -> float:
        """Calculate position within Bollinger Bands (0-100%)"""
        if len(prices) < period:
            return 50.0
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        if std == 0:
            return 50.0
        upper = sma + (2 * std)
        lower = sma - (2 * std)
        if upper == lower:
            return 50.0
        return ((current_price - lower) / (upper - lower)) * 100
    
    async def analyze_trade(self, trade: Dict[str, Any]) -> TradeAnalysis:
        """Analyze a single trade with full market context"""
        
        trade_date = trade.get('date')
        if isinstance(trade_date, str):
            trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
        
        stock = trade.get('stock') or trade.get('stockName', '').upper()
        # Normalize stock names
        stock_mapping = {
            'HIND ZINC': 'HINDZINC',
            'HERO MOTORS': 'HEROMOTOCO',
            'HERO MOTOCORP': 'HEROMOTOCO',
        }
        stock = stock_mapping.get(stock.upper(), stock.upper())
        
        strike = float(trade.get('strike', 0))
        option_type = trade.get('optionType', 'CE')
        entry_time_str = trade.get('entryTime', '14:00')
        entry_premium = float(trade.get('entryPremium', 0))
        exit_premium = trade.get('exitPremium')
        pnl = trade.get('pnl')
        
        # Parse entry time
        if isinstance(entry_time_str, str):
            try:
                entry_time = datetime.strptime(entry_time_str, '%H:%M').time()
            except:
                entry_time = dt_time(14, 0)
        else:
            entry_time = dt_time(14, 0)
        
        # Create base analysis
        analysis = TradeAnalysis(
            trade_date=str(trade_date),
            stock=stock,
            strike=strike,
            option_type=option_type,
            entry_time=str(entry_time),
            entry_premium=entry_premium,
            exit_premium=float(exit_premium) if exit_premium else None,
            pnl=float(pnl) if pnl else None,
            entry_hour=entry_time.hour,
            entry_minute=entry_time.minute,
            minutes_from_open=(entry_time.hour - 9) * 60 + entry_time.minute - 15,
            minutes_to_close=(15 - entry_time.hour) * 60 + (30 - entry_time.minute)
        )
        
        # Get market data
        async with self.pool.acquire() as conn:
            # Get futures data (proxy for spot)
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
            
            if not data:
                return analysis
            
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp']) + pd.Timedelta(hours=5, minutes=30)
            df['time'] = df['timestamp'].dt.time
            
            # Find entry candle
            entry_candles = df[df['time'] >= entry_time]
            if len(entry_candles) == 0:
                return analysis
            
            entry_idx = entry_candles.index[0]
            entry_candle = df.loc[entry_idx]
            data_till_entry = df.loc[:entry_idx]
            
            # Extract price features
            prices = data_till_entry['close'].values.astype(float)
            spot_price = float(entry_candle['close'])
            
            analysis.spot_price = spot_price
            analysis.morning_open = float(df.iloc[0]['close'])
            analysis.morning_high = float(data_till_entry['high'].max())
            analysis.morning_low = float(data_till_entry['low'].min())
            analysis.morning_range_pct = ((analysis.morning_high - analysis.morning_low) / analysis.morning_low) * 100
            
            analysis.price_vs_morning_high = ((spot_price - analysis.morning_high) / analysis.morning_high) * 100
            analysis.price_vs_morning_low = ((spot_price - analysis.morning_low) / analysis.morning_low) * 100
            
            if analysis.morning_high > analysis.morning_low:
                analysis.range_position = ((spot_price - analysis.morning_low) / (analysis.morning_high - analysis.morning_low)) * 100
            
            # Technical indicators
            if len(prices) >= 14:
                analysis.rsi_14 = self.calculate_rsi(prices, 14)
            
            if len(prices) >= 26:
                analysis.macd, analysis.macd_signal, analysis.macd_histogram = self.calculate_macd(prices)
            
            if len(prices) >= 9:
                analysis.sma_9 = float(np.mean(prices[-9:]))
            if len(prices) >= 20:
                analysis.sma_20 = float(np.mean(prices[-20:]))
            if len(prices) >= 50:
                analysis.sma_50 = float(np.mean(prices[-50:]))
            
            if analysis.sma_9:
                analysis.price_vs_sma_9 = ((spot_price - analysis.sma_9) / analysis.sma_9) * 100
            if analysis.sma_20:
                analysis.price_vs_sma_20 = ((spot_price - analysis.sma_20) / analysis.sma_20) * 100
            
            if len(prices) >= 20:
                analysis.bollinger_position = self.calculate_bollinger_position(prices, spot_price, 20)
            
            # Volume features
            volumes = data_till_entry['volume'].values.astype(float)
            analysis.volume_at_entry = float(entry_candle['volume'])
            if len(volumes) >= 20:
                analysis.avg_volume_20 = float(np.mean(volumes[-20:]))
                if analysis.avg_volume_20 > 0:
                    analysis.volume_ratio = analysis.volume_at_entry / analysis.avg_volume_20
            
            # Strike features
            analysis.strike_distance = spot_price - strike
            if spot_price > 0:
                analysis.strike_distance_pct = (analysis.strike_distance / spot_price) * 100
            
            if analysis.strike_distance > 0:
                analysis.moneyness = 'ITM'
            elif analysis.strike_distance < 0:
                analysis.moneyness = 'OTM'
            else:
                analysis.moneyness = 'ATM'
            
            # Post-entry movement (if we have data)
            post_entry = df.loc[entry_idx+1:]
            if len(post_entry) > 0:
                max_price = float(post_entry['high'].max())
                min_price = float(post_entry['low'].min())
                analysis.max_gain_pct = ((max_price - spot_price) / spot_price) * 100
                analysis.max_loss_pct = ((min_price - spot_price) / spot_price) * 100
        
        return analysis
    
    async def analyze_multiple_trades(self, trades: List[Dict]) -> List[TradeAnalysis]:
        """Analyze multiple trades"""
        results = []
        for trade in trades:
            analysis = await self.analyze_trade(trade)
            results.append(analysis)
        return results


async def main():
    """Test the trade analyzer"""
    
    # Test trades
    trades = [
        {
            "date": "2025-12-01",
            "stockName": "HINDZINC",
            "strike": 500,
            "optionType": "CE",
            "entryTime": "14:00",
            "entryPremium": 14.0,
            "exitPremium": 23.0,
            "pnl": 11025
        },
        {
            "date": "2025-12-01",
            "stockName": "Hero Motors",
            "strike": 6200,
            "optionType": "CE",
            "entryTime": "14:00",
            "entryPremium": 195.0
        }
    ]
    
    analyzer = TradeAnalyzer('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await analyzer.connect()
    
    print("=" * 80)
    print("🔍 TRADE ANALYZER - Feature Extraction")
    print("=" * 80)
    
    for trade in trades:
        print(f"\n📊 Analyzing: {trade.get('stockName', trade.get('stock'))} {trade.get('strike')} {trade.get('optionType')}")
        analysis = await analyzer.analyze_trade(trade)
        
        print(f"\n📈 Features Extracted:")
        print(f"   Stock: {analysis.stock}")
        print(f"   Date: {analysis.trade_date}")
        print(f"   Entry Time: {analysis.entry_time}")
        print(f"   Entry Premium: ₹{analysis.entry_premium}")
        
        if analysis.spot_price:
            print(f"\n   📊 Price Features:")
            print(f"      Spot Price: ₹{analysis.spot_price:.2f}")
            print(f"      Morning Open: ₹{analysis.morning_open:.2f}")
            print(f"      Morning Range: {analysis.morning_range_pct:.2f}%")
            print(f"      Range Position: {analysis.range_position:.1f}%")
        
        if analysis.rsi_14:
            print(f"\n   📈 Technical Indicators:")
            print(f"      RSI(14): {analysis.rsi_14:.2f}")
            print(f"      MACD: {analysis.macd:.2f}")
            print(f"      MACD Signal: {analysis.macd_signal:.2f}")
            print(f"      Bollinger Position: {analysis.bollinger_position:.1f}%")
        
        if analysis.volume_ratio:
            print(f"\n   📊 Volume:")
            print(f"      Volume Ratio: {analysis.volume_ratio:.2f}x")
        
        print(f"\n   🎯 Strike Analysis:")
        print(f"      Strike: {analysis.strike}")
        print(f"      Distance: {analysis.strike_distance:.2f} ({analysis.strike_distance_pct:.2f}%)")
        print(f"      Moneyness: {analysis.moneyness}")
        
        print("-" * 80)
    
    await analyzer.close()
    print("\n✅ Analysis Complete!")


if __name__ == "__main__":
    asyncio.run(main())
