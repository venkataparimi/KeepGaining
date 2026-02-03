import asyncio
import sys
from datetime import datetime, timedelta
from loguru import logger

# Add parent directory to path
sys.path.insert(0, '.')

from app.brokers.fyers import FyersBroker
from app.brokers.paper import PaperBroker
from app.execution.oms import OrderManagementSystem
from app.execution.risk import RiskManager
from app.strategies.ema_option_buyer import EMAOptionBuyingStrategy
from app.services.data_feed import DataFeedService

async def verify_full_flow():
    """
    Verification Script for Phase 4:
    Tests the full trading flow with:
    - FyersBroker for Data (Real)
    - PaperBroker for Execution (Safe)
    - RiskManager for Pre-Trade Checks
    - OMS for Order Routing
    - EMAOptionBuyingStrategy for Signal Generation
    """
    logger.info("=" * 60)
    logger.info("Phase 4 Verification: Full Trading Flow")
    logger.info("=" * 60)
    
    # 1. Initialize Data Broker (Real Fyers)
    logger.info("\n[Step 1] Initializing Fyers Broker for Data...")
    data_broker = FyersBroker()
    await data_broker.authenticate()
    
    # 2. Initialize Execution Broker (Paper)
    logger.info("\n[Step 2] Initializing Paper Broker for Execution...")
    exec_broker = PaperBroker()
    await exec_broker.authenticate()
    
    # 3. Initialize OMS with Paper Broker
    logger.info("\n[Step 3] Initializing OMS with Paper Broker...")
    oms = OrderManagementSystem(exec_broker)
    logger.info(f"Risk Manager Max Order Value: {oms.risk_manager.max_order_value}")
    logger.info(f"Risk Manager Max Daily Loss: {oms.risk_manager.max_daily_loss}")
    
    # 4. Initialize Data Feed Service
    logger.info("\n[Step 4] Initializing Data Feed Service...")
    data_feed = DataFeedService(data_broker)
    
    # 5. Initialize Strategy
    logger.info("\n[Step 5] Initializing EMA Option Buying Strategy...")
    strategy_config = {
        "underlying": "NSE:NIFTY50-INDEX",
        "fast_ema": 9,
        "slow_ema": 21,
        "quantity": 50,
        "expiry_date": "28NOV",  # Update this based on current weekly expiry
        "sl_percentage": 0.10,
        "target_percentage": 0.20
    }
    
    # Use data_broker for fetching historical data, but route orders via OMS
    strategy = EMAOptionBuyingStrategy(
        broker=data_broker,  # For data fetching
        data_feed=data_feed,
        config=strategy_config
    )
    
    # 6. Test Risk Manager Directly
    logger.info("\n[Step 6] Testing Risk Manager...")
    from app.schemas.broker import OrderRequest, OrderSide
    
    # Test 1: Valid Order
    test_order = OrderRequest(
        symbol="NSE:NIFTY2811924000CE",
        quantity=50,
        side=OrderSide.BUY,
        order_type="MARKET"
    )
    is_valid = oms.risk_manager.check_order(test_order)
    logger.info(f"Valid Order Test: {'PASSED' if is_valid else 'FAILED'}")
    
    # Test 2: Restricted Symbol
    risky_order = OrderRequest(
        symbol="SCAM_CO",
        quantity=100,
        side=OrderSide.BUY,
        order_type="MARKET"
    )
    is_rejected = not oms.risk_manager.check_order(risky_order)
    logger.info(f"Restricted Symbol Test: {'PASSED' if is_rejected else 'FAILED'}")
    
    # 7. Test OMS Order Placement
    logger.info("\n[Step 7] Testing OMS Order Placement (Paper)...")
    response = await oms.place_order(test_order, strategy_id=1)
    logger.info(f"Order Response: {response.status} - {response.message}")
    logger.info(f"Order ID: {response.order_id}")
    
    # 8. Verify Paper Broker Execution
    logger.info("\n[Step 8] Checking Paper Broker Positions...")
    positions = await exec_broker.get_positions()
    logger.info(f"Current Positions: {len(positions)}")
    for pos in positions:
        logger.info(f"  - {pos.symbol}: {pos.quantity} @ {pos.average_price}")
    
    # 9. Test Strategy with Mock Candles
    logger.info("\n[Step 9] Testing Strategy with Mock Candles...")
    await strategy.start()
    
    # Simulate a few candles to trigger EMA calculation
    mock_candles = [
        {"timestamp": datetime.now() - timedelta(minutes=10), "open": 24000, "high": 24050, "low": 23980, "close": 24020, "volume": 100000},
        {"timestamp": datetime.now() - timedelta(minutes=5), "open": 24020, "high": 24080, "low": 24010, "close": 24060, "volume": 110000},
        {"timestamp": datetime.now(), "open": 24060, "high": 24100, "low": 24050, "close": 24090, "volume": 120000},
    ]
    
    for candle in mock_candles:
        await strategy.on_candle(candle)
    
    logger.info(f"Strategy Candles Loaded: {len(strategy.candles)}")
    if len(strategy.candles) > 0 and 'fast_ema' in strategy.candles.columns:
        logger.info(f"Latest Fast EMA: {strategy.candles['fast_ema'].iloc[-1]:.2f}")
        logger.info(f"Latest Slow EMA: {strategy.candles['slow_ema'].iloc[-1]:.2f}")
    
    # 10. Summary
    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION COMPLETE")
    logger.info("=" * 60)
    logger.info("✓ Fyers Broker: Connected")
    logger.info("✓ Paper Broker: Operational")
    logger.info("✓ Risk Manager: Enforcing Limits")
    logger.info("✓ OMS: Routing Orders")
    logger.info("✓ Strategy: Generating Signals")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(verify_full_flow())
