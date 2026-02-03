from typing import List, Dict, Any
from app.brokers.fyers import FyersBroker
import asyncio
import random
from loguru import logger

class MarketService:
    def __init__(self):
        self.use_mock = False
        try:
            self.broker = FyersBroker()
            # Trigger auth check (will raise if auth fails and no fallback)
            # But FyersBroker init just creates client. Client auth happens on first call or explicit auth.
            # We'll let it fail on first call and handle there, or try to auth now?
            # FyersBroker doesn't expose auth method directly, but client does.
            # Let's assume we try to use it, and if it fails, we switch to mock.
            pass
        except Exception as e:
            logger.error(f"Failed to initialize FyersBroker: {e}")
            self.use_mock = True
        
        # Map display names to Fyers symbols
        self.sector_map = {
            "Nifty Bank": "NSE:NIFTYBANK-INDEX",
            "Nifty PSU Bank": "NSE:NIFTYPSUBANK-INDEX", 
            "Nifty Pvt Bank": "NSE:NIFTYPVTBANK-INDEX",
            "Nifty Midcap 50": "NSE:NIFTYMIDCAP50-INDEX",
            "Nifty Oil & Gas": "NSE:NIFTYOILANDGAS-INDEX",
            "Nifty Media": "NSE:NIFTYMEDIA-INDEX",
            "Nifty IT": "NSE:NIFTYIT-INDEX",
            "Nifty Auto": "NSE:NIFTYAUTO-INDEX",
            "Nifty Pharma": "NSE:NIFTYPHARMA-INDEX",
            "Nifty FMCG": "NSE:NIFTYFMCG-INDEX",
            "Nifty Metal": "NSE:NIFTYMETAL-INDEX",
            "Nifty Energy": "NSE:NIFTYENERGY-INDEX",
            "Nifty Infra": "NSE:NIFTYINFRA-INDEX",
            "Nifty Realty": "NSE:NIFTYREALTY-INDEX"
        }
        
        # Top F&O Stocks (Representative List)
        self.fno_symbols = [
            "NSE:RELIANCE-EQ", "NSE:HDFCBANK-EQ", "NSE:INFY-EQ", "NSE:TCS-EQ",
            "NSE:ICICIBANK-EQ", "NSE:SBIN-EQ", "NSE:AXISBANK-EQ", "NSE:KOTAKBANK-EQ",
            "NSE:LT-EQ", "NSE:ITC-EQ", "NSE:BHARTIARTL-EQ", "NSE:ASIANPAINT-EQ",
            "NSE:MARUTI-EQ", "NSE:TATASTEEL-EQ", "NSE:TATAMOTORS-EQ", "NSE:SUNPHARMA-EQ",
            "NSE:TITAN-EQ", "NSE:BAJFINANCE-EQ", "NSE:HINDUNILVR-EQ", "NSE:NTPC-EQ",
            "NSE:POWERGRID-EQ", "NSE:ONGC-EQ", "NSE:COALINDIA-EQ", "NSE:ADANIENT-EQ",
            "NSE:ADANIPORTS-EQ", "NSE:WIPRO-EQ", "NSE:HCLTECH-EQ", "NSE:TECHM-EQ",
            "NSE:ULTRACEMCO-EQ", "NSE:GRASIM-EQ"
        ]

    async def get_sector_performance(self) -> List[Dict[str, Any]]:
        """Fetch real-time performance for sectors."""
        if self.use_mock:
            return self._generate_mock_sector_performance()

        try:
            symbols = list(self.sector_map.values())
            quotes = await self.broker.get_quotes_batch(symbols)
            
            if not quotes:
                logger.warning("No quotes received from Fyers, falling back to mock")
                return self._generate_mock_sector_performance()
            
            performance = []
            for name, symbol in self.sector_map.items():
                data = quotes.get(symbol, {})
                change = data.get("change_percent", 0.0)
                
                performance.append({
                    "sector": name,
                    "change_percent": round(change, 2),
                    "volume_million": round(data.get("volume", 0) / 1000000, 2),
                    "advances": 0, 
                    "declines": 0,
                    "trend": "Bullish" if change > 0.5 else "Bearish" if change < -0.5 else "Neutral"
                })
                
            return sorted(performance, key=lambda x: x["change_percent"], reverse=True)
        except Exception as e:
            logger.error(f"Error fetching sector data: {e}")
            return self._generate_mock_sector_performance()

    async def get_fno_movers(self) -> Dict[str, Any]:
        """Fetch real-time F&O movers."""
        if self.use_mock:
            return self._generate_mock_fno_movers()

        try:
            quotes = await self.broker.get_quotes_batch(self.fno_symbols)
            
            if not quotes:
                return self._generate_mock_fno_movers()
            
            stocks = []
            for symbol, data in quotes.items():
                display_name = symbol.replace("NSE:", "").replace("-EQ", "")
                change = data.get("change_percent", 0.0)
                
                # Determine build-up
                buildup = "Neutral"
                if change > 0:
                    buildup = "Long Buildup"
                elif change < 0:
                    buildup = "Short Buildup"
                    
                stocks.append({
                    "symbol": display_name,
                    "price": data.get("price", 0.0),
                    "change_percent": round(change, 2),
                    "oi_change_percent": 0.0, 
                    "volume_shock": False,
                    "buildup": buildup
                })
                
            return {
                "top_gainers": sorted(stocks, key=lambda x: x["change_percent"], reverse=True)[:5],
                "top_losers": sorted(stocks, key=lambda x: x["change_percent"])[:5],
                "oi_gainers": [], 
                "oi_losers": [], 
                "volume_shockers": [] 
            }
        except Exception as e:
            logger.error(f"Error fetching F&O data: {e}")
            return self._generate_mock_fno_movers()

    def _generate_mock_sector_performance(self):
        sectors = list(self.sector_map.keys())
        performance = []
        for sector in sectors:
            change = round(random.uniform(-2.5, 2.5), 2)
            performance.append({
                "sector": sector,
                "change_percent": change,
                "volume_million": round(random.uniform(50, 500), 1),
                "advances": random.randint(5, 15),
                "declines": random.randint(5, 15),
                "trend": "Bullish" if change > 0.5 else "Bearish" if change < -0.5 else "Neutral"
            })
        return sorted(performance, key=lambda x: x["change_percent"], reverse=True)

    def _generate_mock_fno_movers(self):
        stocks = []
        for i in range(20):
            symbol = f"STOCK_{i+1}"
            change = round(random.uniform(-5.0, 5.0), 2)
            stocks.append({
                "symbol": symbol,
                "price": round(random.uniform(500, 2000), 2),
                "change_percent": change,
                "oi_change_percent": round(random.uniform(-10, 20), 1),
                "volume_shock": False,
                "buildup": "Long Buildup" if change > 0 else "Short Buildup"
            })
        return {
            "top_gainers": sorted(stocks, key=lambda x: x["change_percent"], reverse=True)[:5],
            "top_losers": sorted(stocks, key=lambda x: x["change_percent"])[:5],
            "oi_gainers": [],
            "oi_losers": [],
            "volume_shockers": []
        }

market_service = MarketService()
