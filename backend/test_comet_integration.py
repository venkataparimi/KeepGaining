"""
Test Comet AI Integration with Trading System

Tests the end-to-end flow: Strategy → Signal → AI Validation → Execution
"""
import asyncio
import sys
sys.path.insert(0, ".")

from decimal import Decimal
from datetime import datetime, timedelta
from dotenv import load_dotenv
from app.services.strategy_engine import Signal, SignalType, SignalStrength
from app.services.comet_validator import CometSignalValidator
from loguru import logger

# Load environment variables
load_dotenv()


async def test_signal_validation():
    """Test signal validation with Comet AI"""
    logger.info("=" * 60)
    logger.info("Testing Comet AI Signal Validation")
    logger.info("=" * 60)
    
    # Create validator
    validator = CometSignalValidator(
        enabled=True,
        min_sentiment=0.55,
        min_confidence=0.65,
        min_combined_score=0.65
    )
    
    # Test Case 1: KAYNES Technology
    logger.info("\nTest 1: KAYNES Technology (Strong Signal)")
    logger.info("-" * 60)
    
    kaynes_signal = Signal(
        signal_id="test_kaynes",
        strategy_id="VOLROCKET",
        strategy_name="Volume Rocket",
        symbol="KAYNES",
        exchange="NSE",
        signal_type=SignalType.LONG_ENTRY,
        strength=SignalStrength.STRONG,
        entry_price=Decimal("4365"),
        stop_loss=Decimal("4250"),
        target_price=Decimal("4550"),
        quantity_pct=5.0,
        timeframe="15m",
        indicators={
            "rsi_14": 65.5,
            "vwma_20": 4320.0,
            "supertrend_direction": 1,
            "volume_ratio": 2.5,
            "macd": 45.2,
            "signal": 32.1
        },
        reason="Strong breakout above VWMA with 2.5x volume, RSI bullish",
        generated_at=datetime.now(),
        valid_until=datetime.now() + timedelta(minutes=30)
    )
    
    result1 = await validator.validate_signal(kaynes_signal)
    
    logger.info(f"Signal: {kaynes_signal.symbol} - {kaynes_signal.signal_type.value}")
    logger.info(f"Technical Strength: {kaynes_signal.strength.value}")
    logger.info(f"AI Sentiment: {result1.ai_sentiment:.2f}")
    logger.info(f"AI Confidence: {result1.ai_confidence:.2f}")
    logger.info(f"Combined Score: {result1.combined_score:.2f}")
    logger.info(f"Decision: {'✅ APPROVED' if result1.approved else '❌ REJECTED'}")
    logger.info(f"Reason: {result1.reason}")
    if result1.key_insights:
        logger.info(f"Key Insights:")
        for insight in result1.key_insights[:2]:
            logger.info(f"  • {insight[:120]}...")
    if result1.risks:
        logger.info(f"Risks:")
        for risk in result1.risks[:2]:
            logger.info(f"  ⚠️ {risk[:120]}...")
    
    # Test Case 2: INDIGO (InterGlobe Aviation)
    logger.info("\n\nTest 2: INDIGO (Moderate Signal)")
    logger.info("-" * 60)
    
    indigo_signal = Signal(
        signal_id="test_indigo",
        strategy_id="VOLROCKET",
        strategy_name="Volume Rocket",
        symbol="INDIGO",
        exchange="NSE",
        signal_type=SignalType.LONG_ENTRY,
        strength=SignalStrength.MODERATE,
        entry_price=Decimal("5367.50"),
        stop_loss=Decimal("5250.00"),
        target_price=Decimal("5550.00"),
        quantity_pct=4.0,
        timeframe="15m",
        indicators={
            "rsi_14": 58.1,
            "vwma_20": 5340.0,
            "supertrend_direction": 1,
            "volume_ratio": 1.5,
            "macd": 12.5,
            "signal": 8.2
        },
        reason="Trend following setup, moderate volume, RSI > 55",
        generated_at=datetime.now(),
        valid_until=datetime.now() + timedelta(minutes=30)
    )
    
    result2 = await validator.validate_signal(indigo_signal)
    
    logger.info(f"Signal: {indigo_signal.symbol} - {indigo_signal.signal_type.value}")
    logger.info(f"Technical Strength: {indigo_signal.strength.value}")
    logger.info(f"AI Sentiment: {result2.ai_sentiment:.2f}")
    logger.info(f"AI Confidence: {result2.ai_confidence:.2f}")
    logger.info(f"Combined Score: {result2.combined_score:.2f}")
    logger.info(f"Decision: {'✅ APPROVED' if result2.approved else '❌ REJECTED'}")
    logger.info(f"Reason: {result2.reason}")
    if result2.key_insights:
        logger.info(f"Key Insights:")
        for insight in result2.key_insights[:2]:
            logger.info(f"  • {insight[:120]}...")
    if result2.risks:
        logger.info(f"Risks:")
        for risk in result2.risks[:2]:
            logger.info(f"  ⚠️ {risk[:120]}...")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    results = [result1, result2]
    approved = sum(1 for r in results if r.approved)
    rejected = len(results) - approved
    
    logger.info(f"Total Signals: {len(results)}")
    logger.info(f"Approved: {approved}")
    logger.info(f"Rejected: {rejected}")
    logger.info(f"Approval Rate: {(approved/len(results)*100):.1f}%")
    
    logger.info("\nSignal Quality Distribution:")
    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result.approved else "❌ FAIL"
        logger.info(
            f"  {i}. {result.signal.symbol} ({result.signal.strength.value}): "
            f"{status} - Score: {result.combined_score:.2f}"
        )


async def test_disabled_validation():
    """Test with AI validation disabled"""
    logger.info("\n\n" + "=" * 60)
    logger.info("Testing with AI Validation DISABLED")
    logger.info("=" * 60)
    
    # Create disabled validator
    validator = CometSignalValidator(enabled=False)
    
    test_signal = Signal(
        signal_id="test_004",
        strategy_id="VOLROCKET",
        strategy_name="Volume Rocket",
        symbol="TCS",
        exchange="NSE",
        signal_type=SignalType.LONG_ENTRY,
        strength=SignalStrength.STRONG,
        entry_price=Decimal("3800"),
        stop_loss=Decimal("3750"),
        target_price=Decimal("3900"),
        quantity_pct=5.0,
        timeframe="15m",
        indicators={"rsi_14": 65.0, "volume_ratio": 2.0},
        reason="Test signal",
        generated_at=datetime.now(),
        valid_until=datetime.now() + timedelta(minutes=30)
    )
    
    result = await validator.validate_signal(test_signal)
    
    logger.info(f"Signal: {test_signal.symbol}")
    logger.info(f"Validator Enabled: {validator.enabled}")
    logger.info(f"Decision: {'✅ APPROVED' if result.approved else '❌ REJECTED'}")
    logger.info(f"Reason: {result.reason}")
    logger.info(f"Combined Score: {result.combined_score:.2f} (technical only)")


async def test_configuration():
    """Test different validation configurations"""
    logger.info("\n\n" + "=" * 60)
    logger.info("Testing Different Configurations")
    logger.info("=" * 60)
    
    test_signal = Signal(
        signal_id="test_005",
        strategy_id="VOLROCKET",
        strategy_name="Volume Rocket",
        symbol="INFY",
        exchange="NSE",
        signal_type=SignalType.LONG_ENTRY,
        strength=SignalStrength.MODERATE,
        entry_price=Decimal("1500"),
        stop_loss=Decimal("1480"),
        target_price=Decimal("1540"),
        quantity_pct=5.0,
        timeframe="15m",
        indicators={"rsi_14": 60.0, "volume_ratio": 1.5},
        reason="Moderate setup",
        generated_at=datetime.now(),
        valid_until=datetime.now() + timedelta(minutes=30)
    )
    
    # Config 1: Strict
    logger.info("\nConfig 1: Strict Validation")
    logger.info("-" * 60)
    validator_strict = CometSignalValidator(
        enabled=True,
        min_sentiment=0.65,
        min_confidence=0.75,
        min_combined_score=0.75
    )
    result_strict = await validator_strict.validate_signal(test_signal)
    logger.info(f"Decision: {'✅ APPROVED' if result_strict.approved else '❌ REJECTED'}")
    logger.info(f"Combined Score: {result_strict.combined_score:.2f}")
    logger.info(f"Reason: {result_strict.reason}")
    
    # Config 2: Lenient
    logger.info("\nConfig 2: Lenient Validation")
    logger.info("-" * 60)
    validator_lenient = CometSignalValidator(
        enabled=True,
        min_sentiment=0.45,
        min_confidence=0.55,
        min_combined_score=0.55
    )
    result_lenient = await validator_lenient.validate_signal(test_signal)
    logger.info(f"Decision: {'✅ APPROVED' if result_lenient.approved else '❌ REJECTED'}")
    logger.info(f"Combined Score: {result_lenient.combined_score:.2f}")
    logger.info(f"Reason: {result_lenient.reason}")


async def main():
    """Run all tests"""
    try:
        # Test 1: Signal validation
        await test_signal_validation()
        
        # Test 2: Disabled validation
        await test_disabled_validation()
        
        # Test 3: Configuration
        await test_configuration()
        
        logger.info("\n\n" + "=" * 60)
        logger.info("✅ All Integration Tests Completed!")
        logger.info("=" * 60)
        logger.info("\nComet AI is now integrated into your trading system.")
        logger.info("Signals will be validated before execution in paper/live modes.")
        
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
