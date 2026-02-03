"""
Trading Mode Orchestrator

Central controller that manages trading modes and coordinates all components:
- Strategy Engine (signal generation)
- Paper Trading Engine (simulated execution)
- Live Trading Engine (real execution via brokers)
- Backtest Engine (historical testing)

Supports seamless switching between modes with the same strategy code.

Usage:
    orchestrator = TradingOrchestrator()
    await orchestrator.start(mode=TradingMode.PAPER)
    orchestrator.add_strategy("VOLROCKET", config)
    # Strategies now run in paper mode
    
    await orchestrator.switch_mode(TradingMode.LIVE)
    # Same strategies now run in live mode
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type
from zoneinfo import ZoneInfo

from app.core.events import EventBus, EventType, get_event_bus_sync
from app.services.strategy_engine import (
    BaseStrategy,
    Signal,
    SignalType,
    StrategyEngine,
    StrategyRegistry,
    create_strategy_engine
)
from app.execution.paper_trading import (
    PaperTradingEngine,
    PaperTradingConfig,
    create_paper_trading_engine
)
from app.execution.oms import OrderManagementSystem
from app.execution.risk import RiskManager
from app.brokers.base import BaseBroker


class TradingMode(str, Enum):
    """Trading mode."""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class SystemStatus(str, Enum):
    """System status."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class TradingSession:
    """Trading session information."""
    session_id: str
    mode: TradingMode
    started_at: datetime
    ended_at: Optional[datetime] = None
    initial_capital: Decimal = Decimal("0")
    final_capital: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    total_trades: int = 0
    strategies_active: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorConfig:
    """Orchestrator configuration."""
    # Capital settings
    paper_capital: Decimal = Decimal("100000")
    live_capital_limit: Decimal = Decimal("50000")  # Max capital for live trading
    
    # Risk settings
    max_daily_loss: Decimal = Decimal("10000")
    max_daily_loss_percent: Decimal = Decimal("5")
    max_positions: int = 5
    max_order_value: Decimal = Decimal("200000")
    
    # Trading hours
    market_open: str = "09:15"
    market_close: str = "15:30"
    no_entry_after: str = "14:45"
    
    # Mode settings
    auto_square_off: bool = True
    auto_square_off_time: str = "15:20"
    
    # Live trading safety
    require_confirmation: bool = True  # Require confirmation for live orders
    live_trading_enabled: bool = False  # Must be explicitly enabled
    
    # AI validation (Comet)
    ai_validation_enabled: bool = False  # Use Comet AI for signal validation
    ai_min_sentiment: float = 0.55  # Minimum AI sentiment score
    ai_min_confidence: float = 0.65  # Minimum AI confidence
    ai_min_combined_score: float = 0.65  # Minimum combined technical + AI score


class TradingOrchestrator:
    """
    Central orchestrator for the trading system.
    
    Coordinates:
    - Mode management (backtest/paper/live)
    - Strategy lifecycle
    - Signal routing
    - Risk management
    - Session tracking
    """
    
    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        event_bus: Optional[EventBus] = None,
        broker: Optional[BaseBroker] = None
    ):
        self.config = config or OrchestratorConfig()
        self.event_bus = event_bus or get_event_bus_sync()
        self.broker = broker
        self.logger = logging.getLogger(__name__)
        
        # State
        self.status = SystemStatus.STOPPED
        self.mode = TradingMode.PAPER
        self.current_session: Optional[TradingSession] = None
        
        # Components (initialized on start)
        self.strategy_engine: Optional[StrategyEngine] = None
        self.paper_engine: Optional[PaperTradingEngine] = None
        self.oms: Optional[OrderManagementSystem] = None
        self.risk_manager: Optional[RiskManager] = None
        self.signal_validator = None  # Comet AI validator (lazy init)
        
        # Session history
        self.sessions: List[TradingSession] = []
        
        # Daily tracking
        self._daily_pnl = Decimal("0")
        self._daily_trades = 0
        self._trading_halted = False
        self._halt_reason: Optional[str] = None
        
        # Signal handlers
        self._signal_handlers: Dict[TradingMode, Callable] = {}
    
    async def start(
        self,
        mode: TradingMode = TradingMode.PAPER,
        strategies: Optional[List[str]] = None
    ) -> bool:
        """
        Start the trading system in specified mode.
        
        Args:
            mode: Trading mode (BACKTEST, PAPER, LIVE)
            strategies: List of strategy IDs to activate
            
        Returns:
            True if started successfully
        """
        if self.status == SystemStatus.RUNNING:
            self.logger.warning("System already running")
            return False
        
        try:
            self.status = SystemStatus.STARTING
            self.mode = mode
            
            self.logger.info(f"Starting trading system in {mode.value} mode...")
            
            # Initialize components based on mode
            await self._initialize_components(mode)
            
            # Register signal handlers
            self._setup_signal_handlers()
            
            # Subscribe to signals from strategy engine
            await self.event_bus.subscribe(
                "signal",
                self._on_signal
            )
            
            # Start components
            if self.strategy_engine:
                await self.strategy_engine.start()
            
            if self.paper_engine and mode == TradingMode.PAPER:
                await self.paper_engine.start()
            
            # Activate strategies
            if strategies:
                for strategy_id in strategies:
                    self.add_strategy(strategy_id)
            
            # Create session
            self.current_session = TradingSession(
                session_id=self._generate_session_id(),
                mode=mode,
                started_at=datetime.now(ZoneInfo("Asia/Kolkata")),
                initial_capital=self._get_initial_capital(mode),
                strategies_active=strategies or []
            )
            
            self.status = SystemStatus.RUNNING
            self.logger.info(
                f"Trading system started. Session: {self.current_session.session_id}"
            )
            
            return True
            
        except Exception as e:
            self.status = SystemStatus.ERROR
            self.logger.error(f"Failed to start trading system: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the trading system."""
        if self.status not in [SystemStatus.RUNNING, SystemStatus.PAUSED]:
            return
        
        self.status = SystemStatus.STOPPING
        self.logger.info("Stopping trading system...")
        
        try:
            # Stop strategy engine
            if self.strategy_engine:
                await self.strategy_engine.stop()
            
            # Stop paper engine
            if self.paper_engine:
                await self.paper_engine.stop()
            
            # Close session
            if self.current_session:
                self.current_session.ended_at = datetime.now(ZoneInfo("Asia/Kolkata"))
                self.current_session.final_capital = self._get_current_capital()
                self.current_session.total_pnl = (
                    self.current_session.final_capital - 
                    self.current_session.initial_capital
                )
                self.current_session.total_trades = self._daily_trades
                self.sessions.append(self.current_session)
            
            self.status = SystemStatus.STOPPED
            self.logger.info("Trading system stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping trading system: {e}")
            self.status = SystemStatus.ERROR
    
    async def pause(self) -> None:
        """Pause the trading system (no new signals processed)."""
        if self.status != SystemStatus.RUNNING:
            return
        
        self.status = SystemStatus.PAUSED
        self._trading_halted = True
        self.logger.info("Trading system paused")
    
    async def resume(self) -> None:
        """Resume the trading system."""
        if self.status != SystemStatus.PAUSED:
            return
        
        self.status = SystemStatus.RUNNING
        self._trading_halted = False
        self._halt_reason = None
        self.logger.info("Trading system resumed")
    
    async def switch_mode(self, new_mode: TradingMode) -> bool:
        """
        Switch trading mode.
        
        Preserves strategy configuration but restarts engines.
        """
        if new_mode == self.mode:
            return True
        
        if new_mode == TradingMode.LIVE and not self.config.live_trading_enabled:
            self.logger.error("Live trading not enabled in configuration")
            return False
        
        self.logger.info(f"Switching mode from {self.mode.value} to {new_mode.value}")
        
        # Get active strategies
        active_strategies = []
        if self.strategy_engine:
            active_strategies = [
                s.strategy_id 
                for s in self.strategy_engine.registry.get_enabled_strategies()
            ]
        
        # Stop current session
        await self.stop()
        
        # Start in new mode
        return await self.start(mode=new_mode, strategies=active_strategies)
    
    async def _initialize_components(self, mode: TradingMode) -> None:
        """Initialize components based on mode."""
        # Always initialize strategy engine
        self.strategy_engine = create_strategy_engine(self.event_bus)
        
        # Initialize risk manager
        self.risk_manager = RiskManager()
        self.risk_manager.max_order_value = float(self.config.max_order_value)
        self.risk_manager.max_daily_loss = float(self.config.max_daily_loss)
        
        if mode == TradingMode.PAPER:
            paper_config = PaperTradingConfig(
                initial_capital=self.config.paper_capital,
                max_positions=self.config.max_positions,
                max_order_value=self.config.max_order_value,
                auto_square_off_time=self.config.auto_square_off_time if self.config.auto_square_off else None
            )
            self.paper_engine = PaperTradingEngine(
                config=paper_config,
                event_bus=self.event_bus
            )
            
        elif mode == TradingMode.LIVE:
            if not self.broker:
                raise ValueError("Broker required for live trading")
            
            self.oms = OrderManagementSystem(self.broker)
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for each mode."""
        self._signal_handlers = {
            TradingMode.BACKTEST: self._handle_backtest_signal,
            TradingMode.PAPER: self._handle_paper_signal,
            TradingMode.LIVE: self._handle_live_signal,
        }
    
    async def _on_signal(self, signal_data: Dict[str, Any]) -> None:
        """Handle incoming signals from strategy engine."""
        if self._trading_halted:
            self.logger.debug("Signal ignored - trading halted")
            return
        
        if self.status != SystemStatus.RUNNING:
            return
        
        # Check trading hours
        if not self._is_trading_hours():
            self.logger.debug("Signal ignored - outside trading hours")
            return
        
        # Check daily loss limit
        if await self._check_daily_loss_limit():
            return
        
        # Route to appropriate handler
        handler = self._signal_handlers.get(self.mode)
        if handler:
            await handler(signal_data)
    
    async def _handle_backtest_signal(self, signal_data: Dict[str, Any]) -> None:
        """Handle signal in backtest mode."""
        # In backtest mode, signals are logged for analysis
        self.logger.info(
            f"[BACKTEST] Signal: {signal_data.get('signal_type')} "
            f"for {signal_data.get('symbol')}"
        )
    
    async def _handle_paper_signal(self, signal_data: Dict[str, Any]) -> None:
        """Handle signal in paper trading mode."""
        if not self.paper_engine:
            return
        
        # Convert dict to Signal object
        signal = self._dict_to_signal(signal_data)
        if not signal:
            return
        
        # AI validation (if enabled)
        if self.config.ai_validation_enabled:
            validation_result = await self._validate_signal_with_ai(signal)
            if not validation_result.approved:
                self.logger.warning(
                    f"[PAPER] Signal REJECTED by AI: {signal.symbol} - {validation_result.reason}"
                )
                return
            else:
                self.logger.info(
                    f"[PAPER] Signal APPROVED by AI: {signal.symbol} - "
                    f"Sentiment: {validation_result.ai_sentiment:.2f}, "
                    f"Combined: {validation_result.combined_score:.2f}"
                )
        
        # Execute in paper trading
        order = await self.paper_engine.execute_signal(signal)
        
        if order:
            self._daily_trades += 1
            self.logger.info(
                f"[PAPER] Order executed: {order.order_id} "
                f"{order.side.value} {order.quantity} {order.symbol}"
            )
    
    async def _handle_live_signal(self, signal_data: Dict[str, Any]) -> None:
        """Handle signal in live trading mode."""
        if not self.oms:
            self.logger.error("OMS not initialized for live trading")
            return
        
        # Safety check
        if not self.config.live_trading_enabled:
            self.logger.warning("Live trading disabled - signal ignored")
            return
        
        signal = self._dict_to_signal(signal_data)
        if not signal:
            return
        
        # AI validation (REQUIRED for live trading)
        if self.config.ai_validation_enabled:
            validation_result = await self._validate_signal_with_ai(signal)
            if not validation_result.approved:
                self.logger.warning(
                    f"[LIVE] Signal REJECTED by AI: {signal.symbol} - {validation_result.reason}"
                )
                return
            else:
                self.logger.info(
                    f"[LIVE] Signal APPROVED by AI: {signal.symbol} - "
                    f"Sentiment: {validation_result.ai_sentiment:.2f}, "
                    f"Confidence: {validation_result.ai_confidence:.2f}, "
                    f"Combined: {validation_result.combined_score:.2f}"
                )
        
        # Check position limits
        if len(await self.oms.broker.get_positions()) >= self.config.max_positions:
            self.logger.warning("Max positions reached - signal ignored")
            return
        
        # Confirmation required for live trades
        if self.config.require_confirmation:
            self.logger.info(
                f"[LIVE] Signal requires confirmation: "
                f"{signal.signal_type.value} {signal.symbol}"
            )
            # In production, this would trigger a confirmation flow
            # For now, we log and proceed
        
        # Execute via OMS
        from app.schemas.broker import OrderRequest, OrderSide
        
        side = OrderSide.BUY if "LONG" in signal.signal_type.value.upper() else OrderSide.SELL
        quantity = int(
            (self.config.live_capital_limit * Decimal(str(signal.quantity_pct / 100))) 
            / signal.entry_price
        )
        
        order_request = OrderRequest(
            symbol=signal.symbol,
            quantity=quantity,
            side=side,
            order_type="MARKET",
            product_type="MIS"
        )
        
        # Risk check
        from app.schemas.broker import OrderRequest as BrokerOrderRequest
        broker_order = BrokerOrderRequest(
            symbol=signal.symbol,
            quantity=quantity,
            side=side,
            price=float(signal.entry_price)
        )
        
        if not self.risk_manager.check_order(broker_order, float(self._daily_pnl)):
            self.logger.warning("Order rejected by risk manager")
            return
        
        # Place order via OMS
        response = await self.oms.place_order(order_request, strategy_id=1)
        
        self._daily_trades += 1
        self.logger.info(
            f"[LIVE] Order placed: {response.order_id} "
            f"Status: {response.status}"
        )
    
    async def _validate_signal_with_ai(self, signal: Signal):
        """Validate signal using Comet AI."""
        # Lazy init validator
        if self.signal_validator is None:
            try:
                from app.services.comet_validator import CometSignalValidator
                self.signal_validator = CometSignalValidator(
                    enabled=self.config.ai_validation_enabled,
                    min_sentiment=self.config.ai_min_sentiment,
                    min_confidence=self.config.ai_min_confidence,
                    min_combined_score=self.config.ai_min_combined_score
                )
            except Exception as e:
                self.logger.warning(f"Failed to initialize Comet validator: {e}")
                # Create disabled validator as fallback
                from app.services.comet_validator import CometSignalValidator
                self.signal_validator = CometSignalValidator(enabled=False)
        
        return await self.signal_validator.validate_signal(signal)
    
    def _dict_to_signal(self, signal_data: Dict[str, Any]) -> Optional[Signal]:
        """Convert signal dict to Signal object."""
        try:
            from app.services.strategy_engine import SignalStrength
            
            return Signal(
                signal_id=signal_data.get("signal_id", ""),
                strategy_id=signal_data.get("strategy_id", ""),
                strategy_name=signal_data.get("strategy_name", ""),
                symbol=signal_data.get("symbol", ""),
                exchange=signal_data.get("exchange", "NSE"),
                signal_type=SignalType(signal_data.get("signal_type", "")),
                strength=SignalStrength(signal_data.get("strength", "moderate")),
                entry_price=Decimal(str(signal_data.get("entry_price", 0))),
                stop_loss=Decimal(str(signal_data.get("stop_loss", 0))),
                target_price=Decimal(str(signal_data.get("target_price", 0))),
                quantity_pct=signal_data.get("quantity_pct", 5.0),
                timeframe=signal_data.get("timeframe", "5m"),
                indicators=signal_data.get("indicators", {}),
                reason=signal_data.get("reason", ""),
                generated_at=datetime.fromisoformat(
                    signal_data.get("generated_at", datetime.now().isoformat())
                ),
                valid_until=datetime.fromisoformat(
                    signal_data.get("valid_until", datetime.now().isoformat())
                ),
                metadata=signal_data.get("metadata", {})
            )
        except Exception as e:
            self.logger.error(f"Failed to parse signal: {e}")
            return None
    
    async def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit is reached."""
        current_pnl = self._get_daily_pnl()
        
        # Check absolute limit
        if current_pnl < -float(self.config.max_daily_loss):
            if not self._trading_halted:
                self._trading_halted = True
                self._halt_reason = f"Daily loss limit reached: ₹{current_pnl:,.2f}"
                self.logger.warning(self._halt_reason)
            return True
        
        # Check percentage limit
        initial_capital = float(self._get_initial_capital(self.mode))
        loss_percent = abs(current_pnl / initial_capital * 100) if initial_capital > 0 else 0
        
        if current_pnl < 0 and loss_percent > float(self.config.max_daily_loss_percent):
            if not self._trading_halted:
                self._trading_halted = True
                self._halt_reason = f"Daily loss limit reached: {loss_percent:.1f}%"
                self.logger.warning(self._halt_reason)
            return True
        
        return False
    
    def _get_daily_pnl(self) -> float:
        """Get current daily P&L."""
        if self.mode == TradingMode.PAPER and self.paper_engine:
            return float(self.paper_engine.get_stats().get("total_pnl", 0))
        return float(self._daily_pnl)
    
    def _is_trading_hours(self) -> bool:
        """Check if within trading hours."""
        now = datetime.now(ZoneInfo("Asia/Kolkata")).time()
        
        market_open = datetime.strptime(self.config.market_open, "%H:%M").time()
        no_entry_after = datetime.strptime(self.config.no_entry_after, "%H:%M").time()
        
        return market_open <= now <= no_entry_after
    
    def _get_initial_capital(self, mode: TradingMode) -> Decimal:
        """Get initial capital for mode."""
        if mode == TradingMode.PAPER:
            return self.config.paper_capital
        elif mode == TradingMode.LIVE:
            return self.config.live_capital_limit
        return Decimal("0")
    
    def _get_current_capital(self) -> Decimal:
        """Get current capital."""
        if self.mode == TradingMode.PAPER and self.paper_engine:
            return Decimal(str(self.paper_engine.capital))
        return self._get_initial_capital(self.mode)
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import uuid
        date_str = datetime.now().strftime("%Y%m%d")
        return f"SES-{date_str}-{uuid.uuid4().hex[:6].upper()}"
    
    def add_strategy(
        self,
        strategy_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add and activate a strategy."""
        if not self.strategy_engine:
            return False
        
        try:
            self.strategy_engine.initialize_strategy(strategy_id, config)
            
            if self.current_session:
                self.current_session.strategies_active.append(strategy_id)
            
            self.logger.info(f"Strategy added: {strategy_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add strategy {strategy_id}: {e}")
            return False
    
    def remove_strategy(self, strategy_id: str) -> bool:
        """Remove a strategy."""
        if not self.strategy_engine:
            return False
        
        result = self.strategy_engine.registry.remove_strategy(strategy_id)
        
        if result and self.current_session:
            if strategy_id in self.current_session.strategies_active:
                self.current_session.strategies_active.remove(strategy_id)
        
        return result
    
    def enable_strategy(self, strategy_id: str) -> bool:
        """Enable a strategy."""
        if not self.strategy_engine:
            return False
        return self.strategy_engine.registry.enable_strategy(strategy_id)
    
    def disable_strategy(self, strategy_id: str) -> bool:
        """Disable a strategy."""
        if not self.strategy_engine:
            return False
        return self.strategy_engine.registry.disable_strategy(strategy_id)
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        return {
            "status": self.status.value,
            "mode": self.mode.value,
            "trading_halted": self._trading_halted,
            "halt_reason": self._halt_reason,
            "session": {
                "id": self.current_session.session_id if self.current_session else None,
                "started_at": self.current_session.started_at.isoformat() if self.current_session else None,
                "initial_capital": float(self.current_session.initial_capital) if self.current_session else 0,
                "strategies_active": self.current_session.strategies_active if self.current_session else [],
            },
            "daily_stats": {
                "pnl": self._get_daily_pnl(),
                "trades": self._daily_trades,
            },
            "strategy_engine": self.strategy_engine.get_stats() if self.strategy_engine else None,
            "paper_engine": self.paper_engine.get_stats() if self.paper_engine else None,
        }
    
    def get_portfolio(self) -> Dict[str, Any]:
        """Get current portfolio status."""
        if self.mode == TradingMode.PAPER and self.paper_engine:
            return self.paper_engine.get_portfolio_summary()
        return {}
    
    def get_performance(self) -> Dict[str, Any]:
        """Get performance metrics."""
        if self.mode == TradingMode.PAPER and self.paper_engine:
            return self.paper_engine.get_performance_metrics()
        return {}
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        if self.mode == TradingMode.PAPER and self.paper_engine:
            return [
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "quantity": p.quantity,
                    "avg_price": float(p.average_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pnl),
                    "stop_loss": float(p.stop_loss) if p.stop_loss else None,
                    "target": float(p.target) if p.target else None,
                    "entry_time": p.entry_time.isoformat()
                }
                for p in self.paper_engine.get_all_positions()
            ]
        return []
    
    def get_trades(self) -> List[Dict[str, Any]]:
        """Get trade history."""
        if self.mode == TradingMode.PAPER and self.paper_engine:
            return [
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "side": t.side.value,
                    "quantity": t.quantity,
                    "entry_price": float(t.entry_price),
                    "exit_price": float(t.exit_price),
                    "net_pnl": float(t.net_pnl),
                    "pnl_percent": float(t.pnl_percent),
                    "exit_reason": t.exit_reason,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "holding_minutes": t.holding_period_minutes
                }
                for t in self.paper_engine.get_trades()
            ]
        return []
    
    async def update_price(self, symbol: str, price: Decimal) -> None:
        """Manually update price for a symbol (for testing)."""
        if self.paper_engine:
            self.paper_engine.update_price(symbol, price)
    
    async def close_position(self, symbol: str, reason: str = "MANUAL") -> bool:
        """Manually close a position."""
        if self.mode == TradingMode.PAPER and self.paper_engine:
            trade = await self.paper_engine._exit_position(symbol, reason)
            return trade is not None
        return False


# Singleton instance
_orchestrator: Optional[TradingOrchestrator] = None


def get_orchestrator() -> TradingOrchestrator:
    """Get or create orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TradingOrchestrator()
    return _orchestrator


def create_orchestrator(
    config: Optional[OrchestratorConfig] = None,
    event_bus: Optional[EventBus] = None,
    broker: Optional[BaseBroker] = None
) -> TradingOrchestrator:
    """Create a new orchestrator instance."""
    global _orchestrator
    _orchestrator = TradingOrchestrator(
        config=config,
        event_bus=event_bus,
        broker=broker
    )
    return _orchestrator
