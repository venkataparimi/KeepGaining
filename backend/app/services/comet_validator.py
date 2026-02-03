"""
Comet AI Signal Validator

Validates trading signals using Perplexity Pro AI before execution.
Provides real-time market intelligence to confirm or reject signals.
"""
import asyncio
from typing import Dict, Any, Optional
from decimal import Decimal
from loguru import logger

from app.comet.mcp_client_perplexity import CometMCP
from app.services.strategy_engine import Signal, SignalType, SignalStrength


class SignalValidationResult:
    """Result of signal validation"""
    
    def __init__(
        self,
        signal: Signal,
        approved: bool,
        ai_sentiment: float,
        ai_confidence: float,
        key_insights: list[str],
        risks: list[str],
        combined_score: float,
        reason: str
    ):
        self.signal = signal
        self.approved = approved
        self.ai_sentiment = ai_sentiment
        self.ai_confidence = ai_confidence
        self.key_insights = key_insights
        self.risks = risks
        self.combined_score = combined_score
        self.reason = reason
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "signal_id": self.signal.signal_id,
            "symbol": self.signal.symbol,
            "approved": self.approved,
            "ai_sentiment": self.ai_sentiment,
            "ai_confidence": self.ai_confidence,
            "combined_score": self.combined_score,
            "reason": self.reason,
            "key_insights": self.key_insights[:3],  # Top 3
            "risks": self.risks[:3]  # Top 3
        }


class CometSignalValidator:
    """
    Validates trading signals using Comet AI.
    
    Integration point between strategy engine and execution.
    Adds AI-powered validation layer to filter signals.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        min_sentiment: float = 0.55,
        min_confidence: float = 0.65,
        min_combined_score: float = 0.65,
        technical_weight: float = 0.5,
        ai_weight: float = 0.5
    ):
        """
        Initialize validator.
        
        Args:
            enabled: Whether AI validation is active
            min_sentiment: Minimum AI sentiment (0-1)
            min_confidence: Minimum AI confidence (0-1)
            min_combined_score: Minimum combined score (0-1)
            technical_weight: Weight for technical score
            ai_weight: Weight for AI score
        """
        self.enabled = enabled
        self.min_sentiment = min_sentiment
        self.min_confidence = min_confidence
        self.min_combined_score = min_combined_score
        self.technical_weight = technical_weight
        self.ai_weight = ai_weight
        
        # Initialize Comet client
        try:
            self.comet = CometMCP() if enabled else None
            logger.info("Comet Signal Validator initialized")
        except Exception as e:
            logger.warning(f"Comet initialization failed: {e}. Running without AI validation.")
            self.enabled = False
            self.comet = None
    
    async def validate_signal(self, signal: Signal) -> SignalValidationResult:
        """
        Validate a trading signal with AI intelligence.
        
        Args:
            signal: Signal to validate
            
        Returns:
            SignalValidationResult with approval decision
        """
        # If disabled, auto-approve
        if not self.enabled or not self.comet:
            return SignalValidationResult(
                signal=signal,
                approved=True,
                ai_sentiment=0.5,
                ai_confidence=0.0,
                key_insights=["AI validation disabled"],
                risks=[],
                combined_score=self._get_technical_score(signal),
                reason="AI validation disabled - using technical only"
            )
        
        try:
            # Get AI analysis using template
            ai_result = await self.comet.analyze_with_template(
                "signal_analysis",
                {
                    "symbol": signal.symbol,
                    "signal_type": self._format_signal_type(signal.signal_type),
                    "entry_price": float(signal.entry_price),
                    "current_price": float(signal.entry_price),  # Same at signal time
                    "timeframe": signal.timeframe,
                    "option_details": self._format_option_details(signal.metadata),
                    "indicators": self._format_indicators(signal.indicators),
                    "market_context": signal.reason
                }
            )
            
            # Extract AI scores
            ai_sentiment = ai_result.get("sentiment", 0.5)
            ai_confidence = ai_result.get("confidence", 0.5)
            key_insights = ai_result.get("key_insights", [])
            risks = ai_result.get("risks", [])
            
            # Calculate technical score from signal strength
            technical_score = self._get_technical_score(signal)
            
            # Combined score
            combined_score = (
                (technical_score * self.technical_weight) +
                (ai_sentiment * self.ai_weight * 0.7) +
                (ai_confidence * self.ai_weight * 0.3)
            )
            
            # Decision logic
            approved, reason = self._make_decision(
                ai_sentiment,
                ai_confidence,
                combined_score,
                risks
            )
            
            logger.info(
                f"Signal validation: {signal.symbol} - "
                f"Technical: {technical_score:.2f}, AI Sentiment: {ai_sentiment:.2f}, "
                f"AI Confidence: {ai_confidence:.2f}, Combined: {combined_score:.2f} - "
                f"{'APPROVED' if approved else 'REJECTED'}"
            )
            
            return SignalValidationResult(
                signal=signal,
                approved=approved,
                ai_sentiment=ai_sentiment,
                ai_confidence=ai_confidence,
                key_insights=key_insights,
                risks=risks,
                combined_score=combined_score,
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"AI validation failed for {signal.symbol}: {e}")
            # On error, fall back to technical only
            technical_score = self._get_technical_score(signal)
            return SignalValidationResult(
                signal=signal,
                approved=technical_score > 0.6,
                ai_sentiment=0.5,
                ai_confidence=0.0,
                key_insights=[],
                risks=[f"AI validation error: {str(e)}"],
                combined_score=technical_score,
                reason=f"AI validation failed - using technical only (score: {technical_score:.2f})"
            )
    
    def _get_technical_score(self, signal: Signal) -> float:
        """Convert signal strength to score"""
        strength_scores = {
            SignalStrength.STRONG: 0.85,
            SignalStrength.MODERATE: 0.65,
            SignalStrength.WEAK: 0.45
        }
        return strength_scores.get(signal.strength, 0.65)
    
    def _format_signal_type(self, signal_type: SignalType) -> str:
        """Format signal type for AI"""
        type_map = {
            SignalType.LONG_ENTRY: "BULLISH_ENTRY",
            SignalType.SHORT_ENTRY: "BEARISH_ENTRY",
            SignalType.LONG_EXIT: "BULLISH_EXIT",
            SignalType.SHORT_EXIT: "BEARISH_EXIT"
        }
        return type_map.get(signal_type, str(signal_type))
    
    def _format_option_details(self, metadata: Dict[str, Any]) -> str:
        """Format option details if present"""
        if not metadata or "option_type" not in metadata:
            return "Asset Type: Equity/Spot"
            
        details = [
            f"- Asset Type: OPTION ({metadata.get('option_type')})",
            f"- Strike Price: {metadata.get('strike_price')}",
            f"- Expiry: {metadata.get('expiry_date')}",
            f"- Underlying Price: {metadata.get('underlying_price', 'N/A')}"
        ]
        return "\n".join(details)

    def _format_indicators(self, indicators: Dict[str, Any]) -> str:
        """Format indicators dict to readable string"""
        parts = []
        for key, value in indicators.items():
            if isinstance(value, (int, float, Decimal)):
                parts.append(f"{key}: {float(value):.2f}")
            else:
                parts.append(f"{key}: {value}")
        return ", ".join(parts[:8])  # Limit to 8 indicators
    
    def _make_decision(
        self,
        sentiment: float,
        confidence: float,
        combined_score: float,
        risks: list[str]
    ) -> tuple[bool, str]:
        """
        Make approval decision based on scores.
        
        Returns:
            (approved, reason) tuple
        """
        # Check for major risks
        major_risks = [r for r in risks if any(
            keyword in r.lower() 
            for keyword in ["major", "high", "critical", "severe", "warning"]
        )]
        
        if major_risks:
            return False, f"Major risks detected: {major_risks[0][:100]}"
        
        # Check minimum thresholds
        if sentiment < self.min_sentiment:
            return False, f"AI sentiment too low: {sentiment:.2f} < {self.min_sentiment}"
        
        if confidence < self.min_confidence:
            return False, f"AI confidence too low: {confidence:.2f} < {self.min_confidence}"
        
        if combined_score < self.min_combined_score:
            return False, f"Combined score too low: {combined_score:.2f} < {self.min_combined_score}"
        
        # Approved
        return True, f"Signal validated (score: {combined_score:.2f})"
    
    def update_config(
        self,
        min_sentiment: Optional[float] = None,
        min_confidence: Optional[float] = None,
        min_combined_score: Optional[float] = None,
        technical_weight: Optional[float] = None,
        ai_weight: Optional[float] = None
    ):
        """Update validator configuration"""
        if min_sentiment is not None:
            self.min_sentiment = min_sentiment
        if min_confidence is not None:
            self.min_confidence = min_confidence
        if min_combined_score is not None:
            self.min_combined_score = min_combined_score
        if technical_weight is not None:
            self.technical_weight = technical_weight
        if ai_weight is not None:
            self.ai_weight = ai_weight
        
        logger.info(
            f"Validator config updated: sentiment={self.min_sentiment}, "
            f"confidence={self.min_confidence}, combined={self.min_combined_score}"
        )


# Global validator instance
_validator: Optional[CometSignalValidator] = None


def get_signal_validator() -> CometSignalValidator:
    """Get or create global validator instance"""
    global _validator
    if _validator is None:
        _validator = CometSignalValidator(enabled=True)
    return _validator


def create_signal_validator(
    enabled: bool = True,
    **kwargs
) -> CometSignalValidator:
    """Create new validator instance with custom config"""
    return CometSignalValidator(enabled=enabled, **kwargs)
