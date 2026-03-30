# Fintelligence — Backtests

## ⚠️ Run locally only — not on the server

These scripts validate the quantitative logic of the VolGuard system using historical NSE data.
They are **not part of the production system** and must not be run on the EC2 instance.

## Why not on EC2?

Both scripts use `yfinance` to download NIFTY 50 and India VIX data from Yahoo Finance.
Yahoo Finance blocks requests from AWS datacenter IP ranges — the same environment the
production server runs on. The scripts will fail silently or with connection errors if run there.

The production system uses Twelve Data + FRED + Upstox (all datacenter-friendly) for the same
underlying data. The backtest scripts have not been migrated to these sources because they are
development/research tools, not production code.

## What they test

| Script | What it validates |
|--------|-------------------|
| `vrp_backtest_10year.py` | VRP (Volatility Risk Premium) structural existence in NIFTY 50 over 10 years (2015–2025). Answers: does selling IV consistently outperform realised vol? |
| `volguard_v5_backtest.py` | Full end-to-end simulation of the VolGuard V5 regime-based strategy. Tests the scoring engine, mandate generation, and exit logic against historical data. |

## How to run locally

```bash
# Install dependencies (separate from production requirements)
pip install yfinance arch pandas numpy matplotlib seaborn scipy

# Run VRP existence proof
python backtests/vrp_backtest_10year.py

# Run full strategy backtest
python backtests/volguard_v5_backtest.py
```

Requires Python 3.10+ and an internet connection with access to Yahoo Finance.
