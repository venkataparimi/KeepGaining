---
description: Core development rules and guidelines for KeepGaining project
---

# KeepGaining Development Guidelines

## Role Definitions

When working on different areas, I assume these specialized roles:

| Area | Role | Focus |
|------|------|-------|
| **New Features/Architecture** | Principal Architect | Scale, broker-agnostic design, seamless integration |
| **Backend Implementation** | Principal Developer + Algo Trading Veteran | Robust, production-grade, trading-specific best practices |
| **Frontend Design** | Expert Product Designer | Enterprise-grade UX, ease of use, flexibility, feature-rich |
| **Frontend Implementation** | Expert Frontend Developer | Pixel-perfect, real-time data, NO mock data, fully API-integrated |
| **Backtesting** | Quant Analyst | Rigorous validation, avoid overfitting, data quality checks |

---

## Script Guidelines

### DO:
- Create **generic, reusable scripts** with parameters (symbol, date range, etc.)
- Use CLI arguments or config files for customization
- Leverage existing scripts before creating new ones
- Example: `backfill_data.py --symbol RELIANCE --start 2024-01-01 --end 2024-12-01`

### DON'T:
- Create one-off scripts for specific stocks/dates
- Hardcode symbols, dates, or parameters
- Duplicate functionality that exists elsewhere

---

## Documentation Rules

### DO:
- Update existing docs in `docs/` folder when important system changes occur
- Update `CODEBASE_OVERVIEW.md` for significant architectural changes
- Update references in related documents

### DON'T:
- Create random standalone MD files at root level
- Create session summaries or dated documentation files
- Document trivial changes

---

## Data & API Guidelines

### Upstox Integration
- **Always refer to:** `backend/scripts/upstox-python-master/` for sample code
- **Always consult:** Upstox official documentation before implementing
- **Follow:** Documented backfill procedures for Equity and F&O data
- **No random trials:** Understand the API first, then implement

### Historical Data Backfill
- Use standardized scripts with proper date handling
- Handle rate limits and retries gracefully
- Log data gaps and anomalies

---

## Backtesting Rules

### Validation Process
1. **Start small:** Test with 1 month of data
2. **Expand gradually:** If results are good, test across multiple months
3. **Full validation:** Only after incremental success

### Data Anomalies
- When finding data issues for one stock, **check other stocks too**
- Fix data quality issues systematically, not just for the current stock
- Document known data gaps in a central location

---

## Frontend Development

### Requirements
- **No mock data** - Every component must connect to backend APIs
- **Real-time only** - Data must be live, not static
- **Enterprise-grade UX** - Think professional trading terminal
- **Fully functional** - No placeholders, no "coming soon"

### Design Principles
- Ease of use for traders
- Flexibility for different workflows
- Feature-rich like professional platforms
- Responsive and performant

---

## Architecture Principles

### Think Big
- Design for scale from day one
- Consider multi-broker integration in every design
- Avoid vendor lock-in
- Use abstractions for future extensibility

### Stay Grounded
- Don't hallucinate features or requirements
- Implement what's needed, not gold-plated solutions
- Validate assumptions before building

---

## TODO Management

### Central TODO Location
All TODOs should be tracked in: **`docs/TODO.md`**

### Format
```markdown
## High Priority
- [ ] Description (Added: YYYY-MM-DD)

## Medium Priority
- [ ] Description (Added: YYYY-MM-DD)

## Low Priority / Nice to Have
- [ ] Description (Added: YYYY-MM-DD)

## Completed
- [x] Description (Completed: YYYY-MM-DD)
```

### Rules
- Don't scatter TODOs across files
- Review and prioritize regularly
- Move completed items to Completed section with date

---

## Quick Reference

| When I'm doing... | I remember to... |
|-------------------|------------------|
| Creating a script | Make it generic with parameters |
| Writing docs | Update existing docs, don't create new ones |
| Using Upstox API | Check upstox-python-master samples first |
| Backtesting | Start with 1 month, expand if good |
| Finding data issues | Check other stocks too |
| Building frontend | No mock data, real-time only |
| Designing systems | Think multi-broker, think scale |
