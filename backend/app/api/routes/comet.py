from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.comet import comet_client
from loguru import logger

router = APIRouter()

class CometAnalysisRequest(BaseModel):
    type: str  # breakout_confirm, macro_analysis, sector_scan, stock_buzz
    symbol: Optional[str] = None
    event: Optional[str] = None
    price: Optional[float] = None
    sector: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None

class CometFollowUpRequest(BaseModel):
    question: str
    conversation_id: str

@router.post("/analyze")
async def analyze_event(request: CometAnalysisRequest):
    """
    Get AI-powered market intelligence analysis.
    
    Examples:
    - Breakout confirmation: {"type": "breakout_confirm", "symbol": "RELIANCE", "price": 2850}
    - Macro analysis: {"type": "macro_analysis", "event": "US Fed rate cut"}
    - Sector scan: {"type": "sector_scan", "sector": "IT"}
    """
    try:
        context = request.dict(exclude_none=True)
        analysis = await comet_client.analyze(context)
        return analysis
    except Exception as e:
        logger.error(f"Comet analysis failed: {e}")
        return {
            "sentiment": 0.5,
            "confidence": 0.0,
            "key_insights": [f"Analysis failed: {str(e)}"],
            "trading_signals": [],
            "risks": ["Service error"]
        }

@router.post("/followup")
async def followup_question(request: CometFollowUpRequest):
    """
    Ask follow-up question in an existing conversation.
    """
    try:
        response = await comet_client.follow_up(
            request.question,
            request.conversation_id
        )
        return response
    except Exception as e:
        logger.error(f"Comet follow-up failed: {e}")
        return {
            "sentiment": 0.5,
            "confidence": 0.0,
            "key_insights": [f"Follow-up failed: {str(e)}"],
            "trading_signals": [],
            "risks": ["Service error"]
        }

@router.get("/sector/{sector}/sentiment")
async def sector_sentiment(sector: str):
    """
    Get current sentiment for a specific sector.
    """
    try:
        analysis = await comet_client.analyze({
            "type": "sector_scan",
            "sector": sector
        })
        return analysis
    except Exception as e:
        logger.error(f"Sector sentiment failed: {e}")
        return {
            "sentiment": 0.5,
            "confidence": 0.0,
            "key_insights": [f"Analysis unavailable: {str(e)}"],
            "trading_signals": [],
            "risks": ["Service error"]
        }

@router.get("/stock/{symbol}/buzz")
async def stock_buzz(symbol: str):
    """
    Check why a stock is getting attention.
    """
    try:
        analysis = await comet_client.analyze({
            "type": "stock_buzz",
            "symbol": symbol
        })
        return analysis
    except Exception as e:
        logger.error(f"Stock buzz check failed: {e}")
        return {
            "sentiment": 0.5,
            "confidence": 0.0,
            "key_insights": [f"Analysis unavailable: {str(e)}"],
            "trading_signals": [],
            "risks": ["Service error"]
        }
