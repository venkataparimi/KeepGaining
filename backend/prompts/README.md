# Comet AI Prompt Templates

This directory contains structured prompt templates for Comet AI (Perplexity) integration in the KeepGaining trading system.

## Available Templates

### 1. `signal_analysis.txt`
Analyzes trading signals and provides comprehensive assessment including:
- Signal strength rating
- Key support/resistance levels
- Risk factors
- Position sizing recommendations

**Usage:**
```python
from app.comet.prompt_manager import PromptManager

pm = PromptManager()
prompt = pm.format_prompt(
    "signal_analysis",
    symbol="NIFTY",
    signal_type="BULLISH",
    entry_price=22000,
    current_price=22050,
    timeframe="15m",
    indicators="RSI: 65, MACD: Bullish Crossover",
    market_context="Strong uptrend, above all EMAs"
)
```

### 2. `risk_assessment.txt`
Evaluates risk for existing positions and portfolio:
- Current risk level assessment
- Risk factor identification
- Mitigation recommendations
- Warning signals

**Usage:**
```python
prompt = pm.format_prompt(
    "risk_assessment",
    symbol="BANKNIFTY",
    position_type="LONG",
    entry_price=45000,
    current_price=45200,
    position_size=50,
    unrealized_pnl=10000,
    total_capital=1000000,
    position_percentage=22.5,
    current_drawdown=5,
    open_positions_count=3,
    market_conditions="High volatility",
    technical_indicators="RSI: 72 (Overbought)"
)
```

### 3. `market_context.txt`
Provides broader market analysis:
- Overall market sentiment
- Symbol-specific context
- Timing considerations
- Correlation analysis

**Usage:**
```python
prompt = pm.format_prompt(
    "market_context",
    symbol="RELIANCE",
    current_price=2450,
    day_high=2475,
    day_low=2440,
    volume=5000000,
    avg_volume=3500000,
    atr=25,
    index_performance="NIFTY: +0.8%, SENSEX: +0.6%",
    recent_events="Quarterly results announced",
    technical_context="Consolidating near ATH",
    current_time="10:30 AM IST",
    market_session="Pre-noon",
    day_of_week="Wednesday"
)
```

### 4. `trade_plan.txt`
Generates complete trade execution plans:
- Entry/exit strategy
- Position sizing
- Stop loss and targets
- Risk management rules

**Usage:**
```python
prompt = pm.format_prompt(
    "trade_plan",
    symbol="TCS",
    strategy_name="Volume Rocket",
    signal_time="2025-12-06 09:45:00",
    signal_type="BULLISH_BREAKOUT",
    entry_price=3500,
    current_price=3505,
    entry_confidence=8,
    technical_setup="Volume spike + breakout above resistance",
    max_risk_percent=2,
    account_size=1000000,
    max_position_size=50000,
    market_conditions="Strong market, low volatility"
)
```

## Template Guidelines

### Parameter Naming Convention
- Use `snake_case` for parameter names
- Be descriptive: `entry_price` not `ep`
- Include units/context where relevant

### Template Structure
Each template should follow this structure:
1. **Context Section** - What data is being analyzed
2. **Request Section** - What analysis is needed
3. **Output Format** - Structured format for response

### Adding New Templates

1. Create a new `.txt` file in `prompts/templates/`
2. Use `{parameter_name}` syntax for placeholders
3. Structure the prompt for clear, actionable responses
4. Document parameters and usage in this README

## Best Practices

1. **Be Specific** - Provide clear context and expected output format
2. **Use Structured Output** - Request numbered lists, sections, ratings
3. **Include Examples** - When relevant, show desired output format
4. **Version Control** - Track prompt changes as they affect AI behavior
5. **Test Thoroughly** - Validate prompts with various input scenarios

## Integration with Comet AI

These templates are loaded via `PromptManager` and used with the existing `MCPClient`:

```python
from app.comet.mcp_client import MCPClient

comet = MCPClient()

# Using templates
analysis = comet.analyze_with_template(
    "signal_analysis",
    symbol="NIFTY",
    signal_type="BULLISH",
    # ... other parameters
)
```

## Prompt Versioning

When modifying templates:
1. Test changes with sample data first
2. Document significant changes in git commit messages
3. Monitor AI response quality after changes
4. Revert if response quality degrades

## Performance Optimization

- **Caching**: Similar prompts can be cached (see `comet_config.yaml`)
- **Token Management**: Keep prompts concise but complete
- **Rate Limiting**: Respect Perplexity API limits
- **Batch Processing**: Process multiple signals together when possible

## Future Templates

Potential templates to add:
- `portfolio_rebalancing.txt` - Portfolio optimization recommendations
- `strategy_evaluation.txt` - Backtest result analysis
- `pattern_recognition.txt` - Chart pattern identification
- `sentiment_analysis.txt` - News/social sentiment analysis
- `correlation_analysis.txt` - Inter-symbol correlation insights
