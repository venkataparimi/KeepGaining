"""
Comet MCP Client - AI-powered market intelligence using Perplexity (OpenAI-compatible)
"""
import os
import json
import re
from typing import Dict, Any, Optional, List
from openai import OpenAI, AsyncOpenAI
from loguru import logger


class CometMCP:
    """
    AI agent for market intelligence using Perplexity's sonar-pro model.
    Provides real-time market analysis with web search capabilities.
    """
    
    def __init__(self):
        """Initialize Perplexity client"""
        perplexity_key = os.getenv("PERPLEXITY_API_KEY")
        
        if not perplexity_key:
            raise ValueError(
                "PERPLEXITY_API_KEY not found in environment. "
                "Get your API key from https://www.perplexity.ai/settings/api"
            )
        
        # Use async client for better performance
        self.client = AsyncOpenAI(
            api_key=perplexity_key,
            base_url="https://api.perplexity.ai"
        )
        
        # Model selection based on use case
        self.models = {
            "pro": "sonar-pro",              # Best for real-time market data
            "standard": "sonar",             # General queries
            "reasoning": "sonar-reasoning"   # Complex analysis
        }
        
        self.default_model = self.models["pro"]
        self.system_prompt = self._load_system_prompt()
        self.conversation_history = {}  # Store context for follow-ups

    def _load_system_prompt(self) -> str:
        """Load the core Comet persona and instructions"""
        return """You are Comet, an AI financial intelligence analyst for algorithmic trading.

EXPERTISE:
- Indian stock markets (NSE, BSE)
- Real-time market news and sentiment analysis
- Global macro events → Indian market impact
- Sector analysis and rotation trends
- Technical + Fundamental confluence

YOUR MISSION:
Provide actionable intelligence to enhance trading decisions. Focus on:
1. Real-time news and sentiment affecting stocks/indices
2. Confirming technical signals with fundamental/news backing
3. Early detection of opportunities from macro events
4. Sector momentum and rotation signals
5. Risk assessment and contradictory signals

OUTPUT RULES:
- Always return valid JSON
- Include sentiment score (0.0 to 1.0, where 0.5 is neutral)
- Provide confidence level (0.0 to 1.0)
- Give specific stock symbols when relevant
- Cite information sources (you have web access)
- Flag risks and contradictions
- Be specific and actionable

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
  "citations": [list of source URLs],
  "data_freshness": "real_time" | "recent" | "historical"
}

CRITICAL: 
- Use your web search capabilities to get CURRENT information
- Be specific. Avoid generic commentary
- Focus on what traders can ACT on
- Cite sources for credibility"""

    async def analyze(
        self,
        context: Dict[str, Any],
        conversation_id: Optional[str] = None,
        model: str = "pro"
    ) -> Dict[str, Any]:
        """
        Analyze a trading event or market situation using Perplexity.
        
        Args:
            context: Dictionary with analysis parameters (must have 'query' key)
            conversation_id: Optional ID to maintain conversation context
            model: Model to use - "pro", "standard", or "reasoning"
        
        Returns:
            Dictionary with analysis results including sentiment, signals, and citations
        
        Example:
            result = await comet.analyze({
                "query": "What's the sentiment on NIFTY banking stocks today?",
                "focus": "trading_opportunities"
            })
        """
        if not context.get("query"):
            raise ValueError("Context must include 'query' field")
        
        try:
            # Build messages
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            # Add conversation history if exists
            if conversation_id and conversation_id in self.conversation_history:
                messages.extend(self.conversation_history[conversation_id])
            
            # Add current query
            user_message = self._format_query(context)
            messages.append({"role": "user", "content": user_message})
            
            # Select model
            selected_model = self.models.get(model, self.default_model)
            
            logger.info(f"Querying Perplexity ({selected_model}): {context.get('query', '')[:100]}...")
            
            # Make API call
            response = await self.client.chat.completions.create(
                model=selected_model,
                messages=messages,
                temperature=context.get("temperature", 0.7),
                max_tokens=context.get("max_tokens", 2000),
            )
            
            # Extract response
            content = response.choices[0].message.content
            
            # Try to parse as JSON, fall back to structured format
            try:
                # Try direct parse first
                result = json.loads(content)
            except json.JSONDecodeError as e:
                # Log the error and response for debugging
                logger.debug(f"JSON parse error at position {e.pos}: {e.msg}")
                logger.debug(f"Content around error (chars {max(0,e.pos-50)}:{e.pos+50}): ...{content[max(0,e.pos-50):e.pos+50]}...")
                
                # Try to extract just the JSON object
                # Find first { and last }
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1 and end > start:
                    json_str = content[start:end+1]
                    try:
                        result = json.loads(json_str)
                        logger.debug("Successfully extracted and parsed JSON")
                    except json.JSONDecodeError:
                        logger.warning("Could not parse extracted JSON, using fallback")
                        result = self._structure_response(content)
                else:
                    logger.warning("No JSON object found in response, using fallback")
                    result = self._structure_response(content)
            
            # Add metadata
            result["model"] = selected_model
            result["usage"] = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
            # Store conversation history
            if conversation_id:
                if conversation_id not in self.conversation_history:
                    self.conversation_history[conversation_id] = []
                
                self.conversation_history[conversation_id].append(
                    {"role": "user", "content": user_message}
                )
                self.conversation_history[conversation_id].append(
                    {"role": "assistant", "content": content}
                )
                
                # Limit history to last 10 messages
                if len(self.conversation_history[conversation_id]) > 10:
                    self.conversation_history[conversation_id] = \
                        self.conversation_history[conversation_id][-10:]
            
            logger.info(f"Perplexity analysis complete. Sentiment: {result.get('sentiment', 'N/A')}, "
                       f"Confidence: {result.get('confidence', 'N/A')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Comet analysis failed: {str(e)}")
            return self._error_response(str(e))

    def _format_query(self, context: Dict[str, Any]) -> str:
        """Format context into a clear query"""
        query = context["query"]
        
        # Add additional context if provided
        if context.get("focus"):
            query += f"\n\nFocus area: {context['focus']}"
        
        if context.get("symbols"):
            query += f"\n\nSymbols of interest: {', '.join(context['symbols'])}"
        
        if context.get("timeframe"):
            query += f"\n\nTimeframe: {context['timeframe']}"
        
        if context.get("additional_context"):
            query += f"\n\nAdditional context: {context['additional_context']}"
        
        return query

    def _structure_response(self, content: str) -> Dict[str, Any]:
        """Structure non-JSON response into expected format"""
        return {
            "sentiment": 0.5,  # Neutral default
            "confidence": 0.5,
            "key_insights": [content],
            "trading_signals": [],
            "risks": [],
            "citations": [],
            "data_freshness": "unknown",
            "raw_response": content
        }

    def _error_response(self, error_msg: str) -> Dict[str, Any]:
        """Return error response in expected format"""
        return {
            "sentiment": 0.5,
            "confidence": 0.0,
            "key_insights": [],
            "trading_signals": [],
            "risks": [f"Error: {error_msg}"],
            "citations": [],
            "data_freshness": "error",
            "error": error_msg
        }

    async def query(self, question: str, model: str = "pro") -> Dict[str, Any]:
        """
        Simple query method for quick questions.
        
        Args:
            question: The question to ask
            model: Model to use - "pro", "standard", or "reasoning"
        
        Returns:
            Analysis results
        
        Example:
            result = await comet.query("What's happening with RELIANCE today?")
        """
        return await self.analyze({"query": question}, model=model)

    async def analyze_with_template(
        self,
        template_name: str,
        template_vars: Dict[str, Any],
        model: str = "pro"
    ) -> Dict[str, Any]:
        """
        Analyze using a prompt template.
        
        Args:
            template_name: Name of template to use
            template_vars: Variables to fill in template
            model: Model to use
        
        Returns:
            Analysis results
        
        Example:
            result = await comet.analyze_with_template(
                "signal_analysis",
                {
                    "symbol": "NIFTY",
                    "signal_type": "BULLISH",
                    "entry_price": 22000,
                    "current_price": 22050,
                    "timeframe": "15m",
                    "indicators": "RSI: 65, MACD: Bullish",
                    "market_context": "Strong uptrend"
                }
            )
        """
        from app.comet.prompt_manager import PromptManager
        
        pm = PromptManager()
        prompt = pm.format_prompt(template_name, **template_vars)
        
        return await self.analyze({"query": prompt}, model=model)

    def clear_conversation(self, conversation_id: str):
        """Clear conversation history for a specific ID"""
        if conversation_id in self.conversation_history:
            del self.conversation_history[conversation_id]

    def get_conversation_history(self, conversation_id: str) -> List[Dict]:
        """Get conversation history for a specific ID"""
        return self.conversation_history.get(conversation_id, [])


class MCPClient:
    """
    Synchronous wrapper for CometMCP for use in notebooks and scripts.
    
    Example:
        from app.comet.mcp_client import MCPClient
        
        comet = MCPClient()
        result = comet.analyze({"query": "Market sentiment today?"})
        print(result['key_insights'])
    """
    
    def __init__(self):
        """Initialize synchronous client"""
        import asyncio
        self.comet = CometMCP()
        
        # Get or create event loop
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    def analyze(
        self,
        context: Dict[str, Any],
        conversation_id: Optional[str] = None,
        model: str = "pro"
    ) -> Dict[str, Any]:
        """Synchronous analyze method"""
        return self.loop.run_until_complete(
            self.comet.analyze(context, conversation_id, model)
        )

    def query(self, question: str, model: str = "pro") -> Dict[str, Any]:
        """Synchronous query method"""
        return self.loop.run_until_complete(
            self.comet.query(question, model)
        )

    def analyze_with_template(
        self,
        template_name: str,
        template_vars: Dict[str, Any],
        model: str = "pro"
    ) -> Dict[str, Any]:
        """Synchronous template analysis"""
        return self.loop.run_until_complete(
            self.comet.analyze_with_template(template_name, template_vars, model)
        )
