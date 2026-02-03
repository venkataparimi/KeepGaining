from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import random
from loguru import logger
from app.services.market_service import market_service

router = APIRouter()


def generate_candles(base_price: float, count: int, volatility: float) -> List[Dict[str, Any]]:
    """Generate candle data for a timeframe."""
    candles = []
    price = base_price * (0.98 + random.random() * 0.04)
    
    for i in range(count, -1, -1):
        change = (random.random() - 0.48) * volatility
        open_price = price
        close_price = price + change
        high = max(open_price, close_price) + random.random() * volatility * 0.3
        low = min(open_price, close_price) - random.random() * volatility * 0.3
        
        candles.append({
            "time": str(i),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close_price, 2),
        })
        price = close_price
    
    return candles


def create_timeframes(base_price: float) -> Dict[str, Dict[str, Any]]:
    """Create multi-timeframe analysis data."""
    def get_trend_signal():
        r = random.random()
        if r > 0.6:
            return "bullish", "Buy"
        elif r > 0.3:
            return "bearish", "Sell"
        return "neutral", "Hold"
    
    timeframes = {}
    configs = {
        "5M": (0.001, 0.5, 0.995, 1.005),
        "15M": (0.002, 1.0, 0.99, 1.01),
        "1H": (0.003, 2.0, 0.985, 1.015),
        "4H": (0.005, 3.0, 0.98, 1.02),
        "1D": (0.008, 5.0, 0.97, 1.03),
    }
    
    for tf, (vol_mult, change_mult, support_mult, resistance_mult) in configs.items():
        trend, signal = get_trend_signal()
        timeframes[tf] = {
            "trend": trend,
            "change": round((random.random() - 0.5) * change_mult, 2),
            "support": round(base_price * support_mult, 2),
            "resistance": round(base_price * resistance_mult, 2),
            "signal": signal,
            "candles": generate_candles(base_price, 50, base_price * vol_mult),
        }
    
    return timeframes


# API Endpoints

@router.get("/indices")
async def get_indices():
    """
    Get all major indices with multi-timeframe analysis.
    Returns NIFTY 50, BANK NIFTY, NIFTY IT, NIFTY FIN with price data and timeframe analysis.
    """
    try:
        # Try to get real data from data hub
        try:
            from app.services.realtime_hub import get_data_hub
            hub = await get_data_hub()
            
            nifty = hub._quote_cache.get("NSE_INDEX|Nifty 50")
            banknifty = hub._quote_cache.get("NSE_INDEX|Nifty Bank")
            niftyit = hub._quote_cache.get("NSE_INDEX|Nifty IT")
            finnifty = hub._quote_cache.get("NSE_INDEX|Nifty Fin Service")
            
            if nifty and nifty.ltp > 0:
                indices = []
                quote_map = [
                    ("NIFTY 50", "^NSEI", nifty),
                    ("BANK NIFTY", "^NSEBANK", banknifty),
                    ("NIFTY IT", "^CNXIT", niftyit),
                    ("NIFTY FIN", "^CNXFIN", finnifty),
                ]
                
                for name, symbol, quote in quote_map:
                    if quote and quote.ltp > 0:
                        indices.append({
                            "name": name,
                            "symbol": symbol,
                            "price": quote.ltp,
                            "change": quote.change or 0,
                            "changePercent": quote.change_percent or 0,
                            "dayHigh": quote.high or quote.ltp,
                            "dayLow": quote.low or quote.ltp,
                            "open": quote.open or quote.ltp,
                            "prevClose": quote.prev_close or quote.ltp,
                            "timeframes": create_timeframes(quote.ltp),
                        })
                
                if indices:
                    return indices
        except Exception as e:
            logger.debug(f"Could not get real-time index data: {e}")
        
        # Fallback to simulated data
        indices_data = [
            ("NIFTY 50", "^NSEI", 24523.50, 125.30, 0.51),
            ("BANK NIFTY", "^NSEBANK", 52180.75, -245.50, -0.47),
            ("NIFTY IT", "^CNXIT", 38542.25, 312.80, 0.82),
            ("NIFTY FIN", "^CNXFIN", 22845.60, 85.20, 0.37),
        ]
        
        result = []
        for name, symbol, price, change, change_pct in indices_data:
            result.append({
                "name": name,
                "symbol": symbol,
                "price": price,
                "change": change,
                "changePercent": change_pct,
                "dayHigh": round(price * 1.002, 2),
                "dayLow": round(price * 0.995, 2),
                "open": round(price - change * 0.3, 2),
                "prevClose": round(price - change, 2),
                "timeframes": create_timeframes(price),
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting indices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sectors/performance")
async def get_sector_performance():
    """Get real-time performance metrics for all major sectors"""
    return await market_service.get_sector_performance()

@router.get("/sectors/{sector_id}/stocks")
async def get_sector_stocks(sector_id: str):
    """Get stock details for a specific sector"""
    # TODO: Implement real-time sector constituents fetching
    # For now, return mock data to avoid breaking the UI
    # In future, we can map sector -> list of symbols and fetch batch quotes
    count = random.randint(10, 15)
    stocks = []
    base_price = random.uniform(100, 3000)
    
    for i in range(count):
        symbol = f"{sector_id.split()[-1].upper()}_{i+1}"
        change = round(random.uniform(-4.0, 4.0), 2)
        price = round(base_price * (1 + random.uniform(-0.2, 0.2)), 2)
        
        stocks.append({
            "symbol": symbol,
            "price": price,
            "change_percent": change,
            "volume": random.randint(100000, 5000000),
            "oi_change_percent": round(random.uniform(-10, 20), 1),
            "delivery_percent": round(random.uniform(20, 60), 1)
        })
    return sorted(stocks, key=lambda x: x["change_percent"], reverse=True)

@router.get("/fno/movers")
async def get_fno_movers_data():
    """Get real-time top F&O movers"""
    return await market_service.get_fno_movers()
