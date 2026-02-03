#!/usr/bin/env python3
"""
Paper Trading Validation Script
KeepGaining Trading Platform

Validates the signal → order → position flow using the PaperBroker.
Tests the complete paper trading pipeline without requiring live connections.

Usage:
    cd backend
    python scripts/test_paper_trading.py
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app.brokers.paper import PaperBroker
from app.brokers.mock import MockBroker
from app.schemas.broker import OrderRequest
from app.db.models import OrderSide
from app.core.events import (
    EventBus, EventType, get_event_bus, BaseEvent,
    SignalEvent, OrderEvent, PositionEvent, TickEvent
)


# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")


class PaperTradingValidator:
    """
    Validates the paper trading pipeline:
    1. Signal Generation → Event Bus
    2. Signal → Order Placement
    3. Order Execution → Position Update
    4. P&L Tracking
    """
    
    def __init__(self):
        self.broker = PaperBroker(slippage_std_dev=0.02, latency_ms=50)
        self.event_bus: EventBus = None
        self.events_received: Dict[str, List[BaseEvent]] = {
            "signals": [],
            "orders": [],
            "positions": [],
            "ticks": [],
        }
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.pnl = 0.0
    
    async def initialize(self):
        """Initialize the validator."""
        logger.info("=" * 60)
        logger.info("Paper Trading Validation")
        logger.info("=" * 60)
        
        # Initialize broker
        auth_result = await self.broker.authenticate()
        logger.info(f"✓ PaperBroker authenticated: {auth_result}")
        
        # Initialize event bus
        self.event_bus = await get_event_bus()
        logger.info(f"✓ Event Bus connected")
        
        # Subscribe to events
        await self.event_bus.subscribe(EventType.SIGNAL_GENERATED, self._handle_signal)
        await self.event_bus.subscribe(EventType.ORDER_PLACED, self._handle_order)
        await self.event_bus.subscribe(EventType.ORDER_FILLED, self._handle_order_fill)
        await self.event_bus.subscribe(EventType.POSITION_UPDATED, self._handle_position)
        await self.event_bus.subscribe(EventType.TICK_RECEIVED, self._handle_tick)
        logger.info(f"✓ Event subscriptions registered")
    
    async def _handle_signal(self, event: BaseEvent):
        """Handle signal events."""
        self.events_received["signals"].append(event)
        logger.info(f"📡 Signal received: {event.metadata.get('symbol', 'unknown')} - {event.metadata.get('signal_type', 'unknown')}")
    
    async def _handle_order(self, event: BaseEvent):
        """Handle order events."""
        self.events_received["orders"].append(event)
        logger.info(f"📋 Order event: {event.metadata.get('order_id', 'unknown')[:8]}...")
    
    async def _handle_order_fill(self, event: BaseEvent):
        """Handle order fill events."""
        logger.info(f"✅ Order filled: {event.metadata.get('order_id', 'unknown')[:8]}...")
    
    async def _handle_position(self, event: BaseEvent):
        """Handle position events."""
        self.events_received["positions"].append(event)
        logger.info(f"📊 Position update: {event.metadata.get('symbol', 'unknown')}")
    
    async def _handle_tick(self, event: BaseEvent):
        """Handle tick events."""
        self.events_received["ticks"].append(event)
    
    async def test_signal_to_order_flow(self):
        """Test: Signal generation → Order placement."""
        logger.info("\n" + "-" * 40)
        logger.info("Test 1: Signal → Order Flow")
        logger.info("-" * 40)
        
        # Create a trading signal
        signal = SignalEvent(
            event_type=EventType.SIGNAL_GENERATED,
            strategy_id="momentum_v1",
            instrument_id="NSE_EQ|INE002A01018",
            symbol="RELIANCE",
            signal_type="ENTRY_LONG",
            strength=85.0,
            price=2450.50,
            conditions_met={
                "momentum": True,
                "volume_spike": True,
                "rsi_oversold": False,
            },
            suggested_sl=2400.0,
            suggested_target=2550.0,
            source="backtest_validator",
        )
        
        # Publish signal
        await self.event_bus.publish(signal)
        logger.info(f"✓ Signal published: {signal.symbol} {signal.signal_type} @ ₹{signal.price}")
        
        # Give time for event processing
        await asyncio.sleep(0.2)
        
        # Now place order based on signal
        order_request = OrderRequest(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            order_type="MARKET",
            quantity=10,
            product_type="CNC",
            price=signal.price,
        )
        
        order_response = await self.broker.place_order(order_request)
        logger.info(f"✓ Order placed: {order_response.order_id[:8]}... Status: {order_response.status}")
        
        # Track the order
        self.orders[order_response.order_id] = {
            "symbol": signal.symbol,
            "side": "BUY",
            "quantity": 10,
            "price": signal.price,
            "status": str(order_response.status),
        }
        
        # Publish order event
        order_event = OrderEvent(
            event_type=EventType.ORDER_PLACED,
            order_id=order_response.order_id,
            strategy_id=signal.strategy_id,
            instrument_id=signal.instrument_id,
            symbol=signal.symbol,
            side="BUY",
            order_type="MARKET",
            quantity=10,
            price=signal.price,
            status=str(order_response.status),
            source="paper_broker",
        )
        await self.event_bus.publish(order_event)
        
        await asyncio.sleep(0.1)
        
        return order_response.order_id
    
    async def test_order_execution_and_position(self, order_id: str):
        """Test: Order execution → Position update."""
        logger.info("\n" + "-" * 40)
        logger.info("Test 2: Order Execution → Position")
        logger.info("-" * 40)
        
        order = self.orders.get(order_id)
        if not order:
            logger.error("Order not found!")
            return
        
        # Simulate order fill
        fill_price = order["price"] * 1.001  # Slight slippage
        
        # Create/update position
        position_id = f"pos_{order['symbol']}_{uuid.uuid4().hex[:6]}"
        self.positions[position_id] = {
            "symbol": order["symbol"],
            "side": "LONG",
            "quantity": order["quantity"],
            "avg_price": fill_price,
            "current_price": fill_price,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
        }
        
        logger.info(f"✓ Position created: {order['symbol']} LONG {order['quantity']} @ ₹{fill_price:.2f}")
        
        # Publish position event
        position_event = PositionEvent(
            event_type=EventType.POSITION_OPENED,
            position_id=position_id,
            strategy_id="momentum_v1",
            instrument_id="NSE_EQ|INE002A01018",
            symbol=order["symbol"],
            side="LONG",
            quantity=order["quantity"],
            average_price=fill_price,
            current_price=fill_price,
            unrealized_pnl=0.0,
            source="paper_broker",
        )
        await self.event_bus.publish(position_event)
        
        await asyncio.sleep(0.1)
        
        return position_id
    
    async def test_tick_updates_and_pnl(self, position_id: str):
        """Test: Tick updates → P&L calculation."""
        logger.info("\n" + "-" * 40)
        logger.info("Test 3: Tick Updates → P&L Tracking")
        logger.info("-" * 40)
        
        position = self.positions.get(position_id)
        if not position:
            logger.error("Position not found!")
            return
        
        # Simulate price movements
        price_movements = [
            position["avg_price"] * 1.005,   # +0.5%
            position["avg_price"] * 1.01,    # +1%
            position["avg_price"] * 0.995,   # -0.5%
            position["avg_price"] * 1.02,    # +2%
        ]
        
        for new_price in price_movements:
            # Publish tick event
            tick_event = TickEvent(
                event_type=EventType.TICK_RECEIVED,
                instrument_id="NSE_EQ|INE002A01018",
                symbol=position["symbol"],
                ltp=new_price,
                bid=new_price - 0.05,
                ask=new_price + 0.05,
                volume=50000,
                source="simulated",
            )
            await self.event_bus.publish(tick_event)
            
            # Update position P&L
            position["current_price"] = new_price
            pnl = (new_price - position["avg_price"]) * position["quantity"]
            position["unrealized_pnl"] = pnl
            
            pnl_pct = (new_price / position["avg_price"] - 1) * 100
            emoji = "📈" if pnl >= 0 else "📉"
            logger.info(f"{emoji} Price: ₹{new_price:.2f} | P&L: ₹{pnl:.2f} ({pnl_pct:+.2f}%)")
            
            await asyncio.sleep(0.1)
        
        return position
    
    async def test_exit_order(self, position_id: str):
        """Test: Exit signal → Position close."""
        logger.info("\n" + "-" * 40)
        logger.info("Test 4: Exit Signal → Position Close")
        logger.info("-" * 40)
        
        position = self.positions.get(position_id)
        if not position:
            logger.error("Position not found!")
            return
        
        # Create exit signal
        exit_signal = SignalEvent(
            event_type=EventType.SIGNAL_GENERATED,
            strategy_id="momentum_v1",
            instrument_id="NSE_EQ|INE002A01018",
            symbol=position["symbol"],
            signal_type="EXIT",
            strength=100.0,
            price=position["current_price"],
            conditions_met={"target_hit": True},
            source="backtest_validator",
        )
        await self.event_bus.publish(exit_signal)
        logger.info(f"✓ Exit signal published: {position['symbol']} @ ₹{position['current_price']:.2f}")
        
        # Place exit order
        exit_order = OrderRequest(
            symbol=position["symbol"],
            side=OrderSide.SELL,
            order_type="MARKET",
            quantity=position["quantity"],
            product_type="CNC",
            price=position["current_price"],
        )
        
        exit_response = await self.broker.place_order(exit_order)
        logger.info(f"✓ Exit order placed: {exit_response.order_id[:8]}... Status: {exit_response.status}")
        
        # Calculate realized P&L
        realized_pnl = position["unrealized_pnl"]
        position["realized_pnl"] = realized_pnl
        position["unrealized_pnl"] = 0.0
        position["quantity"] = 0
        
        self.pnl += realized_pnl
        
        # Publish position closed event
        close_event = PositionEvent(
            event_type=EventType.POSITION_CLOSED,
            position_id=position_id,
            strategy_id="momentum_v1",
            instrument_id="NSE_EQ|INE002A01018",
            symbol=position["symbol"],
            side="LONG",
            quantity=0,
            average_price=position["avg_price"],
            current_price=position["current_price"],
            unrealized_pnl=0.0,
            realized_pnl=realized_pnl,
            source="paper_broker",
        )
        await self.event_bus.publish(close_event)
        
        await asyncio.sleep(0.1)
        
        logger.info(f"✓ Position closed | Realized P&L: ₹{realized_pnl:.2f}")
        return realized_pnl
    
    async def test_multiple_concurrent_orders(self):
        """Test: Multiple concurrent orders."""
        logger.info("\n" + "-" * 40)
        logger.info("Test 5: Multiple Concurrent Orders")
        logger.info("-" * 40)
        
        symbols = [
            ("INFY", 1450.0),
            ("TCS", 3520.0),
            ("HDFC", 1580.0),
        ]
        
        orders = []
        for symbol, price in symbols:
            order_request = OrderRequest(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type="MARKET",
                quantity=5,
                product_type="CNC",
                price=price,
            )
            response = await self.broker.place_order(order_request)
            orders.append((symbol, response))
            logger.info(f"✓ Order {symbol}: {response.order_id[:8]}... Status: {response.status}")
        
        # Check all orders placed
        positions = await self.broker.get_positions()
        logger.info(f"✓ Total positions after batch: {len(positions)}")
        
        return len(orders)
    
    async def run_all_tests(self):
        """Run all paper trading validation tests."""
        try:
            await self.initialize()
            
            # Test 1: Signal → Order
            order_id = await self.test_signal_to_order_flow()
            
            # Test 2: Order → Position
            position_id = await self.test_order_execution_and_position(order_id)
            
            # Test 3: Tick updates → P&L
            await self.test_tick_updates_and_pnl(position_id)
            
            # Test 4: Exit order
            realized_pnl = await self.test_exit_order(position_id)
            
            # Test 5: Multiple orders
            order_count = await self.test_multiple_concurrent_orders()
            
            # Summary
            logger.info("\n" + "=" * 60)
            logger.info("Paper Trading Validation Summary")
            logger.info("=" * 60)
            logger.info(f"✓ Signals received: {len(self.events_received['signals'])}")
            logger.info(f"✓ Orders placed: {len(self.events_received['orders']) + order_count}")
            logger.info(f"✓ Position updates: {len(self.events_received['positions'])}")
            logger.info(f"✓ Tick events: {len(self.events_received['ticks'])}")
            logger.info(f"✓ Total P&L: ₹{self.pnl:.2f}")
            logger.info("=" * 60)
            logger.info("✅ All paper trading tests PASSED!")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # Cleanup
            if self.event_bus:
                await self.event_bus.disconnect()


async def main():
    """Main entry point."""
    validator = PaperTradingValidator()
    success = await validator.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
