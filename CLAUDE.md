# ASX Weekly Market Report - AI Assistant Guide

## Project Overview

This repository generates a weekly ASX market report with a **deterministic, rule-based pipeline**:

- Fetches ASX market data from Yahoo Finance
- Scrapes market headlines from public news pages
- Scores market regime and focus stocks with fixed rules
- Renders Markdown/HTML/TXT reports
- Sends email (optional) and publishes reports to GitHub Pages

## Key Flow

1. `get_real_time_data()` / Yahoo helpers fetch quotes and headlines
2. `_build_market_snapshot()` creates a structured snapshot
3. `_generate_market_overview()`, `_generate_stock_analysis()`, `_generate_investment_calendar()`, `_generate_risk_alert()` render deterministic sections
4. `generate_report_content()` builds the final HTML

## Rule Summary

- **Market overview**: weekly return, monthly return, 10-day volatility, and recent volume change
- **Stock analysis**: rank core ASX names by absolute move, news keyword hits, relative volume, and whether they move against the index
- **Investment calendar**: fixed recurring macro-event rules (RBA, NAB survey, Westpac confidence, labour force, CPI, earnings window)
- **Risk alert**: triggered by volatility, selloff + volume expansion, and upcoming macro events

## Environment Variables

```bash
GMAIL_ADDRESS=xxx@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx
RECIPIENT_EMAIL=xxx@example.com
OUTPUT_DIR=/optional/output/path
```

Email config is optional for local generation.

## Common Tasks

### Adjust thresholds or templates

- Market regime thresholds: `_classify_market_regime()`
- Stock ranking: `_rank_focus_stocks()`
- Event rules: `EVENT_RULES`
- News/theme matching: `STOCK_KEYWORDS`
- Output wording: `_generate_*()` helpers

### Styling

Edit the HTML/CSS in `generate_report_content()`.

## Testing

```bash
python3 -m unittest discover -s tests
python3 asx_weekly_reporter.py
```

## Notes

- Yahoo Finance scraping is still the primary data source
- `docs/` contains generated historical reports and archive pages
- The default runtime path no longer calls any LLM service
