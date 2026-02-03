"""
Futures Trading Module

Provides futures-specific trading functionality:
- Futures position management with expiry tracking
- Roll-over logic for near-expiry positions
- Margin requirements calculation
- Mark-to-market (MTM) settlements
- Basis tracking (Futures vs Spot)
- Calendar spread support

Futures Trading Rules:
- Maximum 3 lots per underlying (configurable)
- Auto roll-over 3 days before expiry
- MTM settlement at EOD
- Margin monitoring with alerts
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from zoneinfo import ZoneInfo
import asyncio
import uuid

from loguru import logger

from app.core.events import EventBus, EventType


class FuturesContractType(str, Enum):
    """Types of futures contracts."""
    STOCK_FUTURE = "stock_future"
    INDEX_FUTURE = "index_future"


class FuturesOrderType(str, Enum):
    """Order types for futures."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class FuturesProductType(str, Enum):
    """Product types for futures positions."""
    NRML = "NRML"  # Overnight/Carry forward
    MIS = "MIS"    # Intraday


class RolloverStrategy(str, Enum):
    """Strategies for rolling over futures positions."""
    AUTO = "auto"           # Roll automatically before expiry
    MANUAL = "manual"       # User decides
    SPREAD = "spread"       # Use calendar spread for rollover
    CLOSE = "close"         # Just close, don't roll


@dataclass
class FuturesContract:
    """Represents a futures contract."""
    contract_id: str
    underlying: str
    exchange: str  # NSE, BSE
    contract_type: FuturesContractType
    
    # Contract specifications
    expiry_date: date
    lot_size: int
    tick_size: Decimal
    
    # Current prices
    last_price: Decimal = Decimal("0")
    spot_price: Decimal = Decimal("0")  # Underlying spot
    
    # Contract identifiers
    symbol: str = ""  # Trading symbol like "NIFTY24DECFUT"
    instrument_key: str = ""  # Broker's instrument key
    
    @property
    def days_to_expiry(self) -> int:
        """Days remaining until expiry."""
        today = date.today()
        return (self.expiry_date - today).days
    
    @property
    def basis(self) -> Decimal:
        """Price difference between futures and spot."""
        if self.spot_price > 0:
            return self.last_price - self.spot_price
        return Decimal("0")
    
    @property
    def basis_percentage(self) -> Decimal:
        """Basis as percentage of spot."""
        if self.spot_price > 0:
            return (self.basis / self.spot_price) * 100
        return Decimal("0")
    
    @property
    def is_near_expiry(self) -> bool:
        """Check if within rollover window."""
        return self.days_to_expiry <= 3


@dataclass
class FuturesPosition:
    """Represents an open futures position."""
    position_id: str
    contract: FuturesContract
    
    # Position details
    side: str  # "LONG" or "SHORT"
    quantity: int  # In lots
    product_type: FuturesProductType
    
    # Entry details
    entry_price: Decimal
    entry_date: datetime
    
    # Current status
    current_price: Decimal = Decimal("0")
    mtm_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    
    # Risk management
    stop_loss: Optional[Decimal] = None
    target: Optional[Decimal] = None
    trailing_stop: bool = False
    
    # Margin
    initial_margin: Decimal = Decimal("0")
    maintenance_margin: Decimal = Decimal("0")
    current_margin: Decimal = Decimal("0")
    
    # Rollover
    rollover_strategy: RolloverStrategy = RolloverStrategy.AUTO
    rolled_from: Optional[str] = None  # Previous contract ID if rolled
    
    # Strategy tracking
    strategy_id: Optional[str] = None
    
    @property
    def unrealized_pnl(self) -> Decimal:
        """Calculate unrealized P&L."""
        multiplier = self.contract.lot_size * self.quantity
        if self.side == "LONG":
            return (self.current_price - self.entry_price) * multiplier
        else:  # SHORT
            return (self.entry_price - self.current_price) * multiplier
    
    @property
    def notional_value(self) -> Decimal:
        """Calculate notional value of position."""
        return self.current_price * self.contract.lot_size * self.quantity
    
    @property
    def needs_rollover(self) -> bool:
        """Check if position needs rollover."""
        return (
            self.rollover_strategy == RolloverStrategy.AUTO and
            self.contract.is_near_expiry and
            self.product_type == FuturesProductType.NRML
        )


@dataclass
class MarginRequirement:
    """Margin requirements for a futures position."""
    initial_margin: Decimal
    maintenance_margin: Decimal
    exposure_margin: Decimal
    total_margin: Decimal
    margin_percentage: Decimal


@dataclass
class MTMSettlement:
    """Daily Mark-to-Market settlement."""
    settlement_date: date
    position_id: str
    previous_settlement_price: Decimal
    current_settlement_price: Decimal
    mtm_profit_loss: Decimal
    cumulative_mtm: Decimal


class FuturesTradingEngine:
    """
    Engine for futures trading operations.
    
    Features:
    - Position management with lot-based sizing
    - Automatic rollover before expiry
    - MTM settlement tracking
    - Margin monitoring
    - Basis tracking
    """
    
    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        max_lots_per_underlying: int = 3,
        rollover_days_before_expiry: int = 3,
        margin_alert_threshold: float = 0.8,
    ):
        self.event_bus = event_bus
        self.max_lots_per_underlying = max_lots_per_underlying
        self.rollover_days_before_expiry = rollover_days_before_expiry
        self.margin_alert_threshold = margin_alert_threshold
        
        # State
        self._contracts: Dict[str, FuturesContract] = {}
        self._positions: Dict[str, FuturesPosition] = {}
        self._settlements: List[MTMSettlement] = []
        
        # Callbacks
        self._order_callback: Optional[Callable] = None
        
        # Background tasks
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        logger.info("FuturesTradingEngine initialized")
    
    # =========================================================================
    # Contract Management
    # =========================================================================
    
    def register_contract(self, contract: FuturesContract) -> None:
        """Register a futures contract for tracking."""
        self._contracts[contract.contract_id] = contract
        logger.debug(f"Registered contract: {contract.symbol}")
    
    def get_contract(self, contract_id: str) -> Optional[FuturesContract]:
        """Get a registered contract."""
        return self._contracts.get(contract_id)
    
    def get_contracts_for_underlying(self, underlying: str) -> List[FuturesContract]:
        """Get all contracts for an underlying."""
        return [
            c for c in self._contracts.values()
            if c.underlying == underlying
        ]
    
    def get_near_month_contract(self, underlying: str) -> Optional[FuturesContract]:
        """Get the nearest expiry contract for an underlying."""
        contracts = self.get_contracts_for_underlying(underlying)
        if not contracts:
            return None
        
        # Sort by expiry and get nearest
        contracts.sort(key=lambda c: c.expiry_date)
        return contracts[0]
    
    def get_far_month_contract(self, underlying: str) -> Optional[FuturesContract]:
        """Get the next month contract for an underlying."""
        contracts = self.get_contracts_for_underlying(underlying)
        if len(contracts) < 2:
            return None
        
        contracts.sort(key=lambda c: c.expiry_date)
        return contracts[1]
    
    def update_contract_price(
        self,
        contract_id: str,
        last_price: Decimal,
        spot_price: Optional[Decimal] = None
    ) -> None:
        """Update contract prices."""
        contract = self._contracts.get(contract_id)
        if contract:
            contract.last_price = last_price
            if spot_price:
                contract.spot_price = spot_price
            
            # Update positions with this contract
            for position in self._positions.values():
                if position.contract.contract_id == contract_id:
                    position.current_price = last_price
    
    # =========================================================================
    # Position Management
    # =========================================================================
    
    async def open_position(
        self,
        contract: FuturesContract,
        side: str,
        quantity: int,  # In lots
        entry_price: Decimal,
        product_type: FuturesProductType = FuturesProductType.NRML,
        stop_loss: Optional[Decimal] = None,
        target: Optional[Decimal] = None,
        strategy_id: Optional[str] = None,
    ) -> Optional[FuturesPosition]:
        """
        Open a new futures position.
        
        Args:
            contract: The futures contract
            side: "LONG" or "SHORT"
            quantity: Number of lots
            entry_price: Entry price
            product_type: NRML or MIS
            stop_loss: Optional stop loss price
            target: Optional target price
            strategy_id: Optional strategy ID
            
        Returns:
            The created position or None if validation fails
        """
        # Validate position limits
        current_lots = self._get_lots_for_underlying(contract.underlying)
        if current_lots + quantity > self.max_lots_per_underlying:
            logger.warning(
                f"Position limit exceeded for {contract.underlying}: "
                f"current={current_lots}, requested={quantity}, max={self.max_lots_per_underlying}"
            )
            return None
        
        # Calculate margins
        margin_req = self._calculate_margin(contract, quantity, side)
        
        # Create position
        position = FuturesPosition(
            position_id=str(uuid.uuid4()),
            contract=contract,
            side=side,
            quantity=quantity,
            product_type=product_type,
            entry_price=entry_price,
            entry_date=datetime.now(ZoneInfo("Asia/Kolkata")),
            current_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            initial_margin=margin_req.initial_margin,
            maintenance_margin=margin_req.maintenance_margin,
            current_margin=margin_req.total_margin,
            strategy_id=strategy_id,
        )
        
        self._positions[position.position_id] = position
        
        logger.info(
            f"Opened futures position: {position.position_id} "
            f"{side} {quantity} lots of {contract.symbol} @ {entry_price}"
        )
        
        # Publish event
        if self.event_bus:
            await self.event_bus.publish("position_opened", {
                "position_id": position.position_id,
                "symbol": contract.symbol,
                "side": side,
                "quantity": quantity,
                "entry_price": float(entry_price),
                "instrument_type": "FUTURE",
            })
        
        return position
    
    async def close_position(
        self,
        position_id: str,
        exit_price: Decimal,
        reason: str = "manual",
    ) -> Optional[Decimal]:
        """
        Close a futures position.
        
        Returns:
            Realized P&L or None if position not found
        """
        position = self._positions.get(position_id)
        if not position:
            logger.warning(f"Position not found: {position_id}")
            return None
        
        # Calculate P&L
        multiplier = position.contract.lot_size * position.quantity
        if position.side == "LONG":
            pnl = (exit_price - position.entry_price) * multiplier
        else:
            pnl = (position.entry_price - exit_price) * multiplier
        
        logger.info(
            f"Closed futures position: {position_id} "
            f"@ {exit_price}, P&L: {pnl}, reason: {reason}"
        )
        
        # Publish event
        if self.event_bus:
            await self.event_bus.publish("position_closed", {
                "position_id": position_id,
                "symbol": position.contract.symbol,
                "exit_price": float(exit_price),
                "pnl": float(pnl),
                "reason": reason,
                "instrument_type": "FUTURE",
            })
        
        # Remove position
        del self._positions[position_id]
        
        return pnl
    
    async def modify_position(
        self,
        position_id: str,
        stop_loss: Optional[Decimal] = None,
        target: Optional[Decimal] = None,
        trailing_stop: Optional[bool] = None,
    ) -> bool:
        """Modify position parameters."""
        position = self._positions.get(position_id)
        if not position:
            return False
        
        if stop_loss is not None:
            position.stop_loss = stop_loss
        if target is not None:
            position.target = target
        if trailing_stop is not None:
            position.trailing_stop = trailing_stop
        
        logger.debug(f"Modified position {position_id}: SL={stop_loss}, Target={target}")
        return True
    
    def get_position(self, position_id: str) -> Optional[FuturesPosition]:
        """Get a position by ID."""
        return self._positions.get(position_id)
    
    def get_all_positions(self) -> List[FuturesPosition]:
        """Get all open positions."""
        return list(self._positions.values())
    
    def get_positions_for_underlying(self, underlying: str) -> List[FuturesPosition]:
        """Get positions for a specific underlying."""
        return [
            p for p in self._positions.values()
            if p.contract.underlying == underlying
        ]
    
    def _get_lots_for_underlying(self, underlying: str) -> int:
        """Get total lots for an underlying."""
        return sum(
            p.quantity for p in self._positions.values()
            if p.contract.underlying == underlying
        )
    
    # =========================================================================
    # Margin Calculation
    # =========================================================================
    
    def _calculate_margin(
        self,
        contract: FuturesContract,
        quantity: int,
        side: str,
    ) -> MarginRequirement:
        """
        Calculate margin requirements.
        
        Note: This is a simplified calculation. Real margin depends on
        SPAN + Exposure margins from exchange.
        """
        # Notional value
        notional = contract.last_price * contract.lot_size * quantity
        
        # Simplified margin percentages
        if contract.contract_type == FuturesContractType.INDEX_FUTURE:
            initial_pct = Decimal("0.10")  # 10% for index futures
            maintenance_pct = Decimal("0.08")
            exposure_pct = Decimal("0.03")
        else:
            initial_pct = Decimal("0.15")  # 15% for stock futures
            maintenance_pct = Decimal("0.12")
            exposure_pct = Decimal("0.05")
        
        initial_margin = notional * initial_pct
        maintenance_margin = notional * maintenance_pct
        exposure_margin = notional * exposure_pct
        
        return MarginRequirement(
            initial_margin=initial_margin,
            maintenance_margin=maintenance_margin,
            exposure_margin=exposure_margin,
            total_margin=initial_margin + exposure_margin,
            margin_percentage=initial_pct + exposure_pct,
        )
    
    def get_total_margin_required(self) -> Decimal:
        """Get total margin required for all positions."""
        return sum(p.current_margin for p in self._positions.values())
    
    # =========================================================================
    # Rollover Management
    # =========================================================================
    
    async def check_rollovers(self) -> List[FuturesPosition]:
        """
        Check for positions needing rollover.
        
        Returns:
            List of positions that need rollover
        """
        positions_to_roll = []
        
        for position in self._positions.values():
            if position.needs_rollover:
                positions_to_roll.append(position)
                logger.info(
                    f"Position {position.position_id} needs rollover: "
                    f"{position.contract.symbol} expires in "
                    f"{position.contract.days_to_expiry} days"
                )
        
        return positions_to_roll
    
    async def rollover_position(
        self,
        position_id: str,
        new_contract: FuturesContract,
        strategy: RolloverStrategy = RolloverStrategy.AUTO,
    ) -> Optional[FuturesPosition]:
        """
        Roll over a position to a new contract.
        
        Args:
            position_id: Current position ID
            new_contract: The new contract to roll into
            strategy: Rollover strategy
            
        Returns:
            New position or None if rollover fails
        """
        old_position = self._positions.get(position_id)
        if not old_position:
            logger.warning(f"Position not found for rollover: {position_id}")
            return None
        
        logger.info(
            f"Rolling over position {position_id}: "
            f"{old_position.contract.symbol} -> {new_contract.symbol}"
        )
        
        if strategy == RolloverStrategy.SPREAD:
            # Calendar spread rollover
            # 1. Sell near month, buy far month simultaneously
            # This reduces rollover cost
            return await self._rollover_with_spread(old_position, new_contract)
        else:
            # Simple rollover: close old, open new
            # Close old position
            exit_price = old_position.contract.last_price
            pnl = await self.close_position(position_id, exit_price, reason="rollover")
            
            # Open new position
            new_position = await self.open_position(
                contract=new_contract,
                side=old_position.side,
                quantity=old_position.quantity,
                entry_price=new_contract.last_price,
                product_type=old_position.product_type,
                stop_loss=old_position.stop_loss,
                target=old_position.target,
                strategy_id=old_position.strategy_id,
            )
            
            if new_position:
                new_position.rolled_from = position_id
                new_position.total_pnl = pnl if pnl else Decimal("0")
            
            return new_position
    
    async def _rollover_with_spread(
        self,
        old_position: FuturesPosition,
        new_contract: FuturesContract,
    ) -> Optional[FuturesPosition]:
        """Execute calendar spread rollover."""
        # This would place a spread order: sell near + buy far
        # Implementation depends on broker API support
        logger.info("Calendar spread rollover not fully implemented")
        
        # For now, fall back to simple rollover
        return await self.rollover_position(
            old_position.position_id,
            new_contract,
            RolloverStrategy.AUTO
        )
    
    # =========================================================================
    # MTM Settlement
    # =========================================================================
    
    async def calculate_mtm_settlement(
        self,
        settlement_date: date,
        settlement_prices: Dict[str, Decimal],
    ) -> List[MTMSettlement]:
        """
        Calculate daily MTM settlement for all positions.
        
        Args:
            settlement_date: Date of settlement
            settlement_prices: Contract ID -> settlement price mapping
            
        Returns:
            List of MTM settlements
        """
        settlements = []
        
        for position in self._positions.values():
            if position.product_type != FuturesProductType.NRML:
                continue  # MIS doesn't have MTM
            
            contract_id = position.contract.contract_id
            if contract_id not in settlement_prices:
                continue
            
            current_settlement = settlement_prices[contract_id]
            
            # Get previous settlement price
            previous_settlement = self._get_previous_settlement_price(
                position.position_id,
                settlement_date,
            )
            
            if previous_settlement is None:
                previous_settlement = position.entry_price
            
            # Calculate MTM P&L
            multiplier = position.contract.lot_size * position.quantity
            if position.side == "LONG":
                mtm_pnl = (current_settlement - previous_settlement) * multiplier
            else:
                mtm_pnl = (previous_settlement - current_settlement) * multiplier
            
            # Create settlement record
            settlement = MTMSettlement(
                settlement_date=settlement_date,
                position_id=position.position_id,
                previous_settlement_price=previous_settlement,
                current_settlement_price=current_settlement,
                mtm_profit_loss=mtm_pnl,
                cumulative_mtm=position.mtm_pnl + mtm_pnl,
            )
            
            settlements.append(settlement)
            
            # Update position MTM
            position.mtm_pnl += mtm_pnl
            
            logger.debug(
                f"MTM settlement for {position.position_id}: "
                f"{previous_settlement} -> {current_settlement}, P&L: {mtm_pnl}"
            )
        
        self._settlements.extend(settlements)
        
        # Publish event
        if self.event_bus and settlements:
            await self.event_bus.publish("mtm_settlement", {
                "settlement_date": settlement_date.isoformat(),
                "positions_settled": len(settlements),
                "total_mtm": float(sum(s.mtm_profit_loss for s in settlements)),
            })
        
        return settlements
    
    def _get_previous_settlement_price(
        self,
        position_id: str,
        current_date: date,
    ) -> Optional[Decimal]:
        """Get previous settlement price for a position."""
        # Find most recent settlement before current date
        previous = None
        for settlement in reversed(self._settlements):
            if (settlement.position_id == position_id and 
                settlement.settlement_date < current_date):
                previous = settlement.current_settlement_price
                break
        return previous
    
    # =========================================================================
    # Monitoring
    # =========================================================================
    
    async def start(self) -> None:
        """Start the futures trading engine."""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("FuturesTradingEngine started")
    
    async def stop(self) -> None:
        """Stop the futures trading engine."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("FuturesTradingEngine stopped")
    
    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                # Check for rollovers
                positions_to_roll = await self.check_rollovers()
                
                # Check margin levels
                await self._check_margin_levels()
                
                # Check SL/Target
                await self._check_sl_target()
                
            except Exception as e:
                logger.error(f"Error in futures monitor loop: {e}")
            
            await asyncio.sleep(5)  # Check every 5 seconds
    
    async def _check_margin_levels(self) -> None:
        """Check if margin levels are adequate."""
        for position in self._positions.values():
            if position.current_margin <= 0:
                continue
            
            # Simple margin check based on MTM
            margin_used = position.initial_margin - position.mtm_pnl
            margin_ratio = float(margin_used / position.initial_margin)
            
            if margin_ratio > self.margin_alert_threshold:
                logger.warning(
                    f"Margin alert for {position.position_id}: "
                    f"usage at {margin_ratio*100:.1f}%"
                )
                
                if self.event_bus:
                    await self.event_bus.publish("risk_limit_breached", {
                        "risk_type": "MARGIN_LOW",
                        "position_id": position.position_id,
                        "current_value": margin_ratio,
                        "limit_value": self.margin_alert_threshold,
                    })
    
    async def _check_sl_target(self) -> None:
        """Check stop loss and target for all positions."""
        for position in self._positions.values():
            current = position.current_price
            
            # Check stop loss
            if position.stop_loss:
                sl_hit = (
                    (position.side == "LONG" and current <= position.stop_loss) or
                    (position.side == "SHORT" and current >= position.stop_loss)
                )
                if sl_hit:
                    logger.info(f"Stop loss hit for {position.position_id}")
                    await self.close_position(
                        position.position_id,
                        current,
                        reason="stop_loss"
                    )
                    continue
            
            # Check target
            if position.target:
                target_hit = (
                    (position.side == "LONG" and current >= position.target) or
                    (position.side == "SHORT" and current <= position.target)
                )
                if target_hit:
                    logger.info(f"Target hit for {position.position_id}")
                    await self.close_position(
                        position.position_id,
                        current,
                        reason="target"
                    )
    
    # =========================================================================
    # Reporting
    # =========================================================================
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get futures portfolio summary."""
        positions = list(self._positions.values())
        
        total_pnl = sum(p.unrealized_pnl for p in positions)
        total_margin = sum(p.current_margin for p in positions)
        total_notional = sum(p.notional_value for p in positions)
        
        # Group by underlying
        by_underlying: Dict[str, Dict] = {}
        for p in positions:
            underlying = p.contract.underlying
            if underlying not in by_underlying:
                by_underlying[underlying] = {
                    "long_lots": 0,
                    "short_lots": 0,
                    "net_lots": 0,
                    "pnl": Decimal("0"),
                }
            
            if p.side == "LONG":
                by_underlying[underlying]["long_lots"] += p.quantity
                by_underlying[underlying]["net_lots"] += p.quantity
            else:
                by_underlying[underlying]["short_lots"] += p.quantity
                by_underlying[underlying]["net_lots"] -= p.quantity
            
            by_underlying[underlying]["pnl"] += p.unrealized_pnl
        
        return {
            "total_positions": len(positions),
            "total_unrealized_pnl": float(total_pnl),
            "total_margin_used": float(total_margin),
            "total_notional_value": float(total_notional),
            "positions_by_underlying": {
                k: {
                    "long_lots": v["long_lots"],
                    "short_lots": v["short_lots"],
                    "net_lots": v["net_lots"],
                    "unrealized_pnl": float(v["pnl"]),
                }
                for k, v in by_underlying.items()
            },
            "positions_needing_rollover": len([p for p in positions if p.needs_rollover]),
        }


# Factory function
def create_futures_engine(
    event_bus: Optional[EventBus] = None,
    **kwargs
) -> FuturesTradingEngine:
    """Create a configured FuturesTradingEngine instance."""
    return FuturesTradingEngine(event_bus=event_bus, **kwargs)
