"""
Comet MCP Client - AI-powered market intelligence using OpenAI (fallback to Anthropic)
"""
import os
import json
from typing import Dict, Any, Optional
import openai
from loguru import logger
from anthropic import Anthropic

class CometMCP:
    """
    AI agent for market intelligence gathering using Claude via MCP.
    Provides dynamic, conversational analysis of news, sentiment, and market events.
    """
    
    def __init__(self):
        # Use Anthropic as primary client
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            self.client = Anthropic(api_key=anthropic_key)
            self.model = "claude-3-5-sonnet-20241022"
        else:
            logger.warning("No ANTHROPIC_API_KEY found - Comet will use fallback mode")
            self.client = None
        
        self.system_prompt = self._load_system_prompt()
        self.conversation_history = {}  # Store context for follow-ups

    def _load_system_prompt(self) -> str:
        """Load the core Comet persona and instructions"""
        return """You are Comet, an AI financial intelligence analyst for algorithmic trading.

EXPERTISE:
- Indian stock markets (NSE, BSE)
- Global macro events → Indian market impact
- Sector analysis and rotation trends
- Real-time sentiment from news and social media

YOUR MISSION:
Provide actionable intelligence to enhance trading decisions. Focus on:
1. Confirming technical breakouts with fundamental/news backing
2. Early detection of opportunities from macro events
3. Sector sentiment and rotation signals
4. Risk assessment and contradictory signals

OUTPUT RULES:
- Always return valid JSON
- Include sentiment score (0.0 to 1.0, where 0.5 is neutral)
- Provide confidence level (0.0 to 1.0)
- Give specific stock symbols when relevant
- Cite information sources
- Flag risks and contradictions

RESPONSE FORMAT:
{
  "sentiment": float,
  "confidence": float,
  "key_insights": [list of strings],
  "trading_signals": [{
    "symbol": str,
    "action": "BUY" | "SELL" | "WATCH" | "SKIP",
    "reasoning": str,
    "timeframe": "immediate" | "short_term" | "medium_term"
  }],
  "risks": [list of potential issues],
  "data_freshness": "real_time" | "recent" | "historical"
}

CRITICAL: Be specific. Avoid generic commentary. Focus on what traders can ACT on."""
    
    async def analyze(self, context: Dict[str, Any], conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a trading event or market situation.
        
        Args:
            context: Dictionary with analysis parameters
            conversation_id: Optional ID to maintain conversation context
        
        Returns:
            Analysis result as dictionary
        """
        if not self.client:
            return self._fallback_response(context)
        
        try:
            prompt = self._build_prompt(context)
            
            # Get or create conversation history
            if conversation_id:
                messages = self.conversation_history.get(conversation_id, [])
            else:
                messages = []
            
            # Append the new user message
            messages.append({"role": "user", "content": prompt})
            
            # Call Anthropic
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=self.system_prompt,
                messages=messages
            )
            assistant_message = response.content[0].text            
            # Store assistant reply if conversation tracking is enabled
            if conversation_id:
                messages.append({"role": "assistant", "content": assistant_message})
                self.conversation_history[conversation_id] = messages[-10:]
            
            return self._parse_response(assistant_message)
            
        except Exception as e:
            logger.error(f"Comet analysis failed: {e}")
            return self._fallback_response(context)
    
    def _build_prompt(self, context: Dict[str, Any]) -> str:
        """Build prompt based on context type"""
        analysis_type = context.get("type", "general")
        
        if analysis_type == "breakout_confirm":
            return f"""Stock: {context.get('symbol', 'UNKNOWN')}
Event: Breakout at {context.get('price', 0)} 
Time: Just now

TASK: Confirm if this breakout has fundamental/news backing.

Analyze:
1. Latest news (< 24 hours) about {context.get('symbol')} or its sector
2. Any recent corporate announcements, earnings, or events
3. Social media buzz or unusual volume
4. Is this news-driven or purely technical?

Provide recommendation: CONFIRM (strong backing), WAIT (mixed signals), or SKIP (negative sentiment)."""

        elif analysis_type == "macro_analysis":
            return f"""Global Event: {context.get('event', '')}

TASK: Chain analysis from global event to Indian stock opportunities.

Steps:
1. Immediate impact on Indian markets
2. Most affected sectors (rank by impact)
3. Top 3 stock opportunities per sector with reasoning
4. Timeline: When will impact materialize?

Be specific with stock symbols and actionable timeframes."""

        elif analysis_type == "sector_scan":
            return f"""Sector: {context.get('sector', '')}

TASK: Current sector intelligence gathering.

Provide:
1. Latest sector news and developments
2. Government policies or regulatory changes
3. Earnings season insights
4. Stocks showing unusual movement or opportunity

Focus on tradeable setups."""

        elif analysis_type == "stock_buzz":
            return f"""Stock: {context.get('symbol', '')}

TASK: Why is this stock getting attention?

Investigate:
1. Recent news and announcements
2. Social media sentiment
3. Insider trading or institutional activity
4. Technical setup alignment

Assess if buzz is justified or hype."""

        else:
            # General analysis
            return f"""Context: {json.dumps(context, indent=2)}

Provide market intelligence analysis based on this context."""
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse response into structured format"""
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                # Fallback: create structured response from text
                return {
                    "sentiment": 0.5,
                    "confidence": 0.5,
                    "key_insights": [response_text[:200]],
                    "trading_signals": [],
                    "risks": ["Unable to parse structured response"],
                    "raw_response": response_text
                }
        except json.JSONDecodeError:
            logger.warning("Failed to parse Comet response as JSON")
            return {
                "sentiment": 0.5,
                "confidence": 0.3,
                "key_insights": ["Analysis inconclusive"],
                "trading_signals": [],
                "risks": ["Response parsing failed"],
                "raw_response": response_text
            }
    
    def _fallback_response(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Return safe fallback when API is unavailable"""
        return {
            "sentiment": 0.5,
            "confidence": 0.0,
            "key_insights": ["Comet service unavailable - using technical signals only"],
            "trading_signals": [],
            "risks": ["No market intelligence available"],
            "data_freshness": "unavailable"
        }
    
    async def follow_up(self, question: str, conversation_id: str) -> Dict[str, Any]:
        """
        Ask follow-up question in an existing conversation.
        
        Args:
            question: The follow-up question
            conversation_id: ID of the conversation to continue
        
        Returns:
            Analysis response
        """
        return await self.analyze(
            {"type": "followup", "question": question},
            conversation_id=conversation_id
        )
    
    async def analyze_with_template(self, template_name: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze using a structured prompt template.
        
        This method uses the PromptManager to load and format templates from
        backend/prompts/templates/ directory, providing consistent, structured
        prompts for different analysis types.
        
        Args:
            template_name: Name of the template to use (e.g., "signal_analysis")
            **kwargs: Parameters to substitute in the template
        
        Returns:
            Analysis response as dictionary
        
        Example:
            analysis = await comet.analyze_with_template(
                "signal_analysis",
                symbol="NIFTY",
                signal_type="BULLISH",
                entry_price=22000,
                current_price=22050,
                timeframe="15m",
                indicators="RSI: 65, MACD: Bullish",
                market_context="Strong uptrend"
            )
        
        Available Templates:
            - signal_analysis: Analyze trading signals
            - risk_assessment: Assess position/portfolio risk
            - market_context: Get broader market analysis
            - trade_plan: Generate complete trade execution plans
        """
        try:
            from app.comet.prompt_manager import PromptManager
            
            pm = PromptManager()
            prompt = pm.format_prompt(template_name, **kwargs)
            
            if not prompt:
                logger.error(f"Failed to load template: {template_name}")
                return self._fallback_response({"template": template_name})
            
            # Use the formatted prompt with the existing query method
            return await self.query(prompt)
            
        except Exception as e:
            logger.error(f"Error analyzing with template {template_name}: {e}")
            return self._fallback_response({"template": template_name, "error": str(e)})
    
    async def query(self, prompt: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Simple query method for direct prompt usage.
        
        Args:
            prompt: The prompt text to send to Comet
            conversation_id: Optional ID to maintain conversation context
        
        Returns:
            Analysis response as dictionary
        
        Example:
            response = await comet.query("What's the market sentiment for NIFTY today?")
        """
        return await self.analyze(
            {"type": "general", "query": prompt},
            conversation_id=conversation_id
        )


# Global instance
comet_client = CometMCP()


class MCPClient:
    """
    Synchronous wrapper for CometMCP for easier use in notebooks and synchronous code.
    
    This class provides a simpler interface that doesn't require async/await syntax,
    making it easier to use in Jupyter notebooks and scripts.
    
    Usage:
        from app.comet.mcp_client import MCPClient
        
        comet = MCPClient()
        response = comet.query("Analyze NIFTY sentiment")
        analysis = comet.analyze_with_template("signal_analysis", symbol="NIFTY", ...)
    """
    
    def __init__(self):
        """Initialize synchronous MCP client"""
        self.async_client = CometMCP()
        logger.debug("MCPClient (synchronous wrapper) initialized")
    
    def query(self, prompt: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a query synchronously.
        
        Args:
            prompt: The prompt text
            conversation_id: Optional conversation ID
        
        Returns:
            Analysis response
        """
        import asyncio
        
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Run async method synchronously
            return loop.run_until_complete(
                self.async_client.query(prompt, conversation_id)
            )
        except Exception as e:
            logger.error(f"Error in synchronous query: {e}")
            return self.async_client._fallback_response({"error": str(e)})
    
    def analyze_with_template(self, template_name: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze using a template synchronously.
        
        Args:
            template_name: Template name (e.g., "signal_analysis")
            **kwargs: Template parameters
        
        Returns:
            Analysis response
        
        Example:
            comet = MCPClient()
            analysis = comet.analyze_with_template(
                "signal_analysis",
                symbol="NIFTY",
                signal_type="BULLISH",
                entry_price=22000,
                current_price=22050,
                timeframe="15m",
                indicators="RSI: 65",
                market_context="Uptrend"
            )
        """
        import asyncio
        
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(
                self.async_client.analyze_with_template(template_name, **kwargs)
            )
        except Exception as e:
            logger.error(f"Error in template analysis: {e}")
            return self.async_client._fallback_response({"template": template_name, "error": str(e)})
    
    def analyze(self, context: Dict[str, Any], conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a context synchronously.
        
        Args:
            context: Analysis context dictionary
            conversation_id: Optional conversation ID
        
        Returns:
            Analysis response
        """
        import asyncio
        
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(
                self.async_client.analyze(context, conversation_id)
            )
        except Exception as e:
            logger.error(f"Error in synchronous analyze: {e}")
            return self.async_client._fallback_response(context)
