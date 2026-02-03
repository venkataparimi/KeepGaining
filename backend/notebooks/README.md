# KeepGaining Analysis Notebooks

This directory contains Jupyter notebooks for strategy analysis, signal validation, and performance optimization using Comet AI.

## Available Notebooks

### 1. `01_strategy_backtest_analysis.ipynb`
**Purpose:** Analyze historical backtest results and identify winning/losing patterns

**Features:**
- Load backtest CSV files
- Calculate performance metrics (win rate, profit factor, etc.)
- Visualize P&L distribution and cumulative returns
- Use Comet AI to analyze best/worst trades
- Generate strategy optimization recommendations

**Use Cases:**
- Post-backtest analysis
- Strategy refinement
- Understanding trade patterns
- Performance reporting

**How to Run:**
```bash
cd backend/notebooks
jupyter notebook 01_strategy_backtest_analysis.ipynb
```

---

### 2. `02_comet_signal_validation.ipynb`
**Purpose:** Validate trading signals using Comet AI before execution

**Features:**
- Load signals from strategy generation
- Use Comet AI prompt templates for validation
- Risk assessment for each signal
- Generate complete trade plans
- Build confidence scoring system
- Decision framework for trade execution

**Use Cases:**
- Pre-trade signal validation
- Risk assessment
- Position sizing recommendations
- Trade plan generation
- Signal filtering

**How to Run:**
```bash
cd backend/notebooks
jupyter notebook 02_comet_signal_validation.ipynb
```

---

## Setup Instructions

### 1. Install Jupyter
```bash
pip install jupyter notebook matplotlib seaborn
```

### 2. Set Environment Variables
Make sure your `.env` file has:
```bash
ANTHROPIC_API_KEY=your_perplexity_api_key
FYERS_CLIENT_ID=your_fyers_client_id
# ... other variables
```

### 3. Start Jupyter
```bash
cd backend/notebooks
jupyter notebook
```

This will open Jupyter in your browser at `http://localhost:8888`

---

## Notebook Structure

Each notebook follows this pattern:

```
1. Setup & Imports
2. Initialize Comet AI / Prompt Manager
3. Load Data
4. Analysis / Validation
5. Comet AI Integration
6. Visualization
7. Export Results
8. Integration Guide
```

---

## Comet AI Integration

### Using Prompt Templates

All notebooks use the `PromptManager` to load structured prompts:

```python
from app.comet.mcp_client import MCPClient
from app.comet.prompt_manager import PromptManager

comet = MCPClient()
pm = PromptManager()

# Format and use template
prompt = pm.format_prompt(
    "signal_analysis",
    symbol="NIFTY",
    signal_type="BULLISH",
    entry_price=22000,
    # ... other parameters
)

response = comet.query(prompt)
```

### Available Templates

- `signal_analysis` - Analyze trading signals
- `risk_assessment` - Assess position/portfolio risk
- `market_context` - Broader market analysis
- `trade_plan` - Generate complete trade plans

See `../prompts/README.md` for template documentation.

---

## Data Sources

### Backtest Results
- `../volume_rocket_results.csv` - Volume Rocket strategy results
- `../historical_backtest_results.csv` - Historical backtests
- `../backtest_results/` - Strategy-specific results

### Signal Data
- Load from database (PostgreSQL)
- Load from Redis cache
- Load from CSV exports

### Market Data
- Fyers API (via FyersClient)
- Historical data in `../data_downloads/`

---

## Common Workflows

### Workflow 1: Post-Backtest Analysis
1. Run backtest (outside notebook)
2. Open `01_strategy_backtest_analysis.ipynb`
3. Load backtest CSV
4. Analyze metrics and visualizations
5. Use Comet to identify patterns
6. Generate optimization report

### Workflow 2: Pre-Trade Validation
1. Strategy generates signals
2. Open `02_comet_signal_validation.ipynb`
3. Load signals
4. Validate each signal with Comet AI
5. Get confidence scores
6. Execute high-confidence signals only

### Workflow 3: Strategy Development
1. Backtest new strategy
2. Analyze results in notebook
3. Get Comet suggestions
4. Modify strategy code
5. Re-backtest
6. Compare results

---

## Best Practices

### 1. Version Control
- Track notebook changes in git
- Use clear cell outputs for documentation
- Comment complex analysis steps

### 2. Data Management
- Don't commit large CSV files
- Use `.gitignore` for data files
- Document data sources

### 3. Comet AI Usage
- Cache similar queries to save API calls
- Use templates for consistency
- Monitor API usage and costs

### 4. Code Organization
- Keep analysis code in notebooks
- Production code in `app/` modules
- Import from `app/` instead of duplicating logic

### 5. Documentation
- Add markdown cells to explain analysis
- Include assumptions and limitations
- Document key insights

---

## Performance Tips

### 1. Data Loading
- Load only required date ranges
- Use `chunksize` for large CSVs
- Filter early to reduce memory

### 2. Visualization
- Use `%matplotlib inline` for inline plots
- Set reasonable figure sizes
- Save plots to files for reports

### 3. Comet AI Calls
- Batch similar queries when possible
- Use caching (see `../config/comet_config.yaml`)
- Avoid redundant analysis

---

## Troubleshooting

### Issue: Module Import Errors
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))
```

### Issue: Comet API Not Working
Check:
- `ANTHROPIC_API_KEY` environment variable set
- API key has sufficient credits
- Network connectivity

### Issue: Data Not Loading
Check:
- File paths are correct (relative to notebook location)
- CSV files exist in expected locations
- File permissions

---

## Adding New Notebooks

When creating new notebooks:

1. **Use Naming Convention:**
   - `##_descriptive_name.ipynb`
   - Example: `03_portfolio_optimization.ipynb`

2. **Include Standard Sections:**
   - Title and description
   - Setup/imports
   - Main analysis
   - Visualization
   - Export/integration guide

3. **Document in This README:**
   - Add to "Available Notebooks" section
   - Describe purpose and use cases
   - Include setup instructions

4. **Follow Template Structure:**
   - Initialize Comet AI if using
   - Load data from standard sources
   - Use existing utilities from `app/`

---

## Integration with Production Code

### Using Notebook Insights in Production

After analysis, integrate findings:

```python
# In app/strategies/my_strategy.py

from app.comet.mcp_client import MCPClient
from app.comet.prompt_manager import PromptManager

class MyStrategy:
    def __init__(self):
        self.comet = MCPClient()
        self.pm = PromptManager()
    
    def validate_signal(self, signal_data):
        """Validate signal using Comet (from notebook workflow)"""
        prompt = self.pm.format_prompt("signal_analysis", **signal_data)
        response = self.comet.query(prompt)
        # ... use response for decision
```

---

## Future Enhancements

Potential new notebooks to add:

- `03_portfolio_optimization.ipynb` - Portfolio rebalancing analysis
- `04_strategy_comparison.ipynb` - Compare multiple strategies
- `05_market_regime_detection.ipynb` - Identify market conditions
- `06_risk_metrics_dashboard.ipynb` - Real-time risk monitoring
- `07_signal_performance_tracking.ipynb` - Track signal accuracy over time

---

## Resources

- **Jupyter Documentation:** https://jupyter.org/documentation
- **Pandas Documentation:** https://pandas.pydata.org/docs/
- **Matplotlib Gallery:** https://matplotlib.org/stable/gallery/
- **Comet AI (Perplexity):** https://docs.perplexity.ai/

---

## Support

For issues or questions:
1. Check this README first
2. Review notebook comments and markdown cells
3. Check `../prompts/README.md` for template docs
4. Review `app/comet/` for Comet client code

---

**Last Updated:** December 6, 2025
