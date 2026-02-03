"""
Trading Repository
KeepGaining Trading Platform

Data access layer for trading entities: strategies, orders, trades, positions.
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, or_, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.db.models.trading import (
    StrategyConfig,
    StrategyDefinition,
    Order,
    Trade,
    Position,
)


class StrategyConfigRepository(BaseRepository[StrategyConfig]):
    """Repository for strategy configuration."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(StrategyConfig, session)
    
    async def get_active_strategies(self) -> List[StrategyConfig]:
        """Get all active strategy configurations."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.is_active == True)
            .order_by(self.model.strategy_name)
        )
        return list(result.scalars().all())
    
    async def get_by_name(self, name: str) -> Optional[StrategyConfig]:
        """Get strategy by name."""
        return await self.get_by_field("strategy_name", name)
    
    async def get_by_definition(
        self,
        definition_id: str,
    ) -> List[StrategyConfig]:
        """Get all configurations for a strategy definition."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.strategy_definition_id == definition_id)
            .order_by(self.model.created_at)
        )
        return list(result.scalars().all())
    
    async def activate_strategy(self, strategy_id: str) -> bool:
        """Activate a strategy."""
        strategy = await self.get(strategy_id)
        if strategy:
            strategy.is_active = True
            await self.session.commit()
            return True
        return False
    
    async def deactivate_strategy(self, strategy_id: str) -> bool:
        """Deactivate a strategy."""
        strategy = await self.get(strategy_id)
        if strategy:
            strategy.is_active = False
            await self.session.commit()
            return True
        return False
    
    async def update_params(
        self,
        strategy_id: str,
        params: Dict[str, Any],
    ) -> Optional[StrategyConfig]:
        """Update strategy parameters."""
        strategy = await self.get(strategy_id)
        if strategy:
            strategy.params = {**strategy.params, **params}
            await self.session.commit()
            await self.session.refresh(strategy)
            return strategy
        return None


class StrategyDefinitionRepository(BaseRepository[StrategyDefinition]):
    """Repository for strategy definitions."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(StrategyDefinition, session)
    
    async def get_by_code(self, code: str) -> Optional[StrategyDefinition]:
        """Get strategy definition by code."""
        return await self.get_by_field("strategy_code", code)
    
    async def get_active_definitions(self) -> List[StrategyDefinition]:
        """Get all active strategy definitions."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.is_active == True)
            .order_by(self.model.strategy_name)
        )
        return list(result.scalars().all())
    
    async def get_by_category(
        self,
        category: str,
    ) -> List[StrategyDefinition]:
        """Get strategies by category."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.category == category)
            .order_by(self.model.strategy_name)
        )
        return list(result.scalars().all())


class OrderRepository(BaseRepository[Order]):
    """Repository for orders."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(Order, session)
    
    async def get_by_broker_order_id(
        self,
        broker_order_id: str,
    ) -> Optional[Order]:
        """Get order by broker order ID."""
        return await self.get_by_field("broker_order_id", broker_order_id)
    
    async def get_pending_orders(
        self,
        strategy_id: Optional[str] = None,
    ) -> List[Order]:
        """Get all pending orders."""
        conditions = [
            self.model.status.in_(["PENDING", "OPEN", "TRIGGER_PENDING"]),
        ]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.order_timestamp.desc())
        )
        return list(result.scalars().all())
    
    async def get_today_orders(
        self,
        strategy_id: Optional[str] = None,
    ) -> List[Order]:
        """Get all orders placed today."""
        today_start = datetime.combine(date.today(), datetime.min.time())
        
        conditions = [self.model.order_timestamp >= today_start]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.order_timestamp.desc())
        )
        return list(result.scalars().all())
    
    async def get_orders_by_status(
        self,
        status: str,
        strategy_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Order]:
        """Get orders by status."""
        conditions = [self.model.status == status]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.order_timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_orders_by_instrument(
        self,
        instrument_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Order]:
        """Get orders for an instrument."""
        conditions = [self.model.instrument_id == instrument_id]
        
        if start_date:
            conditions.append(
                self.model.order_timestamp >= datetime.combine(
                    start_date, datetime.min.time()
                )
            )
        if end_date:
            conditions.append(
                self.model.order_timestamp <= datetime.combine(
                    end_date, datetime.max.time()
                )
            )
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.order_timestamp.desc())
        )
        return list(result.scalars().all())
    
    async def update_order_status(
        self,
        order_id: str,
        status: str,
        filled_qty: Optional[int] = None,
        average_price: Optional[float] = None,
        rejection_reason: Optional[str] = None,
    ) -> Optional[Order]:
        """Update order status."""
        order = await self.get(order_id)
        if not order:
            return None
        
        order.status = status
        
        if filled_qty is not None:
            order.filled_quantity = filled_qty
        if average_price is not None:
            order.average_price = Decimal(str(average_price))
        if rejection_reason:
            order.rejection_reason = rejection_reason
        
        await self.session.commit()
        await self.session.refresh(order)
        return order
    
    async def get_order_summary(
        self,
        start_date: date,
        end_date: date,
        strategy_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get order summary statistics."""
        conditions = [
            self.model.order_timestamp >= datetime.combine(
                start_date, datetime.min.time()
            ),
            self.model.order_timestamp <= datetime.combine(
                end_date, datetime.max.time()
            ),
        ]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        
        # Get counts by status
        result = await self.session.execute(
            select(self.model.status, func.count(self.model.id))
            .where(and_(*conditions))
            .group_by(self.model.status)
        )
        
        status_counts = {row[0]: row[1] for row in result.fetchall()}
        
        return {
            "total_orders": sum(status_counts.values()),
            "by_status": status_counts,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }


class TradeRepository(BaseRepository[Trade]):
    """Repository for trades."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(Trade, session)
    
    async def get_by_broker_trade_id(
        self,
        broker_trade_id: str,
    ) -> Optional[Trade]:
        """Get trade by broker trade ID."""
        return await self.get_by_field("broker_trade_id", broker_trade_id)
    
    async def get_trades_for_order(self, order_id: str) -> List[Trade]:
        """Get all trades for an order."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.order_id == order_id)
            .order_by(self.model.trade_timestamp)
        )
        return list(result.scalars().all())
    
    async def get_today_trades(
        self,
        strategy_id: Optional[str] = None,
    ) -> List[Trade]:
        """Get all trades executed today."""
        today_start = datetime.combine(date.today(), datetime.min.time())
        
        conditions = [self.model.trade_timestamp >= today_start]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.trade_timestamp.desc())
        )
        return list(result.scalars().all())
    
    async def get_trades_by_date_range(
        self,
        start_date: date,
        end_date: date,
        strategy_id: Optional[str] = None,
        instrument_id: Optional[str] = None,
    ) -> List[Trade]:
        """Get trades in a date range."""
        conditions = [
            self.model.trade_timestamp >= datetime.combine(
                start_date, datetime.min.time()
            ),
            self.model.trade_timestamp <= datetime.combine(
                end_date, datetime.max.time()
            ),
        ]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        if instrument_id:
            conditions.append(self.model.instrument_id == instrument_id)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.trade_timestamp)
        )
        return list(result.scalars().all())
    
    async def get_trade_summary(
        self,
        start_date: date,
        end_date: date,
        strategy_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get trade summary statistics."""
        trades = await self.get_trades_by_date_range(
            start_date, end_date, strategy_id
        )
        
        if not trades:
            return {
                "total_trades": 0,
                "buy_trades": 0,
                "sell_trades": 0,
                "total_turnover": 0,
            }
        
        buy_trades = [t for t in trades if t.side == "BUY"]
        sell_trades = [t for t in trades if t.side == "SELL"]
        
        total_turnover = sum(
            float(t.price) * t.quantity for t in trades
        )
        
        return {
            "total_trades": len(trades),
            "buy_trades": len(buy_trades),
            "sell_trades": len(sell_trades),
            "total_turnover": round(total_turnover, 2),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }


class PositionRepository(BaseRepository[Position]):
    """Repository for positions."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(Position, session)
    
    async def get_open_positions(
        self,
        strategy_id: Optional[str] = None,
    ) -> List[Position]:
        """Get all open positions."""
        conditions = [self.model.status == "OPEN"]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.entry_time.desc())
        )
        return list(result.scalars().all())
    
    async def get_position_by_instrument(
        self,
        instrument_id: str,
        strategy_id: Optional[str] = None,
        status: str = "OPEN",
    ) -> Optional[Position]:
        """Get position for an instrument."""
        conditions = [
            self.model.instrument_id == instrument_id,
            self.model.status == status,
        ]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.entry_time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_today_positions(
        self,
        strategy_id: Optional[str] = None,
        include_closed: bool = True,
    ) -> List[Position]:
        """Get all positions opened today."""
        today_start = datetime.combine(date.today(), datetime.min.time())
        
        conditions = [self.model.entry_time >= today_start]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        if not include_closed:
            conditions.append(self.model.status == "OPEN")
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.entry_time.desc())
        )
        return list(result.scalars().all())
    
    async def update_position_prices(
        self,
        position_id: str,
        current_price: float,
    ) -> Optional[Position]:
        """Update position with current market price."""
        position = await self.get(position_id)
        if not position:
            return None
        
        position.current_price = Decimal(str(current_price))
        
        # Calculate unrealized P&L
        price_diff = current_price - float(position.average_entry_price)
        if position.side == "SHORT":
            price_diff = -price_diff
        
        position.unrealized_pnl = Decimal(str(price_diff * position.quantity))
        
        await self.session.commit()
        await self.session.refresh(position)
        return position
    
    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_time: Optional[datetime] = None,
    ) -> Optional[Position]:
        """Close a position."""
        position = await self.get(position_id)
        if not position:
            return None
        
        position.status = "CLOSED"
        position.exit_price = Decimal(str(exit_price))
        position.exit_time = exit_time or datetime.now()
        
        # Calculate realized P&L
        price_diff = exit_price - float(position.average_entry_price)
        if position.side == "SHORT":
            price_diff = -price_diff
        
        position.realized_pnl = Decimal(str(price_diff * position.quantity))
        position.unrealized_pnl = Decimal("0")
        
        await self.session.commit()
        await self.session.refresh(position)
        return position
    
    async def update_stop_loss(
        self,
        position_id: str,
        stop_loss: float,
    ) -> Optional[Position]:
        """Update position stop loss."""
        position = await self.get(position_id)
        if position:
            position.stop_loss = Decimal(str(stop_loss))
            await self.session.commit()
            await self.session.refresh(position)
            return position
        return None
    
    async def update_target(
        self,
        position_id: str,
        target: float,
    ) -> Optional[Position]:
        """Update position target."""
        position = await self.get(position_id)
        if position:
            position.target = Decimal(str(target))
            await self.session.commit()
            await self.session.refresh(position)
            return position
        return None
    
    async def get_pnl_summary(
        self,
        start_date: date,
        end_date: date,
        strategy_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get P&L summary for closed positions."""
        conditions = [
            self.model.status == "CLOSED",
            self.model.exit_time.isnot(None),
            self.model.exit_time >= datetime.combine(
                start_date, datetime.min.time()
            ),
            self.model.exit_time <= datetime.combine(
                end_date, datetime.max.time()
            ),
        ]
        
        if strategy_id:
            conditions.append(self.model.strategy_id == strategy_id)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
        )
        positions = list(result.scalars().all())
        
        if not positions:
            return {
                "total_positions": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0,
                "win_rate": 0,
            }
        
        winning = [p for p in positions if float(p.realized_pnl or 0) > 0]
        losing = [p for p in positions if float(p.realized_pnl or 0) < 0]
        total_pnl = sum(float(p.realized_pnl or 0) for p in positions)
        
        return {
            "total_positions": len(positions),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(len(winning) / len(positions) * 100, 2),
            "avg_win": round(
                sum(float(p.realized_pnl) for p in winning) / len(winning), 2
            ) if winning else 0,
            "avg_loss": round(
                sum(float(p.realized_pnl) for p in losing) / len(losing), 2
            ) if losing else 0,
        }


__all__ = [
    "StrategyConfigRepository",
    "StrategyDefinitionRepository",
    "OrderRepository",
    "TradeRepository",
    "PositionRepository",
]
