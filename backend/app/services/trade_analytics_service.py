"""
Trade Analytics Service
Provides comprehensive trade-level tracking and analysis
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from loguru import logger
import statistics

from app.schemas.trade_analytics import (
    TradeAnalytics, TradeAnalyticsSummary, EntryContext,
    StopLossConfig, TargetConfig, CurrentTradeState,
    StopLossRecommendation, TradeDirection, TradeStatus,
    StopLossType
)


class TradeAnalyticsService:
    """
    Service for tracking and analyzing trades with rich contextual data.
    """
    
    def __init__(self):
        # In-memory store for trade analytics (would be DB in production)
        self._trades: Dict[str, TradeAnalytics] = {}
        self._sl_history: Dict[str, List[Dict]] = {}
        
    async def create_trade_analytics(
        self,
        symbol: str,
        direction: TradeDirection,
        quantity: int,
        entry_price: float,
        entry_time: datetime,
        spot_price: float,
        broker_client: Any = None,
        strategy_name: Optional[str] = None
    ) -> TradeAnalytics:
        """
        Create trade analytics with full entry context.
        Called when a new position is opened.
        """
        trade_id = f"{symbol}_{entry_time.strftime('%Y%m%d%H%M%S')}"
        
        # Build entry context
        entry_context = await self._build_entry_context(
            symbol=symbol,
            spot_price=spot_price,
            entry_price=entry_price,
            broker_client=broker_client
        )
        
        # Get SL recommendation
        sl_recommendation = await self._calculate_sl_recommendation(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            spot_price=spot_price,
            entry_context=entry_context
        )
        
        # Initialize SL config
        stop_loss = StopLossConfig(
            sl_type=StopLossType.NONE,
            highest_price_since_entry=entry_price,
            lowest_price_since_entry=entry_price
        )
        
        # Initialize targets
        targets = TargetConfig()
        
        # Current state
        current_state = CurrentTradeState(
            current_ltp=entry_price,
            current_spot_price=spot_price,
            unrealized_pnl=0,
            unrealized_pnl_percent=0,
            max_profit_seen=0,
            max_drawdown_seen=0,
            price_change_percent=0,
            spot_change_since_entry=0
        )
        
        # Extract underlying from symbol
        underlying = self._extract_underlying(symbol)
        
        analytics = TradeAnalytics(
            trade_id=trade_id,
            symbol=symbol,
            tradingsymbol=symbol,
            underlying=underlying,
            direction=direction,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=entry_time,
            status=TradeStatus.OPEN,
            entry_context=entry_context,
            stop_loss=stop_loss,
            targets=targets,
            current_state=current_state,
            sl_recommendation=sl_recommendation,
            strategy_name=strategy_name
        )
        
        self._trades[symbol] = analytics
        logger.info(f"Created trade analytics for {symbol}")
        
        return analytics
    
    async def update_trade_state(
        self,
        symbol: str,
        current_ltp: float,
        current_spot_price: float,
        current_iv: Optional[float] = None,
        current_delta: Optional[float] = None,
        current_theta: Optional[float] = None
    ) -> Optional[TradeAnalytics]:
        """
        Update trade state with current market data.
        Called periodically or on price updates.
        """
        if symbol not in self._trades:
            return None
        
        trade = self._trades[symbol]
        entry = trade.entry_price
        qty = trade.quantity
        direction_mult = 1 if trade.direction == TradeDirection.LONG else -1
        
        # Calculate P&L
        pnl = (current_ltp - entry) * qty * direction_mult
        pnl_percent = ((current_ltp - entry) / entry * 100) * direction_mult
        
        # Update max profit/drawdown
        max_profit = max(trade.current_state.max_profit_seen, pnl)
        max_drawdown = min(trade.current_state.max_drawdown_seen, pnl)
        
        # Update highest/lowest prices for trailing SL
        if trade.stop_loss.highest_price_since_entry:
            trade.stop_loss.highest_price_since_entry = max(
                trade.stop_loss.highest_price_since_entry, current_ltp
            )
        if trade.stop_loss.lowest_price_since_entry:
            trade.stop_loss.lowest_price_since_entry = min(
                trade.stop_loss.lowest_price_since_entry, current_ltp
            )
        
        # Calculate distances
        sl_distance = None
        target_distance = None
        risk_reward = None
        
        if trade.stop_loss.current_sl_price:
            sl_dist = abs(current_ltp - trade.stop_loss.current_sl_price)
            sl_distance = (sl_dist / current_ltp) * 100
        
        if trade.targets.target_price:
            target_dist = abs(trade.targets.target_price - current_ltp)
            target_distance = (target_dist / current_ltp) * 100
            
            if sl_distance and sl_distance > 0:
                risk_reward = target_distance / sl_distance
        
        # IV change calculation
        iv_change = None
        if current_iv and trade.entry_context.iv_at_entry:
            iv_change = current_iv - trade.entry_context.iv_at_entry
        
        # Theta decay impact
        theta_impact = None
        if trade.entry_context.theta_at_entry:
            days_held = (datetime.now(timezone.utc) - trade.entry_time).days
            theta_impact = trade.entry_context.theta_at_entry * days_held * qty
        
        # Update state
        trade.current_state = CurrentTradeState(
            current_ltp=current_ltp,
            current_spot_price=current_spot_price,
            unrealized_pnl=pnl,
            unrealized_pnl_percent=pnl_percent,
            max_profit_seen=max_profit,
            max_drawdown_seen=max_drawdown,
            current_iv=current_iv,
            current_delta=current_delta,
            current_theta=current_theta,
            iv_change=iv_change,
            theta_decay_impact=theta_impact,
            price_change_percent=((current_ltp - entry) / entry) * 100,
            spot_change_since_entry=current_spot_price - trade.entry_context.spot_price,
            sl_distance_percent=sl_distance,
            target_distance_percent=target_distance,
            risk_reward_current=risk_reward
        )
        
        # Check and update trailing SL
        await self._update_trailing_sl(trade, current_ltp)
        
        # Update trade duration
        trade.trade_duration_minutes = int(
            (datetime.now(timezone.utc) - trade.entry_time).total_seconds() / 60
        )
        
        return trade
    
    async def set_stop_loss(
        self,
        symbol: str,
        sl_type: StopLossType,
        sl_price: Optional[float] = None,
        sl_percentage: Optional[float] = None,
        trailing_distance: Optional[float] = None,
        trailing_trigger_price: Optional[float] = None
    ) -> Optional[TradeAnalytics]:
        """Set or update stop loss for a trade."""
        if symbol not in self._trades:
            return None
        
        trade = self._trades[symbol]
        entry = trade.entry_price
        current = trade.current_state.current_ltp
        
        # Calculate SL price based on type
        if sl_type == StopLossType.FIXED and sl_price:
            final_sl = sl_price
        elif sl_type == StopLossType.PERCENTAGE and sl_percentage:
            if trade.direction == TradeDirection.LONG:
                final_sl = entry * (1 - sl_percentage / 100)
            else:
                final_sl = entry * (1 + sl_percentage / 100)
        elif sl_type == StopLossType.TRAILING:
            final_sl = trade.stop_loss.current_sl_price or sl_price
        else:
            final_sl = sl_price
        
        # Record SL change
        sl_change = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "old_sl": trade.stop_loss.current_sl_price,
            "new_sl": final_sl,
            "sl_type": sl_type.value,
            "price_at_change": current
        }
        trade.stop_loss.sl_adjustments.append(sl_change)
        
        # Update SL config
        trade.stop_loss.sl_type = sl_type
        trade.stop_loss.current_sl_price = final_sl
        if not trade.stop_loss.initial_sl_price:
            trade.stop_loss.initial_sl_price = final_sl
        
        trade.stop_loss.sl_percentage = sl_percentage
        trade.stop_loss.sl_points = abs(entry - final_sl) if final_sl else None
        
        # Trailing specific
        if sl_type == StopLossType.TRAILING:
            trade.stop_loss.trailing_distance = trailing_distance
            trade.stop_loss.trailing_trigger_price = trailing_trigger_price
        
        logger.info(f"Set {sl_type.value} SL for {symbol} at {final_sl}")
        return trade
    
    async def set_target(
        self,
        symbol: str,
        target_price: Optional[float] = None,
        target_percentage: Optional[float] = None,
        partial_targets: Optional[List[Dict[str, float]]] = None
    ) -> Optional[TradeAnalytics]:
        """Set or update target for a trade."""
        if symbol not in self._trades:
            return None
        
        trade = self._trades[symbol]
        entry = trade.entry_price
        
        # Calculate target price
        if target_price:
            final_target = target_price
        elif target_percentage:
            if trade.direction == TradeDirection.LONG:
                final_target = entry * (1 + target_percentage / 100)
            else:
                final_target = entry * (1 - target_percentage / 100)
        else:
            final_target = None
        
        trade.targets.target_price = final_target
        trade.targets.target_percentage = target_percentage
        
        if partial_targets:
            trade.targets.partial_targets = partial_targets
        
        # Calculate risk:reward if SL is set
        if trade.stop_loss.current_sl_price and final_target:
            sl_dist = abs(entry - trade.stop_loss.current_sl_price)
            target_dist = abs(final_target - entry)
            trade.targets.risk_reward_ratio = target_dist / sl_dist if sl_dist > 0 else None
        
        return trade
    
    async def get_trade_analytics(self, symbol: str) -> Optional[TradeAnalytics]:
        """Get analytics for a specific trade."""
        return self._trades.get(symbol)
    
    async def get_all_trade_analytics(self) -> TradeAnalyticsSummary:
        """Get summary of all active trades with analytics."""
        trades = list(self._trades.values())
        
        total_unrealized = sum(t.current_state.unrealized_pnl for t in trades)
        total_realized = sum(t.realized_pnl or 0 for t in trades)
        
        # Aggregate Greeks
        net_delta = sum(
            (t.current_state.current_delta or 0) * t.quantity 
            for t in trades
        )
        net_theta = sum(
            (t.current_state.current_theta or 0) * t.quantity 
            for t in trades
        )
        net_vega = sum(
            (t.entry_context.vega_at_entry or 0) * t.quantity 
            for t in trades
        )
        
        # Risk calculations
        total_sl_risk = 0
        max_single_risk = 0
        
        for t in trades:
            if t.stop_loss.current_sl_price:
                risk = abs(t.entry_price - t.stop_loss.current_sl_price) * t.quantity
                total_sl_risk += risk
                max_single_risk = max(max_single_risk, risk)
        
        return TradeAnalyticsSummary(
            total_trades=len(trades),
            total_unrealized_pnl=total_unrealized,
            total_realized_pnl=total_realized,
            net_delta=net_delta,
            net_theta=net_theta,
            net_vega=net_vega,
            total_risk_if_sl_hit=total_sl_risk,
            max_single_trade_risk=max_single_risk,
            portfolio_heat=0,  # Would need capital info
            trades=trades
        )
    
    async def sync_from_positions(
        self,
        positions: List[Dict[str, Any]],
        broker_client: Any = None
    ) -> List[TradeAnalytics]:
        """
        Sync trade analytics from broker positions.
        Creates analytics for positions that don't have tracking yet.
        """
        synced = []
        
        for pos in positions:
            symbol = pos.get("symbol", "")
            qty = pos.get("quantity") or pos.get("netQty") or pos.get("qty", 0)
            
            if qty == 0:
                continue
            
            # Get option LTP
            ltp = pos.get("ltp") or pos.get("last_price", 0)
            
            # Try to get actual underlying spot price for options
            spot_price = await self.fetch_underlying_spot_price(symbol, broker_client)
            if spot_price is None:
                # Fallback: Use option LTP if we can't get underlying
                # This is not ideal for options but better than nothing
                spot_price = ltp
                logger.warning(f"Could not fetch underlying spot for {symbol}, using option LTP as fallback")
            
            # Check if we already track this
            if symbol in self._trades:
                # Update existing
                await self.update_trade_state(symbol, ltp, spot_price)
                synced.append(self._trades[symbol])
            else:
                # Create new analytics
                entry_price = pos.get("avgPrice") or pos.get("netAvg") or pos.get("average_price", 0)
                direction = TradeDirection.LONG if qty > 0 else TradeDirection.SHORT
                
                analytics = await self.create_trade_analytics(
                    symbol=symbol,
                    direction=direction,
                    quantity=abs(qty),
                    entry_price=entry_price,
                    entry_time=datetime.now(timezone.utc),
                    spot_price=spot_price,
                    broker_client=broker_client
                )
                synced.append(analytics)
        
        return synced
    
    # =========================================================================
    # Private Helper Methods
    # =========================================================================
    
    async def _build_entry_context(
        self,
        symbol: str,
        spot_price: float,
        entry_price: float,
        broker_client: Any = None
    ) -> EntryContext:
        """Build comprehensive entry context."""
        
        context = EntryContext(
            spot_price=spot_price,
            spot_change_percent=0  # Would need previous close
        )
        
        # Parse option details from symbol
        option_info = self._parse_option_symbol(symbol)
        if option_info:
            context.strike_price = option_info.get("strike")
            context.option_type = option_info.get("option_type")
            context.expiry_date = option_info.get("expiry")
            
            if context.strike_price and spot_price:
                # Calculate moneyness
                diff_pct = ((spot_price - context.strike_price) / spot_price) * 100
                
                if context.option_type == "CE":
                    if diff_pct > 2:
                        context.moneyness = "ITM"
                    elif diff_pct < -2:
                        context.moneyness = "OTM"
                    else:
                        context.moneyness = "ATM"
                else:  # PE
                    if diff_pct < -2:
                        context.moneyness = "ITM"
                    elif diff_pct > 2:
                        context.moneyness = "OTM"
                    else:
                        context.moneyness = "ATM"
                
                context.distance_from_atm = abs(diff_pct)
        
        # Would fetch VIX, Greeks, etc. from broker if available
        # context.vix_at_entry = await self._fetch_vix(broker_client)
        # context.iv_at_entry = await self._fetch_iv(symbol, broker_client)
        
        return context
    
    async def _calculate_sl_recommendation(
        self,
        symbol: str,
        direction: TradeDirection,
        entry_price: float,
        spot_price: float,
        entry_context: EntryContext
    ) -> StopLossRecommendation:
        """Calculate recommended stop loss based on multiple factors."""
        
        # Default percentages
        DEFAULT_SL_PCT = 20  # 20% for options
        ATR_MULTIPLIER = 1.5
        
        # Calculate different SL levels
        percentage_sl = entry_price * (1 - DEFAULT_SL_PCT / 100) if direction == TradeDirection.LONG \
            else entry_price * (1 + DEFAULT_SL_PCT / 100)
        
        # ATR-based (simulated - would use actual ATR)
        estimated_atr = entry_price * 0.05  # 5% of price as proxy
        atr_sl = entry_price - (ATR_MULTIPLIER * estimated_atr) if direction == TradeDirection.LONG \
            else entry_price + (ATR_MULTIPLIER * estimated_atr)
        
        # Support-based (simplified)
        support_sl = entry_price * 0.85 if direction == TradeDirection.LONG else entry_price * 1.15
        
        # Choose recommended SL
        if entry_context.moneyness == "OTM":
            # OTM options are riskier, wider SL
            recommended_sl = percentage_sl
            sl_type = StopLossType.PERCENTAGE
            reasoning = "OTM option - using percentage-based SL to allow for volatility"
        elif entry_context.iv_at_entry and entry_context.iv_at_entry > 30:
            # High IV - use ATR-based
            recommended_sl = atr_sl
            sl_type = StopLossType.ATR_BASED
            reasoning = "High IV environment - using ATR-based SL for dynamic protection"
        else:
            recommended_sl = atr_sl
            sl_type = StopLossType.ATR_BASED
            reasoning = "Standard conditions - ATR-based SL recommended"
        
        # Calculate risk
        sl_risk = abs(entry_price - recommended_sl)
        sl_risk_pct = (sl_risk / entry_price) * 100
        
        return StopLossRecommendation(
            atr_based_sl=atr_sl,
            percentage_sl=percentage_sl,
            support_based_sl=support_sl,
            swing_low_sl=None,  # Would need historical data
            recommended_sl=recommended_sl,
            recommended_sl_type=sl_type,
            sl_risk_amount=sl_risk,
            sl_risk_percent=sl_risk_pct,
            confidence=0.7,
            reasoning=reasoning,
            historical_sl_hit_rate=None
        )
    
    async def _update_trailing_sl(self, trade: TradeAnalytics, current_price: float):
        """Update trailing stop loss if conditions are met."""
        sl = trade.stop_loss
        
        if sl.sl_type != StopLossType.TRAILING:
            return
        
        if not sl.trailing_distance:
            return
        
        # Check if trailing should activate
        if sl.trailing_trigger_price and current_price < sl.trailing_trigger_price:
            return
        
        sl.trailing_activated = True
        
        # Update SL based on direction
        if trade.direction == TradeDirection.LONG:
            # For long, SL trails up with price
            new_sl = current_price - sl.trailing_distance
            if sl.current_sl_price is None or new_sl > sl.current_sl_price:
                old_sl = sl.current_sl_price
                sl.current_sl_price = new_sl
                
                sl.sl_adjustments.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "old_sl": old_sl,
                    "new_sl": new_sl,
                    "trigger": "trailing",
                    "price_at_change": current_price
                })
        else:
            # For short, SL trails down with price
            new_sl = current_price + sl.trailing_distance
            if sl.current_sl_price is None or new_sl < sl.current_sl_price:
                old_sl = sl.current_sl_price
                sl.current_sl_price = new_sl
                
                sl.sl_adjustments.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "old_sl": old_sl,
                    "new_sl": new_sl,
                    "trigger": "trailing",
                    "price_at_change": current_price
                })
    
    def _extract_underlying(self, symbol: str) -> Optional[str]:
        """Extract underlying from symbol."""
        # NSE:SHRIRAMFIN25DEC890CE -> SHRIRAMFIN
        try:
            parts = symbol.split(":")
            if len(parts) == 2:
                name = parts[1]
                # Remove date and strike
                for i, char in enumerate(name):
                    if char.isdigit():
                        return name[:i]
            return None
        except:
            return None
    
    def get_underlying_symbol(self, symbol: str) -> Optional[str]:
        """
        Get the full trading symbol for the underlying of an option.
        E.g., NSE:SHRIRAMFIN25DEC890CE -> NSE:SHRIRAMFIN-EQ
        """
        underlying = self._extract_underlying(symbol)
        if underlying:
            # Get exchange prefix
            parts = symbol.split(":")
            exchange = parts[0] if len(parts) == 2 else "NSE"
            return f"{exchange}:{underlying}-EQ"
        return None
    
    async def fetch_underlying_spot_price(
        self,
        symbol: str,
        broker_client: Any = None
    ) -> Optional[float]:
        """
        Fetch the underlying spot price for an option symbol.
        Uses the broker client to get LTP of the underlying equity.
        """
        underlying_symbol = self.get_underlying_symbol(symbol)
        if not underlying_symbol:
            return None
        
        try:
            if broker_client and hasattr(broker_client, 'get_quotes'):
                quotes = broker_client.get_quotes([underlying_symbol])
                if quotes.get("s") == "ok" and quotes.get("d"):
                    for quote in quotes.get("d", []):
                        if quote.get("n") == underlying_symbol or quote.get("v", {}).get("short_name"):
                            ltp = quote.get("v", {}).get("lp") or quote.get("v", {}).get("ltp")
                            if ltp:
                                return float(ltp)
        except Exception as e:
            logger.warning(f"Failed to fetch underlying spot price for {symbol}: {e}")
        
        return None
    
    def _parse_option_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Parse option symbol to extract strike, type, expiry."""
        # NSE:SHRIRAMFIN25DEC890CE
        try:
            parts = symbol.split(":")
            if len(parts) != 2:
                return None
            
            name = parts[1]
            
            # Check if it's an option (ends with CE or PE)
            if not (name.endswith("CE") or name.endswith("PE")):
                return None
            
            option_type = name[-2:]  # CE or PE
            remaining = name[:-2]  # SHRIRAMFIN25DEC890
            
            # Find where digits for strike start
            strike_start = len(remaining) - 1
            while strike_start >= 0 and remaining[strike_start].isdigit():
                strike_start -= 1
            strike_start += 1
            
            strike = int(remaining[strike_start:]) if strike_start < len(remaining) else None
            expiry_part = remaining[:strike_start]  # SHRIRAMFIN25DEC
            
            return {
                "option_type": option_type,
                "strike": strike,
                "expiry": expiry_part  # Would need more parsing for actual date
            }
        except:
            return None


# Singleton instance
_trade_analytics_service: Optional[TradeAnalyticsService] = None

def get_trade_analytics_service() -> TradeAnalyticsService:
    global _trade_analytics_service
    if _trade_analytics_service is None:
        _trade_analytics_service = TradeAnalyticsService()
    return _trade_analytics_service
