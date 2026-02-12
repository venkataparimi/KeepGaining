import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from app.mcp.scrapers.nse_oi import NSE_OI_Scraper
from app.mcp.scrapers.trendlyne import TrendlyneScraper
from app.mcp.technical_analyzer import TechnicalAnalyzer
from app.mcp.manager import MCPManager

logger = logging.getLogger(__name__)

class MarketAnalysisEngine:
    """
    Orchestrates data gathering and analysis for potential trading setups.
    Aggregates data from NSE and Trendlyne to identify high-conviction stocks.
    """
    
    def __init__(self, headless: bool = True):
        self.output_dir = "analysis_reports"
        self.headless = headless
        
        # Initialize scrapers and analyzers
        self.nse_scraper = NSE_OI_Scraper()
        self.trendlyne_scraper = TrendlyneScraper()
        self.technical_analyzer = TechnicalAnalyzer()
        
    async def run_analysis(self) -> Dict[str, Any]:
        """
        Main execution flow:
        1. Fetch Premarket Data (Gap Up identification)
        2. Fetch Trendlyne Heatmap (Bullish Momentum identification)
        3. Cross-reference candidates
        4. Validate with Option Chain (OI Support)
        5. Generate Report
        """
        logger.info("Starting Market Analysis Engine...")
        report = {
            "timestamp": datetime.now().isoformat(),
            "gap_up_stocks": [],
            "trendlyne_bullish": [],
            "potential_setups": [],
            "errors": []
        }
        
        try:
            # 1. Fetch Premarket Data
            logger.info("Step 1: Fetching Premarket Data...")
            premarket_data = await self.nse_scraper.get_premarket_data()
            if premarket_data:
                # Filter for > 0.5% gap up
                report['gap_up_stocks'] = [
                    s for s in premarket_data 
                    if s.get('pChange', 0) > 0.5
                ]
                logger.info(f"Found {len(report['gap_up_stocks'])} gap-up stocks > 0.5%")
            else:
                report['errors'].append("Failed to fetch premarket data")
                
            # 2. Fetch Trendlyne Heatmap
            logger.info("Step 2: Fetching Trendlyne Heatmap...")
            tl_data = await self.trendlyne_scraper.get_fno_heatmap(headless=self.headless)
            if tl_data and 'stocks' in tl_data:
                # Filter for Long Build Up or Short Covering
                report['trendlyne_bullish'] = [
                    s for s in tl_data['stocks']
                    if s.get('analysis_status') in ["Long Build Up", "Short Covering"]
                ]
                logger.info(f"Found {len(report['trendlyne_bullish'])} bullish Trendlyne stocks")
            else:
                report['errors'].append("Failed to fetch Trendlyne heatmap")
                
            # 3. Cross-Reference (Intersection)
            logger.info("Step 3: Finding Candidates...")
            
            candidates = []
            
            # Scenario A: We have both data sources (Ideal)
            if report['gap_up_stocks'] and report['trendlyne_bullish']:
                logger.info("Using Intersection Strategy (Gap Up + Trendlyne)")
                tl_bullish_symbols = {s['symbol'] for s in report['trendlyne_bullish']}
                for stock in report['gap_up_stocks']:
                    symbol = stock.get('symbol')
                    if symbol in tl_bullish_symbols:
                        candidates.append({
                            "symbol": symbol,
                            "gap_up_pct": stock.get('pChange'),
                            "price": stock.get('lastPrice'),
                            "trendlyne_status": next(
                                (s['analysis_status'] for s in report['trendlyne_bullish'] if s['symbol'] == symbol), 
                                "Unknown"
                            ),
                            "strategy": "Gap Up + Trendlyne"
                        })
            
            # Scenario B: We only have Trendlyne (Fallback)
            elif report['trendlyne_bullish']:
                logger.warning("Fallback: Using only Trendlyne Bullish stocks (NSE Premarket missing)")
                for stock in report['trendlyne_bullish']:
                    candidates.append({
                        "symbol": stock.get('symbol'),
                        "gap_up_pct": "N/A",
                        "price": stock.get('price'),
                        "trendlyne_status": stock.get('analysis_status'),
                        "strategy": "Trendlyne Only"
                    })
            
            logger.info(f"Found {len(candidates)} candidates for OI validation")
            
            # 4. Validate with Technical Analysis & OI Support
            logger.info("Step 4: Validating candidates with Technical Analysis & OI...")
            
            for setup in candidates:
                symbol = setup['symbol']
                logger.info(f"Analyzing {symbol}...")
                
                try:
                    # A. Technical Score (DB Data)
                    ta_result = await self.technical_analyzer.get_technical_analysis(symbol)
                    setup['technical_score'] = ta_result.get('score', 0)
                    setup['rating'] = ta_result.get('rating', 'Unknown')
                    setup['indicators'] = ta_result.get('indicators', {})
                    
                    # B. Option Chain (Live Data)
                    # Only fetch if technical score is decent (>4) to save time, or just fetch all
                    if setup['technical_score'] >= 4:
                         oc_data = await self.nse_scraper.get_oi_data(symbol) # Use new method name
                    else:
                         oc_data = None
                         logger.info(f"Skipping OI for {symbol} due to low technical score ({setup['technical_score']})")

                    # Simple OI Support Logic:
                    if oc_data:
                        # Logic placeholder - implies we need to parse OC data deep
                        # For now, we will mark as 'OI Data Fetched' and manually reviewing recommended
                        setup['oi_support'] = "Check Manual" 
                        setup['oc_summary'] = f"PCR: Included in detailed report" # Ideally calculate PCR
                    else:
                        setup['oi_support'] = "Data Missing/Skipped"
                    
                    report['potential_setups'].append(setup)
                    
                except Exception as e:
                     logger.error(f"Error analyzing {symbol}: {e}")
                     setup['error'] = str(e)
                     report['potential_setups'].append(setup)

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            report['errors'].append(str(e))
            
        return report

if __name__ == "__main__":
    # Basic self-test
    logging.basicConfig(level=logging.INFO)
    engine = MarketAnalysisEngine(headless=True)
    asyncio.run(engine.run_analysis())
