# ASX Weekly Market Report - AI Assistant Guide

## Project Overview

This is an automated ASX (Australian Securities Exchange) weekly market report system that:
- Fetches real-time ASX market data from Yahoo Finance
- Generates AI-powered market analysis using Z.ai GLM API
- Sends reports via email and publishes to GitHub Pages
- Runs every Saturday at 8:00 AM AEST (via cron or GitHub Actions)

**Current Report Structure:**
1. 市场概况 (Market Overview) - ASX 200 index performance with trend chart
2. 个股深度分析 (Stock Analysis) - 3-5 stocks dynamically selected based on news
3. 近期投资日历 (Investment Calendar) - Upcoming events (simplified format)
4. 风险提示 (Risk Alert) - Key immediate risks only (not generic long-term risks)

## Architecture

```
┌─────────────────┐
│  Scheduler      │ (cron / GitHub Actions)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  asx_weekly_reporter.py                 │
│  ┌───────────────────────────────────┐  │
│  │ get_real_time_data()              │  │
│  │   - Yahoo Finance HTML scraping   │  │
│  │   - ASX 200 index                 │  │
│  │   - Market news                   │  │
│  └───────────────────────────────────┘  │
│                 │                        │
│                 ▼                        │
│  ┌───────────────────────────────────┐  │
│  │ generate_market_research()        │  │
│  │   - 4 AI prompts (market overview,│  │
│  │     stock analysis, calendar,     │  │
│  │     risk alert)                   │  │
│  └───────────────────────────────────┘  │
│                 │                        │
│                 ▼                        │
│  ┌───────────────────────────────────┐  │
│  │ generate_report_content()         │  │
│  │   - Markdown → HTML conversion    │  │
│  │   - Generate ASX 200 chart        │  │
│  └───────────────────────────────────┘  │
│                 │                        │
│                 ▼                        │
│  ┌───────────────────────────────────┐  │
│  │ Output                            │  │
│  │   - Save HTML/TXT locally         │  │
│  │   - Send email                    │  │
│  │   - Update archive index          │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Key Components

### 1. Data Source (`get_real_time_data()`)
- **Primary**: Yahoo Finance HTML scraping (`_fetch_yahoo_finance_data()`)
- **Fallback**: Web search via Z.ai API
- **Data Retrieved**:
  - S&P/ASX 200 index (price, change, volume)
  - Market news headlines
  - Individual stock data (for stock analysis)

### 2. AI Prompts (`generate_market_research()`)
Uses Z.ai GLM API with 4 prompts:
1. **Market Overview** - ASX 200 analysis
2. **Stock Analysis** - Dynamically selects 3-5 stocks based on news
3. **Investment Calendar** - One line per event format
4. **Risk Alert** - Only immediate, event-driven risks

### 3. Chart Generation (`generate_asx_chart()`)
- Uses matplotlib to generate ASX 200 trend chart
- Past 1 month of data
- Returns base64-encoded data URL

### 4. Output Generation
- **HTML**: Styled report with responsive design
- **TXT**: Plain text for email
- **Archive Index**: Auto-updated `index.html` in docs/

## Important Design Decisions

### What Was Removed (and Why)
1. **Broker Recommendations** - Redundant with stock analysis section
2. **Sector Analysis** - Data availability issues; individual stocks are more valuable

### Report Format Guidelines
- **Investment Calendar**: One event per line, format: `Date - Description (1-2 sentences on market expectation)`
- **Risk Alert**: Only immediate risks with dates/trigger conditions, no generic long-term risks
- **Stock Analysis**: Dynamic selection based on news/events, not fixed stock list

## File Structure

```
asx_weekly_report/
├── asx_weekly_reporter.py    # Main script (~1400 lines)
├── setup.sh                   # Installation script
├── run_report.sh              # Quick run script
├── .env.example               # Environment template
├── .github/workflows/
│   └── asx-weekly-report.yml # GitHub Actions
├── docs/                      # GitHub Pages output
│   ├── index.html             # Archive index
│   └── asx_report_*.html      # Weekly reports
└── logs/                      # Run logs
```

## Environment Variables

Required in `.env` or GitHub Secrets:
```bash
ZAI_API_KEY=xxx                    # Z.ai GLM API key
GMAIL_ADDRESS=xxx@gmail.com        # Sender Gmail
GMAIL_APP_PASSWORD=xxxx xxxx       # Gmail app password (16 chars)
RECIPIENT_EMAIL=xxx@example.com    # Recipient (optional)
```

## Common Tasks

### Adding a New Report Section
1. Add API call in `generate_market_research()`
2. Add to return dict
3. Add HTML conversion in `generate_report_content()`
4. Add HTML section in template
5. Add TXT section in plain text format

### Modifying AI Prompts
Edit the prompt strings in `generate_market_research()`:
- Line ~750-780: Market overview prompt
- Line ~835-865: Stock analysis prompt
- Line ~868-890: Investment calendar prompt
- Line ~893-910: Risk alert prompt

### Changing Report Styling
Edit the HTML/CSS in `generate_report_content()`:
- Styles defined in `<style>` block (line ~1055-1190)
- Email-friendly, responsive design

## Yahoo Finance Data Fetching

The system uses HTML scraping for Yahoo Finance data:
- **Function**: `_fetch_yahoo_finance_data(ticker_symbol)`
- **Method**: Regex parsing of embedded JSON in HTML
- **Rate Limiting**: Consider adding delays if fetching multiple stocks
- **Reliability**: Generally reliable but may need fallbacks

**Note**: Yahoo Finance does NOT provide ASX sector index data. Individual stocks must be fetched separately if sector analysis is needed.

## Testing Changes

```bash
# Run locally
./run_report.sh

# Check output
cat asx_report_$(date +%Y%m%d).html
cat asx_report_$(date +%Y%m%d).txt

# Check logs
tail -f logs/cron.log
```

## Troubleshooting

| Issue | Likely Cause | Solution |
|-------|-------------|----------|
| No data fetched | Yahoo Finance scraping failed | Check network, test URL manually |
| AI returns generic content | Insufficient context in prompt | Review `realtime_context` passed to API |
| Email not sent | Gmail app password expired | Regenerate app password |
| GitHub Actions fails | Secrets not configured | Check repository Secrets |

## Future Enhancement Ideas

- [ ] Add stock price data fetch for multiple representative stocks
- [ ] Implement caching to reduce API calls
- [ ] Add more chart types (sector comparison, volume, etc.)
- [ ] Support for multiple recipients
- [ ] Add summary statistics (best/worst performers)
- [ ] Integration with ASX company announcements API

## Contact/Support

- Issues: Check `logs/cron.log` or GitHub Actions logs
- API: Z.ai GLM at https://open.bigmodel.cn/
- Data: Yahoo Finance at https://au.finance.yahoo.com/
