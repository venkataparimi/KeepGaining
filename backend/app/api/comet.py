"""
Comet AI API Routes
Provides endpoints for AI-powered market intelligence using Perplexity Pro
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from loguru import logger
from app.comet.mcp_client_perplexity import CometMCP

router = APIRouter(prefix="/api/comet", tags=["Comet AI"])

# Global client instance
comet_client: Optional[CometMCP] = None


def get_comet() -> CometMCP:
    """Get or create Comet client instance"""
    global comet_client
    if comet_client is None:
        try:
            comet_client = CometMCP()
            logger.info("Comet AI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Comet: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Comet initialization failed: {str(e)}"
            )
    return comet_client


# Request/Response Models
class QueryRequest(BaseModel):
    """Simple query request"""
    question: str = Field(..., description="The question to ask Comet")
    model: str = Field("pro", description="Model to use: pro, standard, or reasoning")
    conversation_id: Optional[str] = Field(None, description="ID for conversation context")


class AnalysisRequest(BaseModel):
    """Advanced analysis request"""
    query: str = Field(..., description="Main query")
    symbols: Optional[List[str]] = Field(None, description="Stock symbols of interest")
    focus: Optional[str] = Field(None, description="Focus area: trading_opportunities, risk_assessment, etc.")
    timeframe: Optional[str] = Field(None, description="Timeframe: immediate, short_term, medium_term")
    additional_context: Optional[str] = Field(None, description="Additional context")
    model: str = Field("pro", description="Model to use")
    conversation_id: Optional[str] = Field(None, description="Conversation ID")
    temperature: float = Field(0.7, ge=0.0, le=1.0, description="Response creativity (0-1)")
    max_tokens: int = Field(2000, ge=100, le=4000, description="Max response tokens")


class TemplateAnalysisRequest(BaseModel):
    """Template-based analysis request"""
    template_name: str = Field(..., description="Template name: signal_analysis, risk_assessment, etc.")
    template_vars: Dict[str, Any] = Field(..., description="Variables for template")
    model: str = Field("pro", description="Model to use")


class SignalValidationRequest(BaseModel):
    """Validate a trading signal with Comet"""
    symbol: str
    signal_type: str  # BULLISH, BEARISH, etc.
    entry_price: float
    current_price: float
    timeframe: str
    indicators: str
    market_context: str


class CometResponse(BaseModel):
    """Standard Comet response"""
    sentiment: float = Field(..., description="Sentiment score (0-1)")
    confidence: float = Field(..., description="Confidence level (0-1)")
    key_insights: List[str] = Field(..., description="Key insights")
    trading_signals: List[Dict[str, Any]] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    data_freshness: str = Field(..., description="Data freshness indicator")
    model: Optional[str] = Field(None, description="Model used")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage")


# Endpoints
@router.post("/query", response_model=CometResponse)
async def query_comet(request: QueryRequest):
    """
    Simple query endpoint for quick questions.
    
    Example:
        POST /api/comet/query
        {
            "question": "What's the sentiment on NIFTY today?",
            "model": "pro"
        }
    """
    try:
        comet = get_comet()
        result = await comet.analyze(
            {"query": request.question},
            conversation_id=request.conversation_id,
            model=request.model
        )
        return result
    except Exception as e:
        logger.error(f"Query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", response_model=CometResponse)
async def analyze_market(request: AnalysisRequest):
    """
    Advanced market analysis endpoint.
    
    Example:
        POST /api/comet/analyze
        {
            "query": "Analyze banking sector",
            "symbols": ["HDFCBANK", "ICICIBANK", "AXISBANK"],
            "focus": "trading_opportunities",
            "timeframe": "short_term"
        }
    """
    try:
        comet = get_comet()
        
        context = {
            "query": request.query,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens
        }
        
        if request.symbols:
            context["symbols"] = request.symbols
        if request.focus:
            context["focus"] = request.focus
        if request.timeframe:
            context["timeframe"] = request.timeframe
        if request.additional_context:
            context["additional_context"] = request.additional_context
        
        result = await comet.analyze(
            context,
            conversation_id=request.conversation_id,
            model=request.model
        )
        return result
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/template", response_model=CometResponse)
async def analyze_with_template(request: TemplateAnalysisRequest):
    """
    Template-based analysis endpoint.
    
    Example:
        POST /api/comet/template
        {
            "template_name": "signal_analysis",
            "template_vars": {
                "symbol": "NIFTY",
                "signal_type": "BULLISH",
                "entry_price": 22000,
                "current_price": 22050,
                "timeframe": "15m",
                "indicators": "RSI: 65",
                "market_context": "Uptrend"
            }
        }
    """
    try:
        comet = get_comet()
        result = await comet.analyze_with_template(
            request.template_name,
            request.template_vars,
            model=request.model
        )
        return result
    except Exception as e:
        logger.error(f"Template analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-signal", response_model=CometResponse)
async def validate_signal(request: SignalValidationRequest):
    """
    Validate a trading signal with real-time market intelligence.
    
    This is a convenience endpoint that uses the signal_analysis template.
    
    Example:
        POST /api/comet/validate-signal
        {
            "symbol": "RELIANCE",
            "signal_type": "BULLISH_BREAKOUT",
            "entry_price": 2500,
            "current_price": 2520,
            "timeframe": "1h",
            "indicators": "MACD bullish, RSI 65",
            "market_context": "Strong uptrend"
        }
    """
    try:
        comet = get_comet()
        result = await comet.analyze_with_template(
            "signal_analysis",
            {
                "symbol": request.symbol,
                "signal_type": request.signal_type,
                "entry_price": request.entry_price,
                "current_price": request.current_price,
                "timeframe": request.timeframe,
                "indicators": request.indicators,
                "market_context": request.market_context
            }
        )
        return result
    except Exception as e:
        logger.error(f"Signal validation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """
    Get conversation history.
    
    Example:
        GET /api/comet/conversation/my_session_123
    """
    try:
        comet = get_comet()
        history = comet.get_conversation_history(conversation_id)
        return {
            "conversation_id": conversation_id,
            "message_count": len(history),
            "history": history
        }
    except Exception as e:
        logger.error(f"Failed to get conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversation/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """
    Clear conversation history.
    
    Example:
        DELETE /api/comet/conversation/my_session_123
    """
    try:
        comet = get_comet()
        comet.clear_conversation(conversation_id)
        return {
            "message": f"Conversation {conversation_id} cleared",
            "conversation_id": conversation_id
        }
    except Exception as e:
        logger.error(f"Failed to clear conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """
    Check if Comet AI is available and healthy.
    
    Example:
        GET /api/comet/health
    """
    try:
        comet = get_comet()
        return {
            "status": "healthy",
            "service": "Comet AI",
            "provider": "Perplexity Pro",
            "available_models": list(comet.models.keys()),
            "default_model": comet.default_model
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/templates")
async def list_templates():
    """
    List available prompt templates.
    
    Example:
        GET /api/comet/templates
    """
    try:
        from app.comet.prompt_manager import PromptManager
        pm = PromptManager()
        templates = pm.list_templates()
        return {
            "templates": templates,
            "count": len(templates)
        }
    except Exception as e:
        logger.error(f"Failed to list templates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Background task for async analysis
async def run_analysis_background(
    analysis_id: str,
    context: Dict[str, Any],
    model: str
):
    """Run analysis in background and store results"""
    try:
        comet = get_comet()
        result = await comet.analyze(context, model=model)
        # TODO: Store result in Redis/database with analysis_id
        logger.info(f"Background analysis {analysis_id} completed")
    except Exception as e:
        logger.error(f"Background analysis {analysis_id} failed: {str(e)}")


@router.post("/analyze-async")
async def analyze_async(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks
):
    """
    Start an async analysis that runs in background.
    Returns immediately with an analysis_id to check later.
    
    Useful for long-running analysis that might take >30 seconds.
    
    Example:
        POST /api/comet/analyze-async
        {
            "query": "Deep analysis of all NIFTY 50 stocks",
            "model": "reasoning"
        }
        
        Returns: {"analysis_id": "abc123", "status": "processing"}
    """
    import uuid
    analysis_id = str(uuid.uuid4())
    
    context = {
        "query": request.query,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens
    }
    
    if request.symbols:
        context["symbols"] = request.symbols
    if request.focus:
        context["focus"] = request.focus
    if request.timeframe:
        context["timeframe"] = request.timeframe
    if request.additional_context:
        context["additional_context"] = request.additional_context
    
    background_tasks.add_task(
        run_analysis_background,
        analysis_id,
        context,
        request.model
    )
    
    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "message": "Analysis started in background"
    }
