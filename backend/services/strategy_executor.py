"""
Strategy Execution Engine
Manages strategy execution with automatic mode switching based on available funds
"""
import asyncio
import asyncpg
import subprocess
import sys
import os
from datetime import datetime, date, time as dt_time, timedelta
from typing import Optional, Dict, List
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StrategyMode(str, Enum):
    LIVE = "live"
    PAPER = "paper"
    STOPPED = "stopped"

class StrategyStatus:
    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.mode = StrategyMode.LIVE
        self.is_running = False
        self.auto_switched = False
        self.switch_reason = None
        self.available_funds = 0
        self.required_funds_per_trade = 50000  # ₹50K default
        self.active_positions = []
        
    def check_funds_and_switch(self):
        """Auto-switch to paper mode if insufficient funds"""
        if self.mode == StrategyMode.LIVE and self.available_funds < self.required_funds_per_trade:
            logger.warning(f"Insufficient funds for {self.strategy_name}. Switching to paper mode.")
            self.mode = StrategyMode.PAPER
            self.auto_switched = True
            self.switch_reason = f"Insufficient funds. Available: ₹{self.available_funds:,.0f}, Required: ₹{self.required_funds_per_trade:,.0f}"
            return True
        return False
    
    def to_dict(self):
        return {
            "strategy_name": self.strategy_name,
            "mode": self.mode.value,
            "is_running": self.is_running,
            "auto_switched": self.auto_switched,
            "switch_reason": self.switch_reason,
            "available_funds": self.available_funds,
            "required_funds": self.required_funds_per_trade,
            "active_positions": len(self.active_positions)
        }

class StrategyExecutor:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
        self.strategies: Dict[str, StrategyStatus] = {}
        self.running = False
        
    async def connect(self):
        """Connect to database"""
        self.pool = await asyncpg.create_pool(self.db_url)
        logger.info("Connected to database")
        
    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection closed")
    
    async def sync_latest_data(self, force: bool = False) -> Dict:
        """
        Download latest missing data from Upstox.
        
        Automatically detects missing/stale data and downloads updates for:
        - Current & equity instruments for trading
        
        Args:
            force: If True, runs sync even if data appears recent
            
        Returns:
            Dict with sync status and statistics
        """
        result = {
            'status': 'checking',
            'data_current': True,
            'last_data_date': None,
            'synced': False,
            'details': {}
        }
        
        try:
            # Check if we have recent data
            async with self.pool.acquire() as conn:
                # Get the most recent data date for active equity instruments
                last_data = await conn.fetchrow("""
                    SELECT MAX(s.last_date) as last_date, COUNT(*) as instruments_with_data
                    FROM candle_data_summary s
                    JOIN instrument_master im ON s.instrument_id = im.instrument_id
                    WHERE im.instrument_type = 'EQUITY' AND im.is_active = true
                """)
                
                if last_data and last_data['last_date']:
                    result['last_data_date'] = str(last_data['last_date'])
                    result['instruments_with_data'] = last_data['instruments_with_data']
                    
                    # Check if data is stale (more than 1 day old, accounting for weekends)
                    today = date.today()
                    data_date = last_data['last_date']
                    
                    # Calculate expected last trading day (exclude weekends)
                    expected_date = today
                    if today.weekday() == 0:  # Monday
                        expected_date = today - timedelta(days=3)  # Last Friday
                    elif today.weekday() == 6:  # Sunday
                        expected_date = today - timedelta(days=2)  # Last Friday
                    elif today.weekday() == 5:  # Saturday
                        expected_date = today - timedelta(days=1)  # Last Friday
                    else:
                        expected_date = today - timedelta(days=1)  # Yesterday
                    
                    if data_date >= expected_date and not force:
                        result['status'] = 'up_to_date'
                        result['data_current'] = True
                        logger.info(f"Data is current (last: {data_date})")
                        return result
                    else:
                        result['data_current'] = False
                        logger.info(f"Data is stale (last: {data_date}, expected: {expected_date})")
                else:
                    result['data_current'] = False
                    result['last_data_date'] = None
                    logger.warning("No data found in database")
            
            # Run backfill script for current expiry and equity data
            logger.info("Starting data sync...")
            result['status'] = 'syncing'
            
            # Get the script path
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            backfill_script = os.path.join(script_dir, 'scripts', 'backfill_all_data.py')
            
            if not os.path.exists(backfill_script):
                result['status'] = 'error'
                result['error'] = f"Backfill script not found: {backfill_script}"
                logger.error(result['error'])
                return result
            
            # Run equity sync first (usually faster)
            logger.info("Syncing equity data...")
            equity_result = subprocess.run(
                [sys.executable, backfill_script, '--mode', 'equity'],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            result['details']['equity'] = {
                'returncode': equity_result.returncode,
                'success': equity_result.returncode == 0
            }
            
            # Then sync current F&O expiries
            logger.info("Syncing F&O data...")
            fo_result = subprocess.run(
                [sys.executable, backfill_script, '--mode', 'current'],
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            result['details']['current_fo'] = {
                'returncode': fo_result.returncode,
                'success': fo_result.returncode == 0
            }
            
            # Determine overall status
            if equity_result.returncode == 0 and fo_result.returncode == 0:
                result['status'] = 'completed'
                result['synced'] = True
                logger.info("Data sync completed successfully")
            else:
                result['status'] = 'partial'
                result['synced'] = True
                logger.warning("Data sync completed with some errors")
                
        except subprocess.TimeoutExpired:
            result['status'] = 'timeout'
            result['error'] = 'Sync operation timed out'
            logger.error("Data sync timed out")
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            logger.error(f"Data sync failed: {e}")
        
        return result
    
    async def register_strategy(self, strategy_name: str, required_funds: int = 50000):
        """Register a new strategy"""
        status = StrategyStatus(strategy_name)
        status.required_funds_per_trade = required_funds
        self.strategies[strategy_name] = status
        logger.info(f"Registered strategy: {strategy_name}")
        return status
    
    async def update_available_funds(self, strategy_name: str, funds: float):
        """Update available funds for a strategy"""
        if strategy_name in self.strategies:
            self.strategies[strategy_name].available_funds = funds
            # Check if mode switch is needed
            self.strategies[strategy_name].check_funds_and_switch()
    
    async def set_strategy_mode(self, strategy_name: str, mode: StrategyMode):
        """Manually set strategy mode"""
        if strategy_name in self.strategies:
            status = self.strategies[strategy_name]
            
            # If switching to live, check funds first
            if mode == StrategyMode.LIVE:
                if status.available_funds < status.required_funds_per_trade:
                    logger.warning(f"Cannot switch {strategy_name} to live mode: insufficient funds")
                    status.mode = StrategyMode.PAPER
                    status.auto_switched = True
                    status.switch_reason = "Insufficient funds for live trading"
                    return False
            
            status.mode = mode
            status.auto_switched = False
            status.switch_reason = None
            logger.info(f"Strategy {strategy_name} mode set to {mode.value}")
            return True
        return False
    
    async def start_strategy(self, strategy_name: str):
        """Start strategy execution"""
        if strategy_name in self.strategies:
            self.strategies[strategy_name].is_running = True
            logger.info(f"Started strategy: {strategy_name}")
            # Start background task for this strategy
            asyncio.create_task(self._run_strategy(strategy_name))
            return True
        return False
    
    async def stop_strategy(self, strategy_name: str):
        """Stop strategy execution"""
        if strategy_name in self.strategies:
            self.strategies[strategy_name].is_running = False
            self.strategies[strategy_name].mode = StrategyMode.STOPPED
            logger.info(f"Stopped strategy: {strategy_name}")
            return True
        return False
    
    async def _run_strategy(self, strategy_name: str):
        """Background task to run strategy"""
        status = self.strategies[strategy_name]
        
        while status.is_running:
            try:
                # Check funds before each trade
                status.check_funds_and_switch()
                
                # Get current time
                now = datetime.now().time()
                
                # Only trade during market hours (9:15 AM - 3:30 PM)
                if dt_time(9, 15) <= now <= dt_time(15, 30):
                    # Check for entry signals
                    await self._check_entry_signals(strategy_name)
                    
                    # Manage existing positions
                    await self._manage_positions(strategy_name)
                
                # Sleep for 1 minute before next check
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in strategy {strategy_name}: {e}")
                await asyncio.sleep(60)
    
    async def _check_entry_signals(self, strategy_name: str):
        """Morning Momentum Alpha - Check for entry signals at 9:30 AM."""
        status = self.strategies[strategy_name]
        now = datetime.now()
        
        # Only check at 9:30 AM IST (entry time window: 9:25-9:35 AM)
        if not (dt_time(9, 25) <= now.time() <= dt_time(9, 35)):
            return
        
        logger.info(f"[SCAN] Starting signal scan at {now.strftime('%H:%M:%S')} in {status.mode.value} mode")
        
        # Skip if already have max positions
        if len(status.active_positions) >= 3:  # Max 3 positions
            logger.info(f"[SCAN] Max positions reached ({len(status.active_positions)}/3), skipping scan")
            return
        
        # Get list of F&O stocks to scan
        stocks = await self._get_fno_stocks()
        logger.info(f"[SCAN] Scanning {len(stocks[:50])} stocks...")
        
        signals_found = 0
        stocks_scanned = 0
        
        for stock in stocks[:50]:  # Scan top 50 stocks
            try:
                stocks_scanned += 1
                
                # Get opening data (first 15 minutes)
                spot_open = await self._get_spot_open(stock)
                spot_current = await self._get_spot_current(stock)
                
                if not spot_open or not spot_current:
                    logger.debug(f"[{stock}] No spot data")
                    continue
                
                # Calculate early momentum
                momentum_pct = ((spot_current - spot_open) / spot_open) * 100
                
                # Check momentum > 0.5% (bullish) or < -0.5% (bearish)
                if abs(momentum_pct) < 0.5:
                    logger.debug(f"[{stock}] Low momentum: {momentum_pct:+.2f}%")
                    continue
                
                # Determine option type based on momentum direction
                option_type = "CE" if momentum_pct > 0 else "PE"
                
                # Find ATM strike (round to nearest 50/100 based on price)
                strike_step = 50 if spot_current < 1000 else 100 if spot_current < 5000 else 500
                atm_strike = round(spot_current / strike_step) * strike_step
                
                # Check if spot is within 2% of ATM
                distance_to_atm_pct = abs((spot_current - atm_strike) / atm_strike) * 100
                if distance_to_atm_pct > 2.0:
                    logger.debug(f"[{stock}] Too far from ATM: {distance_to_atm_pct:.2f}%")
                    continue
                
                # Get option premium
                option_symbol = f"{stock} {atm_strike} {option_type}"
                option_premium = await self._get_option_premium(stock, atm_strike, option_type)
                
                if not option_premium or option_premium <= 0:
                    logger.debug(f"[{stock}] No option premium for {option_symbol}")
                    continue
                
                # Check if option has volume
                option_volume = await self._get_option_volume(stock, atm_strike, option_type)
                if option_volume <= 0:
                    logger.debug(f"[{stock}] No option volume for {option_symbol}")
                    continue
                
                # All conditions passed - generate signal!
                signals_found += 1
                logger.info(f"✅ SIGNAL #{signals_found}: {stock} {atm_strike} {option_type}")
                logger.info(f"   Momentum: {momentum_pct:+.2f}% | Spot: {spot_open:.2f}→{spot_current:.2f} | Premium: ₹{option_premium:.2f}")
                
                trade_data = {
                    "stock": stock,
                    "strike": atm_strike,
                    "option_type": option_type,
                    "entry_premium": option_premium,
                    "entry_spot": spot_current,
                    "momentum_pct": momentum_pct,
                    "target_pct": 50.0,  # 50% target
                    "stoploss_pct": 40.0,  # 40% SL
                    "time_stop": dt_time(14, 30),  # 2:30 PM exit
                }
                
                # Execute trade (live or paper)
                result = await self.execute_trade(strategy_name, trade_data)
                
                if result.get("success"):
                    logger.info(f"   Trade executed in {result.get('mode')} mode, Order: {result.get('order_id')}")
                    status.active_positions.append({
                        **trade_data,
                        "entry_time": now,
                        "order_id": result.get("order_id"),
                        "mode": result.get("mode")
                    })
                else:
                    logger.warning(f"   Trade failed: {result.get('error')}")
                    
            except Exception as e:
                logger.error(f"[{stock}] Error: {e}")
                continue
        
        logger.info(f"[SCAN] Complete: Scanned {stocks_scanned} stocks, Found {signals_found} signals")
    
    async def _manage_positions(self, strategy_name: str):
        """Morning Momentum Alpha - Manage positions with Target/SL/Time exits."""
        status = self.strategies[strategy_name]
        now = datetime.now()
        
        positions_to_close = []
        
        for i, pos in enumerate(status.active_positions):
            try:
                stock = pos["stock"]
                entry_premium = pos["entry_premium"]
                target_pct = pos.get("target_pct", 50.0)
                stoploss_pct = pos.get("stoploss_pct", 40.0)
                time_stop = pos.get("time_stop", dt_time(14, 30))
                
                # Get current option premium
                current_premium = await self._get_option_premium(
                    stock, pos["strike"], pos["option_type"]
                )
                
                if not current_premium:
                    continue
                
                # Calculate P&L percentage
                pnl_pct = ((current_premium - entry_premium) / entry_premium) * 100
                
                exit_reason = None
                
                # Check Target (50% profit)
                if pnl_pct >= target_pct:
                    exit_reason = f"Target ({target_pct}%)"
                
                # Check Stop Loss (40% loss)
                elif pnl_pct <= -stoploss_pct:
                    exit_reason = f"Stop Loss ({stoploss_pct}%)"
                
                # Check Time Stop (2:30 PM)
                elif now.time() >= time_stop:
                    exit_reason = f"Time Stop ({time_stop.strftime('%H:%M')})"
                
                if exit_reason:
                    logger.info(f"EXIT: {stock} {pos['option_type']} | P&L: {pnl_pct:.2f}% | Reason: {exit_reason}")
                    
                    # Close position
                    close_result = await self._close_position(strategy_name, pos, current_premium, exit_reason)
                    
                    if close_result.get("success"):
                        positions_to_close.append(i)
                        
            except Exception as e:
                logger.error(f"Error managing position {pos}: {e}")
        
        # Remove closed positions (in reverse order to preserve indices)
        for i in reversed(positions_to_close):
            del status.active_positions[i]
    
    async def _close_position(self, strategy_name: str, position: Dict, exit_premium: float, exit_reason: str):
        """Close a position and log the result."""
        status = self.strategies[strategy_name]
        
        entry_premium = position["entry_premium"]
        pnl_pct = ((exit_premium - entry_premium) / entry_premium) * 100
        
        trade_result = {
            **position,
            "exit_time": datetime.now(),
            "exit_premium": exit_premium,
            "pnl_pct": pnl_pct,
            "exit_reason": exit_reason
        }
        
        # Log to database
        await self._log_exit(strategy_name, trade_result)
        
        # Update funds if it was a live trade
        if position.get("mode") == "live":
            # Simplified: assume position value was required_funds
            profit = (pnl_pct / 100) * status.required_funds_per_trade
            status.available_funds += status.required_funds_per_trade + profit
        
        return {"success": True, "pnl_pct": pnl_pct, "exit_reason": exit_reason}
    
    async def _log_exit(self, strategy_name: str, trade_result: Dict):
        """Log exit to database."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE strategy_trades 
                    SET exit_time = $1, exit_premium = $2, pnl_pct = $3, exit_reason = $4
                    WHERE strategy_name = $5 AND stock = $6 AND entry_time = $7
                """, 
                trade_result["exit_time"],
                trade_result["exit_premium"],
                trade_result["pnl_pct"],
                trade_result["exit_reason"],
                strategy_name,
                trade_result["stock"],
                trade_result["entry_time"]
                )
        except Exception as e:
            logger.error(f"Error logging exit: {e}")
    
    async def execute_trade(self, strategy_name: str, trade_data: Dict):
        """Execute a trade (live or paper)"""
        if strategy_name not in self.strategies:
            return {"success": False, "error": "Strategy not found"}
        
        status = self.strategies[strategy_name]
        
        if status.mode == StrategyMode.LIVE:
            # Execute real trade via broker API
            result = await self._execute_live_trade(trade_data)
        elif status.mode == StrategyMode.PAPER:
            # Simulate trade
            result = await self._execute_paper_trade(trade_data)
        else:
            return {"success": False, "error": "Strategy is stopped"}
        
        # Log trade to database
        await self._log_trade(strategy_name, trade_data, result)
        return result
    
    async def _execute_live_trade(self, trade_data: Dict):
        """Execute real trade via Fyers broker."""
        try:
            # Import broker here to avoid circular imports
            import sys
            sys.path.insert(0, '../app')
            from app.brokers.fyers import FyersBroker
            from app.schemas.broker import OrderRequest
            
            broker = FyersBroker()
            
            # Authenticate
            is_connected = await broker.authenticate()
            if not is_connected:
                logger.error("Failed to connect to Fyers broker")
                return {"success": False, "mode": "live", "error": "Broker connection failed"}
            
            # Construct option symbol for Fyers
            # Format: NSE:RELIANCE25DEC1300CE
            stock = trade_data["stock"]
            strike = trade_data["strike"]
            option_type = trade_data["option_type"]
            
            # Get nearest weekly/monthly expiry - simplified for now
            from datetime import datetime
            now = datetime.now()
            # Find next Thursday (weekly expiry)
            days_until_thursday = (3 - now.weekday()) % 7
            if days_until_thursday == 0 and now.hour >= 15:
                days_until_thursday = 7
            expiry_date = now + timedelta(days=days_until_thursday)
            expiry_str = expiry_date.strftime("%d%b").upper()  # e.g., "26DEC"
            
            option_symbol = f"NSE:{stock}{expiry_str.replace(' ', '')}{strike}{option_type}"
            
            logger.info(f"Placing LIVE order: {option_symbol} BUY")
            
            # Calculate quantity (1 lot for now)
            quantity = 1  # Will need lot size lookup for proper implementation
            
            order = OrderRequest(
                symbol=option_symbol,
                quantity=quantity,
                side="BUY",
                order_type="MARKET",
                price=None
            )
            
            result = await broker.place_order(order)
            
            if result.status.value == "PENDING" or result.status.value == "FILLED":
                logger.info(f"LIVE order placed: {result.order_id}")
                return {
                    "success": True, 
                    "mode": "live", 
                    "order_id": result.order_id,
                    "symbol": option_symbol
                }
            else:
                logger.error(f"LIVE order failed: {result.message}")
                return {
                    "success": False, 
                    "mode": "live", 
                    "error": result.message
                }
                
        except Exception as e:
            logger.error(f"Error executing live trade: {e}")
            return {"success": False, "mode": "live", "error": str(e)}
    
    async def _execute_paper_trade(self, trade_data: Dict):
        """Simulate paper trade with realistic logging."""
        import time
        
        stock = trade_data["stock"]
        strike = trade_data["strike"]
        option_type = trade_data["option_type"]
        premium = trade_data["entry_premium"]
        
        # Generate paper order ID
        paper_order_id = f"PAPER_{stock}_{int(time.time())}"
        
        logger.info(f"📝 PAPER TRADE: {stock} {strike} {option_type} @ ₹{premium:.2f}")
        
        return {
            "success": True, 
            "mode": "paper", 
            "order_id": paper_order_id,
            "symbol": f"{stock} {strike} {option_type}"
        }
    
    async def _log_trade(self, strategy_name: str, trade_data: Dict, result: Dict):
        """Log trade to database"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO strategy_trades 
                (strategy_name, trade_date, stock, strike, option_type, 
                 entry_time, entry_premium, trade_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, 
            strategy_name,
            datetime.now().date(),
            trade_data.get('stock'),
            trade_data.get('strike'),
            trade_data.get('option_type'),
            datetime.now(),
            trade_data.get('entry_premium'),
            result.get('mode')
            )
    
    def get_strategy_status(self, strategy_name: str) -> Optional[Dict]:
        """Get current status of a strategy"""
        if strategy_name in self.strategies:
            return self.strategies[strategy_name].to_dict()
        return None
    
    def get_all_strategies(self) -> List[Dict]:
        """Get status of all strategies"""
        return [status.to_dict() for status in self.strategies.values()]
    
    # ==================== DATA HELPER METHODS ====================
    
    async def _get_fno_stocks(self) -> List[str]:
        """Get list of F&O stocks to scan."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT trading_symbol 
                    FROM instrument_master 
                    WHERE segment = 'FO' AND instrument_type = 'EQUITY'
                    ORDER BY trading_symbol
                    LIMIT 200
                """)
                return [row['trading_symbol'] for row in rows]
        except Exception as e:
            logger.error(f"Error fetching F&O stocks: {e}")
            # Fallback to hardcoded list
            return ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 
                    'BAJFINANCE', 'AXISBANK', 'TATAMOTORS', 'MARUTI']
    
    async def _get_spot_open(self, stock: str) -> Optional[float]:
        """Get opening price for a stock (9:15 AM candle)."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT open FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    WHERE im.trading_symbol = $1 
                      AND im.instrument_type = 'EQUITY'
                      AND DATE(c.timestamp) = CURRENT_DATE
                    ORDER BY c.timestamp
                    LIMIT 1
                """, stock)
                return float(row['open']) if row else None
        except Exception as e:
            logger.error(f"Error getting spot open for {stock}: {e}")
            return None
    
    async def _get_spot_current(self, stock: str) -> Optional[float]:
        """Get current (latest) spot price for a stock."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT close FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    WHERE im.trading_symbol = $1 
                      AND im.instrument_type = 'EQUITY'
                      AND DATE(c.timestamp) = CURRENT_DATE
                    ORDER BY c.timestamp DESC
                    LIMIT 1
                """, stock)
                return float(row['close']) if row else None
        except Exception as e:
            logger.error(f"Error getting current spot for {stock}: {e}")
            return None
    
    async def _get_option_premium(self, stock: str, strike: int, option_type: str) -> Optional[float]:
        """Get current option premium."""
        try:
            async with self.pool.acquire() as conn:
                # Find option with matching strike and nearest expiry
                row = await conn.fetchrow("""
                    SELECT c.close FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    JOIN option_master om ON im.instrument_id = om.instrument_id
                    WHERE im.underlying = $1 
                      AND im.instrument_type = $2
                      AND om.strike_price = $3
                      AND om.expiry_date >= CURRENT_DATE
                      AND DATE(c.timestamp) = CURRENT_DATE
                    ORDER BY om.expiry_date, c.timestamp DESC
                    LIMIT 1
                """, stock, option_type, strike)
                return float(row['close']) if row else None
        except Exception as e:
            logger.error(f"Error getting option premium for {stock} {strike} {option_type}: {e}")
            return None
    
    async def _get_option_volume(self, stock: str, strike: int, option_type: str) -> int:
        """Get option volume for the day."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT SUM(c.volume) as total_volume FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    JOIN option_master om ON im.instrument_id = om.instrument_id
                    WHERE im.underlying = $1 
                      AND im.instrument_type = $2
                      AND om.strike_price = $3
                      AND om.expiry_date >= CURRENT_DATE
                      AND DATE(c.timestamp) = CURRENT_DATE
                """, stock, option_type, strike)
                return int(row['total_volume']) if row and row['total_volume'] else 0
        except Exception as e:
            logger.error(f"Error getting option volume: {e}")
            return 0

# Example usage
async def main():
    executor = StrategyExecutor('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await executor.connect()
    
    # Sync latest data before starting
    logger.info("Checking for missing/stale data...")
    sync_result = await executor.sync_latest_data()
    logger.info(f"Data sync result: {sync_result['status']}")
    if sync_result.get('last_data_date'):
        logger.info(f"Last data date: {sync_result['last_data_date']}")
    
    # Register Morning Momentum Alpha strategy
    await executor.register_strategy("Morning Momentum Alpha", required_funds=50000)
    
    # Set available funds
    await executor.update_available_funds("Morning Momentum Alpha", 250000)
    
    # Start strategy
    await executor.start_strategy("Morning Momentum Alpha")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
            status = executor.get_strategy_status("Morning Momentum Alpha")
            logger.info(f"Strategy status: {status}")
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await executor.stop_strategy("Morning Momentum Alpha")
        await executor.close()

if __name__ == "__main__":
    asyncio.run(main())

