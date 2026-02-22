import asyncio
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional
import pandas as pd
from loguru import logger
from sqlalchemy import select

from app.strategies.base import BaseStrategy, Signal, SignalType
from app.brokers.fyers import FyersBroker
from app.brokers.upstox_data import UpstoxDataService, HistoricalCandle
from app.db.session import AsyncSessionLocal
from app.db.models.instrument import InstrumentMaster
from app.db.models.broker import BrokerSymbolMapping
from app.db.models.timeseries import CandleData
from app.services.sentiment_analyzer import get_sentiment_analyzer
from app.schemas.broker import OrderRequest

# Try to import NSE for earnings calendar
try:
    from nsemine import NSE
    NSE_AVAILABLE = True
except ImportError:
    NSE = None
    NSE_AVAILABLE = False
    logger.warning("nsemine library not found. Earnings calendar fetching will be disabled.")


class EMOSStrategy(BaseStrategy):
    """
    Earnings Momentum & Sentiment (EMOS) Strategy.
    
    Combines earnings calendar events, historical price momentum (surprise proxy),
    and sentiment analysis to generate trading signals.
    """
    
    def __init__(self, broker: FyersBroker, upstox_service: UpstoxDataService, config: Dict[str, Any]):
        super().__init__(broker, None, config)  # No default data_feed, using specific services
        self.upstox = upstox_service
        self.broker = broker  # Type hint as FyersBroker
        
        # Configuration
        self.capital = config.get("capital", 100000)
        self.risk_per_trade = config.get("risk_per_trade", 0.01)
        self.stock_universe = config.get("stock_universe", ['AMBER', 'TITAN', 'EICHERMOT', 'OIL', 'APOLLOHOSP'])
        self.days_ahead = config.get("days_ahead", 7)
        self.days_back = config.get("hitorical_days_back", 30)
        self.sentiment_threshold_bullish = config.get("sentiment_threshold_bullish", 0.6)
        self.sentiment_threshold_bearish = config.get("sentiment_threshold_bearish", 0.4)
        self.surprise_threshold = config.get("surprise_threshold", 0.1)
        
        # NSE Scraper
        self.nse = NSE() if NSE_AVAILABLE else None

    async def load_fno_universe(self):
        """Load all FnO stocks from DB (underlying symbols)."""
        try:
            async with AsyncSessionLocal() as session:
                # Get distinct underlying symbols where segment is FO or similar
                # Upstox/Instruments might have 'FO' segment
                stmt = select(InstrumentMaster.underlying).where(
                    InstrumentMaster.segment == 'FO',
                    InstrumentMaster.exchange == 'NSE',
                    InstrumentMaster.is_active == True
                ).distinct()
                result = await session.execute(stmt)
                fno_symbols = [row for row in result.scalars().all() if row]
                
                if fno_symbols:
                    self.stock_universe = sorted(fno_symbols)
                    logger.info(f"Loaded {len(self.stock_universe)} FnO stocks from DB")
                else:
                    logger.warning("No FnO stocks found in DB. Keeping default universe.")
        except Exception as e:
            logger.error(f"Error loading FnO universe: {e}")

    async def on_start(self):
        """Initialize resources and perform initial scan."""
        logger.info("EMOS Strategy starting...")
        
        # Load Universe if default
        # Compare sets to avoid order issues, or check if it matches default exactly
        default_universe = ['AMBER', 'TITAN', 'EICHERMOT', 'OIL', 'APOLLOHOSP']
        if set(self.stock_universe) == set(default_universe):
             logger.info("Using default stock universe. Attempting to load full FnO list from DB...")
             await self.load_fno_universe()

        if not await self.upstox.initialize():
            logger.error("Failed to initialize Upstox service for EMOS Strategy")
            return

        # Perform an initial scan or schedule it
        # specific logic to decide when to run could go here
        # For now, we'll log that it's ready
        logger.info("EMOS Strategy ready. Call run_daily_scan() to execute.")

    async def on_stop(self):
        """Cleanup resources."""
        await self.upstox.close()
        logger.info("EMOS Strategy stopped.")

    async def on_tick(self, tick: Any):
        """Not used for this daily strategy."""
        pass

    async def on_candle(self, candle: Any):
        """Not used for this daily strategy."""
        pass

    async def on_order_update(self, order: Any):
        """Log order updates."""
        logger.info(f"EMOS Strategy Order Update: {order}")

    async def fetch_earnings_calendar(self, days_ahead: int = 7) -> pd.DataFrame:
        """Fetch upcoming earnings using nsemine scraper."""
        if not self.nse:
            logger.warning("NSE scraper not available.")
            return pd.DataFrame()

        # Run blocking scraper in thread pool
        loop = asyncio.get_event_loop()
        try:
            events = await loop.run_in_executor(None, lambda: self.nse.get_events(days=days_ahead))
            # Filter for earnings and stock universe
            earnings = [
                e for e in events 
                if 'Earnings' in e.get('event_type', '') and e.get('symbol') in self.stock_universe
            ]
            return pd.DataFrame(earnings)
        except Exception as e:
            logger.error(f"Error fetching earnings calendar: {e}")
            return pd.DataFrame()

    def get_monthly_expiry(self, trade_date: date) -> date:
        """
        Get the monthly expiry date for the given trade date.
        Rule: Last Thursday of the month. If trade_date > last thursday, move to next month.
        """
        # 1. Start with current month
        curr_month = trade_date.replace(day=1)
        
        while True:
            # Find last day of month
            if curr_month.month == 12:
                next_month = curr_month.replace(year=curr_month.year+1, month=1)
            else:
                next_month = curr_month.replace(month=curr_month.month+1)
            last_day = next_month - timedelta(days=1)
            
            # Find last Thursday
            offset = (last_day.weekday() - 3) % 7 # 3 is Thursday
            last_thursday = last_day - timedelta(days=offset)
            
            if trade_date <= last_thursday:
                return last_thursday
            
            # Move to next month
            curr_month = next_month

    async def get_option_instrument(self, underlying: str, spot: float, type_: str, expiry: date) -> Optional[InstrumentMaster]:
        """
        Find the ATM option instrument from DB.
        Symbol Format: "TITAN 4360 CE 30 DEC 25"
        """
        try:
            async with AsyncSessionLocal() as session:
                # Format Expiry for Symbol Match: DD MMM YY
                # e.g. 26 FEB 26
                exp_str = expiry.strftime("%d %b %y").upper() 
                
                # Broad search for this expiry and type
                # We search for symbols containing Underlying AND Expiry AND Type
                # Pattern: "{UNDERLYING}%{TYPE}%{EXPIRY}" or "{UNDERLYING}%{EXPIRY}%{TYPE}"?
                # Seen: "TITAN 4360 CE 30 DEC 25" -> "{SYMBOL} {STRIKE} {TYPE} {EXPIRY}"
                
                stmt = select(InstrumentMaster).where(
                    InstrumentMaster.segment == 'FO', # Option segment could be NSE_FO or FO (from debug output 'FO')
                    InstrumentMaster.instrument_type == type_, # CE or PE
                    InstrumentMaster.trading_symbol.like(f"{underlying}%{type_}%{exp_str}")
                )
                
                result = await session.execute(stmt)
                options = result.scalars().all()
                
                if not options:
                    # Try alternate segment name or stricter query
                     stmt = select(InstrumentMaster).where(
                        InstrumentMaster.instrument_type == type_,
                        InstrumentMaster.trading_symbol.like(f"{underlying}%{type_}%{exp_str}")
                    )
                     result = await session.execute(stmt)
                     options = result.scalars().all()
                
                if not options:
                    # logger.warning(f"No {type_} options found for {underlying} exp {exp_str}")
                    return None

                # Find ATM Strike
                closest_opt = None
                min_diff = float('inf')
                
                for opt in options:
                    try:
                        # Extract strike from symbol: "TITAN 4360 CE ..."
                        parts = opt.trading_symbol.split()
                        # Verify structure
                        if parts[0] == underlying:
                            strike = float(parts[1])
                            diff = abs(spot - strike)
                            if diff < min_diff:
                                min_diff = diff
                                closest_opt = opt
                    except:
                        continue
                        
                return closest_opt

        except Exception as e:
            logger.error(f"Error finding option instrument: {e}")
            return None

    async def get_instrument_key(self, symbol: str) -> Optional[str]:
        """
        Resolve Upstox instrument key from DB.
        """
        try:
            async with AsyncSessionLocal() as session:
                 stmt = select(InstrumentMaster).where(
                    (InstrumentMaster.trading_symbol == symbol) |
                    (InstrumentMaster.trading_symbol == f"NSE:{symbol}")
                 ).limit(1)
                 result = await session.execute(stmt)
                 inst = result.scalar_one_or_none()
                 
                 if inst:
                     if inst.segment == 'NSE_EQ' and inst.isin:
                         return f"NSE_EQ|{inst.isin}"
                     # For Options, return None as we can't easily guess the key without more info
                     return None
        except Exception as e:
            logger.error(f"Error resolving instrument key: {e}")
        return None

    async def fetch_historical_data(self, symbol: str, interval='1minute', days_back=30, end_date: Optional[datetime] = None) -> Optional[pd.DataFrame]:
        """Fetch OHLC from Local DB or Upstox."""
        
        # 1. Try fetching from Local Database first
        try:
            async with AsyncSessionLocal() as session:
                # Get Instrument ID
                stmt_inst = select(InstrumentMaster).where(
                    (InstrumentMaster.trading_symbol == symbol) |
                    (InstrumentMaster.trading_symbol == f"NSE:{symbol}") | 
                    (InstrumentMaster.trading_symbol == f"NSE_EQ|{symbol}")
                ).limit(1)
                result_inst = await session.execute(stmt_inst)
                instrument = result_inst.scalar_one_or_none()
                
                if instrument:
                    # Parse dates
                    to_date = end_date if end_date else datetime.now()
                    from_date = to_date - timedelta(days=days_back)

                    
                    # Query CandleData
                    # Note: DB timeframe '1m'
                    db_timeframe = "1m" if interval == "1minute" else interval
                    if interval == 'day': db_timeframe = '1d'

                    # Ensure offset-aware timestamp for query
                    if from_date.tzinfo is None:
                        from_date = from_date.astimezone()
                    
                    logger.info(f"Querying DB for {symbol} ({db_timeframe}) >= {from_date}")

                    stmt_candle = select(CandleData).where(
                        CandleData.instrument_id == instrument.instrument_id,
                        CandleData.timeframe == db_timeframe,
                        CandleData.timestamp >= from_date
                    ).order_by(CandleData.timestamp)
                    
                    result_candle = await session.execute(stmt_candle)
                    candles = result_candle.scalars().all()
                    
                    if candles:
                        logger.info(f"Loaded {len(candles)} candles from DB for {symbol}")
                        data = [
                            {
                                "timestamp": c.timestamp,
                                "open": float(c.open),
                                "high": float(c.high),
                                "low": float(c.low),
                                "close": float(c.close),
                                "volume": c.volume,
                                "oi": c.oi
                            }
                            for c in candles
                        ]
                        return pd.DataFrame(data)
                    else:
                        # Fallthrough to fallback if not found in DB or empty
                        logger.warning(f"No candles in DB for {symbol} ({db_timeframe}) >= {from_date}")
                else:
                    logger.warning(f"Instrument not found in DB: {symbol}")
        except Exception as e:
            logger.error(f"Error fetching from DB: {e}")
        except Exception as e:
            logger.error(f"Error fetching from DB: {e}")

        # 2. Fallback to Upstox API
        instrument_key = await self.get_instrument_key(symbol)
        if not instrument_key:
            return None

        # Upstox V2 API expects 'day', '1minute', etc.
        to_date = end_date if end_date else datetime.now()
        from_date = to_date - timedelta(days=days_back)
        
        try:
            candles = await self.upstox.get_historical_data(
                instrument_key, 
                interval, 
                from_date.date(), 
                to_date.date()
            )
            
            if candles:
                # Convert list of HistoricalCandle to DataFrame
                data = [
                    {
                        "timestamp": c.timestamp,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                        "oi": c.oi
                    }
                    for c in candles
                ]
                df = pd.DataFrame(data)
                return df
                
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            
        # 3. Fallback to Fyers if Upstox fails
        try:
            logger.info(f"Falling back to Fyers for {symbol}")
            # Map resolution
            fyers_resolution = "1" 
            if interval == "day": 
                fyers_resolution = "D"
            elif interval == "1minute":
                fyers_resolution = "1"
            # Add other mappings if needed
            
            # Construct Fyers Symbol (Assuming NSE Equity if not specified)
            fyers_symbol = symbol
            if ":" not in symbol:
                fyers_symbol = f"NSE:{symbol}-EQ"
            
            # FyersBroker expects datetime objects
            # Ensure from_date and to_date are datetime
            f_start = from_date
            f_end = to_date
            
            # Call Fyers Broker
            # Note: broker.get_historical_data is async
            df = await self.broker.get_historical_data(
                symbol=fyers_symbol,
                resolution=fyers_resolution,
                start_date=f_start,
                end_date=f_end
            )
            
            if df is not None and not df.empty:
                logger.info(f"Fetched {len(df)} candles from Fyers for {symbol}")
                return df
                
        except Exception as e:
            logger.error(f"Error fetching from Fyers: {e}")

        return None

    async def analyze_sentiment(self, symbol: str) -> float:
        """Fetch sentiment score using SentimentAnalyzer service."""
        try:
            analyzer = get_sentiment_analyzer()
            sentiment = await analyzer.get_aggregate_sentiment(symbol)
            return sentiment.score
        except Exception as e:
            logger.error(f"Error analyzing sentiment for {symbol}: {e}")
            return 0.0

    async def generate_signals(self, earnings_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate trading signals based on earnings, momentum, and sentiment."""
        signals = []
        if earnings_df.empty:
            return signals

        today = datetime.now().date()
        # Default timing from config if not passed (though here we might need to rely on strategy attribute)
        # Using self.result_timing which we should add to __init__, or default to "After Market"
        timing = getattr(self, "result_timing", "After Market") 
        
        for _, row in earnings_df.iterrows():
            symbol = row.get('symbol')
            event_date_str = row.get('event_date') 
            
            # Parse Date
            if isinstance(event_date_str, str):
                try:
                    # Check format YYYY-MM-DD first (standard DB/ISO)
                    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        # Fallback for DD-MMM-YYYY
                        event_date = datetime.strptime(event_date_str, "%d-%b-%Y").date()
                    except ValueError:
                         logger.error(f"Could not parse date {event_date_str} for {symbol}")
                         continue
            else:
                event_date = event_date_str

            if not symbol or not event_date:
                continue

            # Determine Target Trade Date based on Result Timing
            if timing == "After Market":
                # User wants to trade ON Earnings Day Morning
                # So we look for Event Date == Today
                if event_date != today:
                    continue
                    
                # Check Time: Must be after 10:00 AM (Morning Momentum confirmed)
                now = datetime.now()
                if now.hour < 10:
                    # Too early
                    continue
                # If we are way past (e.g. 3 PM), maybe too late? 
                # Strategy says "Trade taken in the morning". 
                # Let's allow signal generation if we haven't traded yet? 
                # Ideally scheduler runs this periodically. 
                # We'll rely on idempotency elsewhere or assume scheduler calls this around 10:00-10:15.
                    
            else:
                # "Market" or "Pre-Market" Results
                # Trade on Previous Day (T-1)
                # So we look for Event Date == Tomorrow
                if event_date != today + timedelta(days=1):
                    continue

            # 1. Fetch Intraday Data for TODAY
            try:
                # Use Fyers or Upstox quote
                quote = await self.broker.get_quote(f"NSE:{symbol}-EQ")
                if not quote:
                    continue
                
                open_price = quote.open
                curr_price = quote.price
                
                if open_price == 0: continue
                
                # 2. Calculate Momentum (Intraday move)
                # For "After Market" (Today): This is Morning Move (Open to Current)
                # For "Market" (Tomorrow): This is Full Day Move (Open to Current) of T-1
                intraday_pct = (curr_price - open_price) / open_price
                
                # 3. Analyze Sentiment
                sentiment_score = await self.analyze_sentiment(symbol)
                
                # 4. Signal Logic
                signal_data = None
                
                # Log logic
                logger.info(f"Analyzing {symbol} for {timing} Earnings on {event_date}. Move: {intraday_pct:.2%}, Sent: {sentiment_score}")
                
                if intraday_pct > self.surprise_threshold and sentiment_score > self.sentiment_threshold_bullish:
                    signal_data = {
                        'symbol': symbol, 
                        'direction': 'Buy Call', 
                        'strike': 'ATM', 
                        'expiry': 'Monthly',
                        'spot_price': curr_price,
                        'reason': f"Momentum {intraday_pct:.2%}, Sentiment {sentiment_score:.2f} before Earnings on {event_date} ({timing})"
                    }
                elif intraday_pct < -self.surprise_threshold or sentiment_score < self.sentiment_threshold_bearish:
                    signal_data = {
                        'symbol': symbol, 
                        'direction': 'Buy Put', 
                        'strike': 'ATM', 
                        'expiry': 'Monthly',
                        'spot_price': curr_price,
                        'reason': f"Momentum {intraday_pct:.2%}, Sentiment {sentiment_score:.2f} before Earnings on {event_date} ({timing})"
                    }
                
                if signal_data:
                    signals.append(signal_data)
                    logger.info(f"Generated Signal for {symbol}: {signal_data}")
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {e}")
                
        return signals

    async def place_order(self, symbol: str, direction: str, qty: int, product_type='INTRADAY'):
        """Place order via Fyers Broker."""
        # Convert simple direction to OrderRequest parameters
        # Strategy wants 'Buy Call' or 'Buy Put'.
        # We need to resolve the Option Symbol (e.g. NSE:SBIN24FEB40000CE)
        # For simplicity in this integration step, we will place Equity orders if Option resolution is complex,
        # OR we assume 'symbol' passed here is already the Option Symbol if resolved.
        # But generate_signals returns 'symbol': 'AMBER' (Underlying)
        
        # User Code Logic:
        # "symbol": f"NSE:{symbol}-EQ"  # Adjust for options: e.g., NSE:SBIN24FEB40000CE
        
        # If we stick to Equity for now as per the Fyers OrderRequest structure matching:
        side = "BUY" if "Buy" in direction else "SELL" # User logic was Buy Call/Put -> Side 1 (-1?). Wrapper uses "BUY"/"SELL"
        # Wait, if Buy Put -> Long Put. Wrapper place_order takes 'side'.
        # If we are buying options, side is always BUY. The instrument determines Call or Put.
        
        # NOTE: This implementation assumes we are trading the UNDERLYING for now as Option Symbol resolution 
        # requires complex lookup (Expiry, ATM Strike calculation).
        # We will log a warning and trade Equity for the specific direction provided if it makes sense (Long/Short),
        # but User code clearly says "side = 1 if 'Call' in direction else -1".
        # This implies user was treating 'Buy Put' as Sell Underlying? OR buying the Put option?
        # "1 if 'Call' in direction else -1" -> If Call=1 (Buy), If Put=-1 (Sell).
        # This simplifies to Directional trading on the Underlying.
        
        final_side = "BUY" if "Call" in direction else "SELL"
        
        order_request = OrderRequest(
            symbol=f"NSE:{symbol}-EQ",
            quantity=qty,
            side=final_side,
            order_type="MARKET",
            price=0.0,
            product_type=product_type
        )
        
        logger.info(f"Placing order: {order_request}")
        response = await self.broker.place_order(order_request)
        return response

    async def run_daily_scan(self):
        """Execute the full strategy workflow."""
        logger.info("Running EMOS Daily Scan...")
        
        # 1. Earnings
        earnings = await self.fetch_earnings_calendar(self.days_ahead)
        if earnings.empty:
            logger.info("No earnings events found in universe.")
            return []

        # 2. Signals
        signals = await self.generate_signals(earnings)
        if not signals:
            logger.info("No trading signals generated.")
            return []

        # 3. Execution
        trades = []
        for sig in signals:
            # Position Sizing
            position_size = self.capital * self.risk_per_trade
            # Get LTP to calculate Qty?
            # Creating a helper or fetching quote
            quote = await self.broker.get_quote(f"NSE:{sig['symbol']}-EQ")
            price = quote.price if quote and quote.price > 0 else 1000 # Fallback safety
            
            qty = max(1, int(position_size / price))
            
            # Place Order
            response = await self.place_order(sig['symbol'], sig['direction'], qty)
            trades.append(response)
            
        logger.info(f"EMOS Scan Completed. {len(trades)} trades executed.")
        return trades

    async def backtest(self, start_date: datetime, end_date: datetime, earnings_map: Optional[Dict[str, List[datetime]]] = None, result_timing: str = "After Market") -> Dict[str, Any]:
        """
        Backtest the strategy on historical data.
        
        Args:
            start_date: Start of backtest period
            end_date: End of backtest period
            earnings_map: Optional dict of {symbol: [earnings_date1]}
            result_timing: 'After Market' (Trade on E Morning) or 'Market'/'Pre-Market' (Trade on E-1 Close)
        """
        logger.info(f"Starting EMOS Backtest from {start_date} to {end_date} (Timing: {result_timing})")
        
        trades = []
        total_pnl = 0.0
        wins = 0
        losses = 0
        
        universe = list(earnings_map.keys()) if earnings_map else self.stock_universe
        
        for symbol in universe:
            # Fetch historical data (1-minute interval)
            # Need data covering E-1 and E
            hist_df = await self.fetch_historical_data(
                symbol, 
                days_back=(datetime.now() - start_date).days + 45
            )
            
            if hist_df is None or hist_df.empty:
                logger.warning(f"No historical data for {symbol}")
                continue
            
            logger.info(f"Fetched Data Range: {hist_df['timestamp'].min()} to {hist_df['timestamp'].max()} (rows: {len(hist_df)})")
            
            # Ensure proper datetime index or column for filtering
            # hist_df['timestamp'] is mostly UTC aware from DB
            
            # Identify Trade Opportunities
            events_to_test = []

            # Ensure start_date/end_date are tz-aware for comparison with DB data (which is UTC or aware)
            tz = hist_df['timestamp'].dt.tz
            if tz is not None:
                if start_date.tzinfo is None:
                    # Assume input naive dates are local/UTC, convert to match DF
                    # Usually DB is UTC. If start_date is naive, pd.Timestamp might treat as local.
                    # Safest is to localize to the DF's timezone.
                    start_ts = pd.Timestamp(start_date).tz_localize(tz)
                    end_ts = pd.Timestamp(end_date).tz_localize(tz)
                else:
                    start_ts = pd.Timestamp(start_date).tz_convert(tz)
                    end_ts = pd.Timestamp(end_date).tz_convert(tz)
            else:
                # DF is naive, use naive
                start_ts = pd.Timestamp(start_date)
                end_ts = pd.Timestamp(end_date)
            
            if earnings_map and symbol in earnings_map:
                # Use provided specific dates
                for e_date in earnings_map[symbol]:
                    # e_date might be naive date or datetime
                    e_ts = pd.Timestamp(e_date)
                    # Use date comparison to avoid timezone mess for "Day" check?
                    # Ideally we store full timestamps
                    # If just date, we accept it.
                    e_date_obj = e_ts.date()
                    if start_ts.date() <= e_date_obj <= end_ts.date():
                        events_to_test.append(e_ts)
            else:
                pass

            # Execute Logic for each Earnings Event
            for event_ts in events_to_test:
                event_date = event_ts.date()
                
                # Determine Reference Day (T) and Entry/Exit Times
                
                entry_time = None
                exit_time = None
                signal = None
                move_pct = 0.0
                spot_entry = 0.0
                spot_exit = 0.0
                
                if result_timing == "After Market":
                    # Trade on Day E (event_date)
                    # Check Morning Momentum: 09:15 to 10:00
                    
                    # Filter data for Event Date
                    day_rows = hist_df[hist_df['timestamp'].dt.date == event_date]
                    if day_rows.empty:
                        logger.warning(f"No data for Event Day {event_date}")
                        continue
                    
                    # Convert to IST for time filtering
                    day_rows_ist = day_rows.copy()
                    day_rows_ist['timestamp'] = day_rows_ist['timestamp'].dt.tz_convert('Asia/Kolkata')
                    
                    # Define Morning Window (9:15 - 10:00)
                    morning_start = day_rows_ist['timestamp'].iloc[0].replace(hour=9, minute=15, second=0, microsecond=0)
                    morning_end = day_rows_ist['timestamp'].iloc[0].replace(hour=10, minute=0, second=0, microsecond=0)
                    
                    morning_data = day_rows_ist[(day_rows_ist['timestamp'] >= morning_start) & (day_rows_ist['timestamp'] <= morning_end)]
                    
                    if morning_data.empty:
                        logger.warning(f"No morning data for {event_date}")
                        continue
                        
                    open_price = morning_data.iloc[0]['open']
                    curr_price = morning_data.iloc[-1]['close'] # Price at 10:00
                    
                    # Momentum Calculation
                    move_pct = (curr_price - open_price) / open_price
                    
                    # Entry/Exit
                    entry_time = morning_data.iloc[-1]['timestamp']
                    # Exit at EOD (e.g. 15:15 or last candle)
                    market_end = day_rows_ist['timestamp'].iloc[0].replace(hour=15, minute=15, second=0, microsecond=0)
                    exit_data = day_rows_ist[day_rows_ist['timestamp'] >= market_end]
                    
                    if not exit_data.empty:
                         exit_row = exit_data.iloc[0] # Exit at 15:15 candle?
                    else:
                         exit_row = day_rows_ist.iloc[-1] # User last candle
                         
                    exit_time = exit_row['timestamp']
                    spot_entry = curr_price
                    spot_exit = exit_row['close']

                else:
                    # 'Market': Trade on E-1 Close
                    prev_days = hist_df[hist_df['timestamp'].dt.date < event_date]
                    if prev_days.empty: continue
                    
                    # Last day before E
                    t_date = prev_days.iloc[-1]['timestamp'].date()
                    t_rows = hist_df[hist_df['timestamp'].dt.date == t_date]
                    
                    # Verify gap
                    if (event_date - t_date).days > 5: continue
                    
                    t_open = t_rows.iloc[0]['open']
                    t_close = t_rows.iloc[-1]['close']
                    
                    move_pct = (t_close - t_open) / t_open
                    
                    # Entry/Exit
                    entry_time = t_rows.iloc[-1]['timestamp']
                    # Exit at E Close
                    e_rows = hist_df[hist_df['timestamp'].dt.date == event_date]
                    if e_rows.empty: continue
                    
                    spot_entry = t_close
                    spot_exit = e_rows.iloc[-1]['close']
                    exit_time = e_rows.iloc[-1]['timestamp']

                # Generate Signal
                sentiment_score = 0.7 if move_pct > 0 else 0.3 # Mock
                
                if move_pct > self.surprise_threshold and sentiment_score > self.sentiment_threshold_bullish:
                    signal = "Buy Call"
                    side = "CE"
                elif move_pct < -self.surprise_threshold or sentiment_score < self.sentiment_threshold_bearish:
                    signal = "Buy Put"
                    side = "PE"
                else:
                    continue # No trade
                
                logger.info(f"Signal ({result_timing}): {signal} on {entry_time} (Move: {move_pct:.2%})")
                
                # --- PnL Calculation (Actual Option Data) ---
                trade_pnl = 0.0
                option_ret = 0.0
                option_symbol = "N/A"
                
                # 1. Determine Expiry (Monthly)
                trade_date_obj = entry_time.date()
                expiry_date = self.get_monthly_expiry(trade_date_obj)
                
                # 2. Get Option Instrument
                opt_inst = await self.get_option_instrument(symbol, spot_entry, side, expiry_date)
                
                option_entry_px = 0.0
                option_exit_px = 0.0
                
                if opt_inst:
                    option_symbol = opt_inst.trading_symbol
                    
                    # 3. Fetch Option Candles
                    # We need data at Entry Time and Exit Time
                    # We can use fetch_historical_data but we need to query by instrument_id ideally or symbol
                    # Our fetch_historical_data takes symbol and looks up ID. PASS option_symbol.
                    
                    # Be careful: fetch_historical_data parses "NSE:{symbol}"
                    # Option symbol "TITAN ..." might not have NSE prefix in logic or DB lookup
                    # Let's fix fetch_historical_data or just trust it handles "TITAN..." in 'trading_symbol' lookup
                    
                    opt_hist = await self.fetch_historical_data(option_symbol, days_back=5, end_date=entry_time) # 5 days back from entry is enough
                    
                    if opt_hist is not None and not opt_hist.empty:
                        # Find Entry Price
                        # Match timestamp closest to entry_time
                        # Ensure opt_hist timestamps are tz aware matching entry_time
                        
                        # Just to be safe with merge/lookup
                        # Find row with timestamp nearest to entry_time
                        
                        # Note: Option data might be sparse or slightly offset
                        # Use searchsorted or get_indexer with method='nearest'
                        
                        # Convert to same TZ
                        tz_opt = opt_hist['timestamp'].dt.tz
                        if tz_opt != entry_time.tzinfo:
                             entry_time_lookup = entry_time.tz_convert(tz_opt)
                             exit_time_lookup = exit_time.tz_convert(tz_opt)
                        else:
                             entry_time_lookup = entry_time
                             exit_time_lookup = exit_time
                             
                        # Find closest indexes
                        idx_entry = opt_hist['timestamp'].searchsorted(entry_time_lookup)
                        idx_exit = opt_hist['timestamp'].searchsorted(exit_time_lookup)
                        
                        # Bounds check
                        if idx_entry < len(opt_hist):
                             option_entry_px = opt_hist.iloc[idx_entry]['close'] # Use close of candle near entry
                             # If entry candle is way off?
                             time_diff = abs(opt_hist.iloc[idx_entry]['timestamp'] - entry_time_lookup)
                             if time_diff.total_seconds() > 3600: # If > 1 hour gap, data missing?
                                  logger.warning(f"Option Entry Data gap for {option_symbol}: {time_diff}")
                                  option_entry_px = 0 # Fallback
                             
                        if idx_exit < len(opt_hist):
                             option_exit_px = opt_hist.iloc[idx_exit]['close']
                        elif idx_exit >= len(opt_hist) and not opt_hist.empty:
                             option_exit_px = opt_hist.iloc[-1]['close'] # Use last available
                             
                        # Calculate PnL if we found prices
                        if option_entry_px > 0 and option_exit_px > 0:
                            option_ret = (option_exit_px - option_entry_px) / option_entry_px
                            invested = self.capital * self.risk_per_trade
                            
                            # Real quantity logic?
                            # Lot size is needed. opt_inst.lot_size
                            lot_size = opt_inst.lot_size
                            # How many lots can we buy with Risk Capital?
                            # Or usually Position Size = Capital * Risk
                            # Num Lots = Amount / (Price * LotSize)
                            
                            trade_val = invested
                            qty_contracts = max(1, int(trade_val / (option_entry_px * lot_size))) * lot_size
                            # Actually, normally we buy 1 Lot for testing or fixed risk?
                            # Let's assume we invest 'invested' amount roughly.
                            
                            trade_pnl = (option_exit_px - option_entry_px) * qty_contracts
                            trade_pnl -= 50 # Comm
                            
                            logger.info(f"Option Trade ({option_symbol}): Entry {option_entry_px} -> Exit {option_exit_px} | Qty: {qty_contracts} | PnL: {trade_pnl}")
                        else:
                             logger.warning(f"Could not find valid option prices for {option_symbol}. Falling back to proxy.")
                             option_symbol = f"{option_symbol} (No Data)"
                    else:
                         logger.warning(f"No historical data for option {option_symbol}")
                else:
                    logger.warning(f"No Option Instrument found for {symbol} {side} {expiry_date}")
                
                # Fallback to Proxy if PnL is 0 (and entry wasn't 0) OR if we didn't find option
                if trade_pnl == 0.0 and option_entry_px == 0.0:
                    underlying_move_pct = (spot_exit - spot_entry) / spot_entry
                    leverage = 5.0 
                    if signal == "Buy Call":
                        option_ret = underlying_move_pct * leverage
                    else:
                        option_ret = -underlying_move_pct * leverage
                        
                    if option_ret < -1.0: option_ret = -1.0
                    
                    invested = self.capital * self.risk_per_trade
                    trade_pnl = invested * option_ret
                    trade_pnl -= 50
                    option_symbol = "PROXY"

                
                trades.append({
                    "symbol": symbol,
                    "event_date": event_date,
                    "entry_date": entry_time, 
                    "direction": signal,
                    "underlying_entry": spot_entry,
                    "underlying_exit": spot_exit,
                    "underlying_move": (spot_exit - spot_entry) / spot_entry,
                    "option_symbol": option_symbol,
                    "option_entry": option_entry_px,
                    "option_exit": option_exit_px,
                    "est_option_ret": option_ret,
                    "pnl": trade_pnl
                })
                
                total_pnl += trade_pnl
                if trade_pnl > 0: wins += 1
                else: losses += 1
                    
        num_trades = len(trades)
        win_rate = (wins / num_trades) if num_trades > 0 else 0.0
        
        results = {
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 2),
            "num_trades": num_trades,
            "trades": trades 
        }
        
        logger.info(f"Backtest Complete. PnL: {total_pnl:.2f}, Win Rate: {win_rate:.2%}")
        return results
