# FINTELLIGENCE
### Financial Intelligence Operating System for the Serious Indian Investor

---

Fintelligence is a self-hosted, institutional-grade financial intelligence platform built for one specific investor profile: the Indian options trader who sells Nifty premium overnight, pledges G-Secs as margin collateral, routes premium income into MF SIPs, and is accumulating direct equity for long-term pledging. Every module is built around that architecture.

This is not a dashboarding tool. It is a command center — five interconnected intelligence modules that reason about different layers of the same capital.

---

## The Capital Architecture

```
┌─────────────────────────────────────────────────────┐
│  LAYER 1 — GOVERNMENT SECURITIES (Foundation)        │
│  ₹10,00,000 pledged as margin collateral             │
│  90% haircut → releases ₹9L margin + earns ~7.2% yield│
└────────────────────────────┬────────────────────────┘
                             │ funds overnight option selling
┌────────────────────────────▼────────────────────────┐
│  LAYER 2 — OPTIONS ENGINE (Income)                   │
│  Nifty overnight premium selling                     │
│  Regime-scored, AI-gated, GTT-managed                │
└────────────────────────────┬────────────────────────┘
                             │ 40% premium → SIP · 20% withdrawn · 40% reserve
┌────────────────────────────▼────────────────────────┐
│  LAYER 3 — MUTUAL FUNDS (Compounding)                │
│  Funded by options premium                           │
│  Rolling returns, alpha, drawdown, holdings          │
└────────────────────────────┬────────────────────────┘
                             │ bluechip accumulation over time
┌────────────────────────────▼────────────────────────┐
│  LAYER 4 — DIRECT EQUITY (Long Game)                 │
│  Bluechip + large-cap + mid-cap                      │
│  Eventually pledged to expand options capacity       │
└─────────────────────────────────────────────────────┘

   ₹  TAX INTELLIGENCE — CROSS-LAYER
      F&O as business income · LTCG/STCG · Harvest engine · Advance tax
```

---

## The Five Modules

### VOLGUARD — Options & Volatility Intelligence
The flagship. A quantitative regime engine that scores market conditions 0–10 across three pillars, gates every trade with an AI reasoning layer, and monitors live positions with automated GTT orders.

**What it computes:**
- **Vol Score** — VoV z-score (4-band graduated penalty), IVP across 30D/90D/1Y windows, VIX momentum direction
- **Structure Score** — Proximity-weighted GEX regime, PCR-ATM balance, 25-delta skew, max pain
- **Edge Score** — Weighted VRP using GARCH(1,1) + Parkinson + historical RV, term structure (DTE-adjusted forward variance, not raw IV comparison)
- **Dynamic weights** — Automatically tilt toward vol signals in high-vol environments and toward edge signals in low-vol environments
- **Score stability** — Cross-validates against 3 alternative weight schemes; low variance = robust signal

**The AI layer:**
- Morning Brief Agent — fetches live macro (S&P, Nikkei, Hang Seng, US 10Y, DXY, USD/INR, crude, gold, crypto) and generates a synthesis of what it means for Nifty option sellers. When Claude key is set, adds live web search for causality ("why did US markets move today").
- Pre-Trade Agent — evaluates each mandate (weekly/monthly/next-weekly) against the quant score, macro context, and news. Issues PROCEED / PROCEED_WITH_CAUTION / VETO.
- Awareness Monitor — scans news feeds every 30 minutes during market hours for VETO-level keywords (RBI rate decision, Union Budget).
- AI Coach — analyses your full trade journal to identify skill vs luck in your P&L.

**Hard gates (rule-based, not AI):**
- VoV z-score ≥ 3.0 → ALL TRADES BLOCKED regardless of anything else
- Vol regime = EXPLODING → VETO
- VIX > 28 → VETO
- Regime score < 3.0 → VETO
- Expiry day or 1 DTE → BLOCKED

**Live data:**
- NIFTY spot, VIX, option chain via Upstox Analytics Token (valid 1 year, read-only)
- Daily broker token for live positions, orders, GTT (paste via UI each morning)
- FII/DII data from NSE
- Macro data from Twelve Data + FRED + CoinGecko (all datacenter-friendly, no AWS IP blocks)

---

### MF INTEL — Mutual Fund Intelligence
Analyses any AMFI-registered mutual fund from first principles using live NAV data.

**Metrics computed (pure Python, no LLM):**
- CAGR across 1Y/3Y/5Y/inception vs benchmark
- SIP XIRR — what a ₹10,000/month SIP investor actually earned (not NAV CAGR)
- Rolling return distributions (1Y/3Y/5Y) with percentile breakdowns (>0%, >8%, >12%, >risk-free)
- Sharpe, Sortino, standard deviation, max drawdown, crisis drawdowns (COVID, 2022 rate hike, IL&FS)
- Upside/downside capture ratios vs benchmark
- Beta, alpha, R-squared
- Portfolio overlap detection (up to 5 funds)

**Data sources:** mfapi.in (NAV history, scheme metadata), AMFI India (holdings, ISIN), mf.captnemo.in (AUM, expense ratio, manager)

**AI synthesis:** Groq (primary) or Claude — writes a plain-English brief explaining what the numbers mean, why this fund should or should not be in your portfolio, and what to watch.

---

### EQUITY — Stock Intelligence
Analyses any BSE-listed company. Reads the actual annual report via Gemini, fetches 10 years of financials from Screener.in, runs sector-specific valuation logic.

**Analysis pipeline:**
1. Fetch annual report PDF from BSE India API
2. Gemini 2.5 Flash reads the full document — extracts financial statements, qualitative signals, management tone, the hidden insight most analysts miss
3. Screener.in provides 10-year P&L, balance sheet, cash flow, ratios
4. Sector-specific DCF with domain-tuned parameters per sector (paints, IT, banks, FMCG, cement, pharma, auto, NBFC)
5. Reverse DCF — what earnings CAGR the market is pricing at CMP
6. ROCE spread — economic moat quantified as ROCE minus cost of capital
7. Pattern recognition — sector-specific signals (TiO2 cycle for paints, USD/INR for IT, steel for auto, etc.)
8. Early warning system — threshold-based alerts with sector calibration
9. Probability scenarios (bear/base/bull) with implied disruption probability
10. Groq — single synthesis: the essence, what the numbers show, the one risk, the price that makes it interesting

**Sector coverage with domain rules:** Paints, IT Services, Private Banks, FMCG, Cement, Pharma, Auto OEM, NBFC, Diversified

**Macro signals:** Per-sector commodity and macro indicator monitoring via Stooq (crude, steel, natural gas, palm oil, aluminium, US 10Y, USD/INR)

---

### TAX — Taxation Intelligence
Pure Python tax engine with Finance Act rules embedded. No LLM for computation — Python computes, Gemini only reads documents when asked.

**What it computes:**
- F&O income classification (business income, Section 43(5))
- Deductible expenses from F&O turnover (Section 37)
- LTCG/STCG on equity, equity MFs, debt MFs (pre/post Finance Act 2023), SGBs, listed bonds, G-Secs
- All rates reflect Budget 2024 No. 2 (effective 23 July 2024): LTCG 12.5%, STCG 20%
- Section 50AA — debt MF post April 2023 taxed at slab rate regardless of holding period
- New vs old regime comparison (FY 2025-26 slabs, Section 115BAC)
- Section 87A rebate for both regimes
- LTCG harvest opportunities — identifies unrealised gains eligible for the ₹1.25L annual exemption
- Advance tax schedule (Section 234C) with overdue detection
- Regime recommendation with actual rupee saving

**File parsing:** Zerodha Tax P&L CSV, CAMS consolidated statement

**Finance Act query:** Type any tax question — Gemini reads the actual Finance Act PDF and answers. Not from memory. Refuses investment advice and non-tax questions.

**Persistence:** Uploaded portfolio saved to SQLite — real brief survives container restarts.

---

## Architecture

```
https://localhost  (port 443, TLS 1.2/1.3)
       │
   [nginx]  ← rate limiting, auth on analyse, 15MB upload limit
       │
       ├── /api/mf/*      → MF backend       (port 8000, SQLite)
       ├── /api/equity/*  → Equity backend   (port 8000, SQLite)
       ├── /api/tax/*     → Tax backend      (port 8000, SQLite)
       ├── /api/*         → Volguard backend (port 8000, SQLite + WAL)
       ├── /ws            → Volguard WebSocket (live market data)
       └── /*             → React SPA (Vite build, served by nginx)
```

Four FastAPI backends in isolated Docker containers. Shared JWT authentication with soft token revocation. Per-user config overrides. Admin audit log for all user management actions.

**LLM provider chain:** Claude (Anthropic) → Groq → rule-based fallback. Hard trading gates always fire regardless of LLM status. VETO rules are never LLM-dependent.

---

## Deploy in One Command

### Prerequisites
- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- 8 GB RAM recommended (4 backends + frontend)
- API keys: Upstox Analytics Token (required for Volguard), GEMINI_API_KEY (required for Equity), GROQ_API_KEY or ANTHROPIC_API_KEY (for AI synthesis)

### Setup

**1. Configure environment**
```bash
cp .env.example .env
# Fill in your API keys — minimum required: JWT_SECRET, TOKEN_ENCRYPTION_KEY, UPSTOX_ANALYTICS_TOKEN, GEMINI_API_KEY
```

**2. Generate required secrets**
```bash
# JWT secret (required)
python3 -c "import secrets; print(secrets.token_hex(32))"

# Token encryption key (required)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**3. Build and start**
```bash
docker compose up --build
```
First build: 10–15 minutes (downloading all dependencies).
Subsequent starts: ~60 seconds.

**4. Open**
```
https://localhost
```
Your browser will show a self-signed certificate warning. Click Advanced → Proceed. This is expected — the cert is generated at build time. Replace with Let's Encrypt if you have a domain.

---

## After First Start

1. Register your account — the first user is automatically made admin
2. **Volguard:** Paste your Upstox Analytics Token (valid 1 year, no daily refresh needed)
3. **Volguard live trading:** Paste your daily OAuth token each morning before 9:15 IST (token expires at 03:30 IST)
4. **MF Intel:** Search any fund by name or AMC — first analysis takes 60–120 seconds
5. **Equity:** Search any company — first analysis takes 90–180 seconds (Gemini reads the annual report)
6. **Tax:** Loads demo portfolio automatically. Upload your Zerodha Tax P&L CSV + CAMS statement for real numbers.

---

## Multi-User Setup

Supports up to 20 users (configurable via `MAX_USERS` in `.env`).

- First user to register is automatically admin
- Admin can manage users via `/api/admin/users`
- Admin can revoke all tokens for any user via `/api/admin/users/{id}/revoke-tokens`
- Per-user config: `BASE_CAPITAL`, `MAX_LOSS_PCT`, `PROFIT_TARGET` — each user's risk limits are independent
- Global config (admin only): circuit breaker thresholds, VoV alert levels, strategy parameters
- All admin actions are logged to `admin_audit_log` table

---

## Stopping Safely

```bash
# Stop containers — preserves all data and trade history
docker compose down

# ⚠️ WARNING: This deletes all trade journals, analysis cache, and tax data
# docker compose down -v
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | ✅ | Signs all user session tokens. Generate with `secrets.token_hex(32)` |
| `TOKEN_ENCRYPTION_KEY` | ✅ | Encrypts Upstox tokens at rest. Generate with Fernet |
| `UPSTOX_ANALYTICS_TOKEN` | ✅ Volguard | 1-year read-only token for market data (quotes, option chain, Greeks) |
| `UPSTOX_API_KEY` | Live trading | From Upstox Developer Portal |
| `UPSTOX_API_SECRET` | Live trading | From Upstox Developer Portal |
| `GEMINI_API_KEY` | ✅ Equity | Gemini 2.5 Flash reads annual report PDFs |
| `GROQ_API_KEY` | Recommended | Free tier. Powers morning brief, pre-trade, MF/equity synthesis |
| `ANTHROPIC_API_KEY` | Optional | Claude — better quality synthesis, web search in morning brief |
| `TWELVE_DATA_API_KEY` | Recommended | Global macro data (S&P, Nasdaq, DXY, crude, gold). Free at twelvedata.com |
| `FRED_API_KEY` | Recommended | US 10Y Treasury yield. Free at fred.stlouisfed.org |
| `TELEGRAM_BOT_TOKEN` | Optional | Regime shift alerts and trade notifications |
| `TELEGRAM_CHAT_ID` | Optional | Target chat for Telegram alerts |
| `MAX_USERS` | Optional | Maximum registered users. Default: 20 |

---

## Data Persistence

All data survives container restarts via Docker named volumes:

| Volume | Contains |
|--------|----------|
| `volguard_data` | Trade journal, morning brief cache, position data, SQLite DB |
| `volguard_logs` | Volguard application logs (7-day rotation, 50MB/file) |
| `mf_data` | Fund analysis cache, search cache, analysis history |
| `equity_data` | Company brief cache, analysis history |
| `tax_data` | Uploaded portfolio data, tax brief cache |

---

## Security Model

- **HTTPS only** — nginx redirects all HTTP to HTTPS. TLS 1.2/1.3 only.
- **JWT authentication** — 30-day tokens signed with HS256. Soft revocation via `last_invalidated_at`.
- **Upstox tokens encrypted at rest** — Fernet symmetric encryption before DB storage.
- **Rate limiting** — Login: 10 req/min. General API: 60 req/min. AI analyse endpoints: 6 req/min (Gemini/Groq cost protection).
- **File upload limit** — 15MB per file (matches CAMS statement sizes).
- **Admin audit log** — Every user management action (patch, delete, revoke) is recorded immutably.
- **bcrypt** — All passwords hashed with bcrypt before storage.

---

## Troubleshooting

**Frontend shows blank page**
```bash
docker compose logs fintelligence_frontend
```

**Volguard not connecting**
- Analytics Token: paste in Volguard → Settings. Valid 1 year, no daily refresh.
- Daily trading token: paste each morning before 9:15 IST. Expires at 03:30 IST.
- Token from: Upstox app → Developer → Access Token

**MF / Equity analysis timing out**
- First analysis per fund/stock: 60–180 seconds (fetching data + AI synthesis)
- Subsequent requests: served from cache instantly
- Logs: `docker compose logs fintelligence_mf_backend`

**Equity analysis failing**
- Requires `GEMINI_API_KEY` — without it, every analysis fails at the PDF read step
- BSE India API occasionally returns 403 for unknown reasons. Retry usually works.
- Logs: `docker compose logs fintelligence_equity_backend`

**Tax upload returns 413**
- File exceeds 15MB limit. CAMS statements from 10+ year portfolios can be large.
- Export a date-filtered CAMS statement (current FY only) to reduce size.

**Container health check failing**
```bash
docker compose logs --tail=100 fintelligence_volguard_backend
```

---

## Development

### Run individual modules
```bash
# Dev ports (not exposed in production — all traffic goes through nginx on 443)
Volguard backend:  http://localhost:8001
MF backend:        http://localhost:8002
Equity backend:    http://localhost:8003
Tax backend:       http://localhost:8004
```

### Update shared auth logic
```bash
# Edit shared/auth_utils.py, then sync to all backends:
./sync_shared.sh
docker compose up --build
```

### Run backtests (local only — not on EC2)
```bash
# See backtests/README.md
pip install yfinance arch
python backtests/vrp_backtest_10year.py
```

---

## What's Not Here

**This system does not:**
- Execute orders automatically unless `AUTO_TRADING=true` in `.env` (disabled by default)
- Provide investment advice — every AI output ends with *"Intelligence, not advice. All reasoning shown. The investor decides."*
- Store your broker credentials — Upstox tokens are session-scoped and encrypted at rest
- Phone home — no telemetry, no external analytics, no third-party tracking

---

*Built for the serious Indian investor. March 2026.*
*No external capital. No team. No compromises.*
