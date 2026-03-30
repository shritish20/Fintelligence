# ============================================================================
# FINTELLIGENCE — Equity Intelligence  |  Module 2  |  Institutional Build
#
# Philosophy:
#   Python reasons about numbers. LLMs read documents.
#   Output is dense and compact — every line earns its place.
#   The brief tells you what you are buying, what breaks it,
#   and at what price the risk/reward makes sense.
#
# Architecture:
#   Gemini 2.5 Flash — reads annual report PDF once
#   Screener          — 10Y company history + sector peers
#   Pure Python       — all pattern recognition, all computations
#   Groq              — ONE synthesis: the essence sentence + verdict
#
# Usage: import as a module. Keys are read from environment variables.
#   GEMINI_API_KEY and GROQ_API_KEY must be set before importing.
#   Call initialize() to connect API clients, or set _GEM / _GROQ directly.
# ============================================================================

import os
import logging
_log = logging.getLogger("equity_engine")
import re, json, time, warnings, textwrap, math
import requests
from datetime import datetime
from typing import Optional
warnings.filterwarnings("ignore")

from google import genai
from google.genai import types
from groq import Groq
from bs4 import BeautifulSoup

# ============================================================================
# API CLIENTS — populated at startup by initialize() or by main.py directly
# ============================================================================

_GEM  = None   # google.genai.Client — set by initialize() or main.py
_GROQ = None   # groq.Groq           — set by initialize() or main.py


def initialize(gem_key: str = "", groq_key: str = "") -> None:
    """
    Connect API clients. Called once at service startup.
    Falls back to environment variables if keys not passed explicitly.
    main.py may also set _GEM / _GROQ directly after import.
    """
    global _GEM, _GROQ
    gk = gem_key  or os.getenv("GEMINI_API_KEY", "")
    rk = groq_key or os.getenv("GROQ_API_KEY",   "")
    if gk:
        try:
            _GEM = genai.Client(api_key=gk)
        except Exception as e:
            import logging; logging.getLogger(__name__).warning(f"Gemini init failed: {e}")
    if rk:
        try:
            _GROQ = Groq(api_key=rk)
        except Exception as e:
            import logging; logging.getLogger(__name__).warning(f"Groq init failed: {e}")

# ============================================================================
# SECTOR INTELLIGENCE PROFILES
# Every rule in these profiles is domain knowledge encoded as Python logic.
# No LLM involved in interpreting these — pure rule-based reasoning.
# ============================================================================


# ============================================================================
# MACRO DATA — Stooq real-time signals
# No API key. No rate limit. Works on any server / datacenter.
# Replaces yfinance which is blocked on server IPs.
# ============================================================================

import pandas as pd  # already imported above, belt-and-suspenders

_EQUITY_MACRO_TICKERS = {
    'crude_wti':   'cl.f',      # WTI Crude futures
    'usd_inr':     'usdinr',    # USD/INR spot
    'natural_gas': 'ng.f',      # Natural Gas futures
    'aluminium':   'almd.f',    # Aluminium futures
    'us_10y':      '10yt.b',    # US 10Y Treasury yield
    'palm_oil':    'fcpo.mde',  # Malaysia Palm Oil futures
    'tio2_proxy':  'trox.us',   # Tronox Holdings — TiO2 proxy stock
}


def fetch_macro() -> dict:
    """
    Fetch commodity and macro indicators via Stooq.
    Returns dict with current price, 6M change, 1Y change per asset.
    Used by macro_sector_signal() for sector-specific impact analysis.
    """
    macro = {}
    for name, ticker in _EQUITY_MACRO_TICKERS.items():
        try:
            url = f'https://stooq.com/q/d/l/?s={ticker}&i=d'
            df  = pd.read_csv(
                url,
                storage_options={'User-Agent': 'Mozilla/5.0'},
                parse_dates=['Date'],
            )
            df = df.sort_values('Date').dropna(subset=['Close'])
            if len(df) < 2:
                continue
            current = round(float(df['Close'].iloc[-1]), 4)
            p6m     = float(df['Close'].iloc[-126]) if len(df) >= 126 else float(df['Close'].iloc[0])
            p1y     = float(df['Close'].iloc[0])
            macro[name] = {
                'current': current,
                'chg_6m':  round((current - p6m) / p6m * 100, 1) if p6m > 0 else None,
                'chg_1y':  round((current - p1y) / p1y * 100, 1) if p1y > 0 else None,
            }
        except Exception:

            _log.warning("Suppressed exception", exc_info=True)
    return macro

# ============================================================================

# fetch_macro() is defined above using Stooq — no yfinance needed


def macro_sector_signal(macro, sector):
    """Convert macro data to sector-specific signals using domain knowledge."""
    if not macro:
        return [{"signal":"NEUTRAL","text":"Macro data unavailable.","impact":"UNKNOWN"}]
    signals = []
    crude  = macro.get("crude_wti",{})
    usd    = macro.get("usd_inr",{})
    tio2   = macro.get("tio2_proxy",{})
    steel  = macro.get("steel_hrc",{})
    gas    = macro.get("natural_gas",{})
    palm   = macro.get("palm_oil",{})
    us10y  = macro.get("us_10y",{})
    alum   = macro.get("aluminium",{})

    if sector == "paints":
        if tio2.get("chg_6m") and tio2["chg_6m"] > 20:
            signals.append({"signal":"WARNING",
                "text":f"TiO2 proxy +{tio2['chg_6m']:.0f}% in 6M → ~{tio2['chg_6m']*0.025:.1f}pp EBITDA compression. "
                       "AP took ~6 months to pass through in FY2022 TiO2 spike.","impact":"MARGIN"})
        elif tio2.get("chg_6m") and tio2["chg_6m"] < -15:
            signals.append({"signal":"POSITIVE",
                "text":f"TiO2 proxy {tio2['chg_6m']:.0f}% in 6M → ~{abs(tio2['chg_6m'])*0.02:.1f}pp margin tailwind. "
                       "Companies retain ~60% of input benefit.","impact":"MARGIN"})
        if crude.get("chg_6m") and crude["chg_6m"] > 25:
            signals.append({"signal":"WARNING",
                "text":f"Crude +{crude['chg_6m']:.0f}% in 6M → solvents/resin costs rising. "
                       "Rule: every 10% crude rise = ~0.6-0.8pp EBITDA compression (2-3Q lag).","impact":"MARGIN"})
        elif crude.get("chg_6m") and crude["chg_6m"] < -20:
            signals.append({"signal":"POSITIVE",
                "text":f"Crude {crude['chg_6m']:.0f}% in 6M → margin expansion cycle. "
                       "AP historically expands EBITDA 150-200bps in 2 quarters after crude down-cycle.","impact":"MARGIN"})

    elif sector == "it_services":
        if usd.get("chg_6m") and abs(usd["chg_6m"]) > 3:
            direction = "+" if usd["chg_6m"] > 0 else ""
            impact = "tailwind" if usd["chg_6m"] > 0 else "headwind"
            uplift = round(abs(usd["chg_6m"])*0.65*0.6,1)
            signals.append({"signal":"POSITIVE" if usd["chg_6m"]>0 else "WARNING",
                "text":f"USD/INR {direction}{usd['chg_6m']:.1f}% in 6M → INR revenue {impact} ~{uplift:.1f}% "
                       "(65% USD revenue assumed). Net margin impact ~{uplift*0.3:.1f}pp.","impact":"REVENUE"})
        if us10y.get("current") and us10y["current"] > 4.5:
            signals.append({"signal":"WARNING",
                "text":f"US 10Y at {us10y['current']:.1f}% → tech budgets compressed. "
                       "Historical pattern: IT deal wins slow 2-3 quarters after US 10Y crosses 4.5%.","impact":"DEMAND"})

    elif sector == "fmcg":
        if palm.get("chg_6m") and palm["chg_6m"] > 20:
            signals.append({"signal":"WARNING",
                "text":f"Palm oil +{palm['chg_6m']:.0f}% in 6M → FMCG personal care/food input pressure. "
                       "HUL takes 1-2 price increases/year to defend margins.","impact":"MARGIN"})
        elif palm.get("chg_6m") and palm["chg_6m"] < -20:
            signals.append({"signal":"POSITIVE",
                "text":f"Palm oil {palm['chg_6m']:.0f}% in 6M → margin tailwind. "
                       "Companies invest ~40% of benefit in A&P, retain 60%.","impact":"MARGIN"})

    elif sector == "cement":
        if gas.get("chg_6m") and gas["chg_6m"] > 30:
            signals.append({"signal":"WARNING",
                "text":f"Natural gas +{gas['chg_6m']:.0f}% in 6M → captive power cost rising. "
                       "Rule: every 10% gas rise = ₹20-25/tonne cost for gas-based plants.","impact":"COST"})
        elif gas.get("chg_6m") and gas["chg_6m"] < -25:
            signals.append({"signal":"POSITIVE",
                "text":f"Gas {gas['chg_6m']:.0f}% in 6M → EBITDA/tonne expansion likely.","impact":"COST"})

    elif sector == "auto_oem":
        if steel.get("chg_6m") and steel["chg_6m"] > 20:
            signals.append({"signal":"WARNING",
                "text":f"Steel HRC +{steel['chg_6m']:.0f}% in 6M → auto OEM input costs rising. "
                       "Rule: every 10% steel rise = 100-150bps margin compression (1Q lag).","impact":"MARGIN"})
        elif steel.get("chg_6m") and steel["chg_6m"] < -15:
            signals.append({"signal":"POSITIVE",
                "text":f"Steel {steel['chg_6m']:.0f}% in 6M → margin expansion next quarter. "
                       "Maruti/M&M: historically 80-120bps benefit per 15%+ steel decline.","impact":"MARGIN"})

    elif sector == "pharma":
        if usd.get("chg_6m") and usd["chg_6m"] > 3:
            signals.append({"signal":"POSITIVE",
                "text":f"USD/INR +{usd['chg_6m']:.1f}% → US generics revenue tailwind. "
                       "Net margin benefit ~0.2-0.3% per 1% USD appreciation after raw material offset.","impact":"REVENUE"})

    if not signals:
        signals.append({"signal":"NEUTRAL","text":"No significant macro signal for this sector.","impact":"NEUTRAL"})

    return signals

# Full institutional sector profiles — 8 sectors, full depth
# Thresholds calibrated from Indian market stress events FY2009-FY2024

SECTOR_PROFILES = {

    "paints": {
        "peers":       ["BERGEPAINT", "KANSAINER", "AKZOINDIA"],
        "peer_names":  ["Berger Paints", "Kansai Nerolac", "Akzo Nobel India"],
        "normal_roce": (15, 28), "normal_margin": (12, 20),
        "key_metrics": ["roce","ebitda_margin","nwc_days","cfo_to_pat","rev_cagr_5y"],
        "value_driver": (
            "Negative working capital is the structural moat — 75,000 dealers pay before AP pays suppliers. "
            "Every ₹1,000Cr revenue growth needs zero incremental working capital. "
            "ROCE premium vs peers (41% vs 18% sector median) is the moat made quantifiable. "
            "This compounding is invisible to P/E and EV/EBITDA screens."
        ),
        "causal_rules": [
            {
                "name": "dealer_funded_operations",
                "condition": lambda m: (m.get("nwc_days") or 0) < -10,
                "insight": lambda m: (
                    f"Negative NWC {m.get('nwc_days',0):.0f} days = dealers funding "
                    f"₹{abs((m.get('nwc_days',0))*(m.get('revenue') or 0)/365):,.0f}Cr operations. "
                    "Zero-cost capital that grows 13% annually as revenue grows. "
                    "At ₹35,000Cr revenue: ₹1,440Cr dealer-funded. At ₹70,000Cr: ₹2,877Cr. "
                    "This does not appear in any standard ratio."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "nwc_deterioration_competitive",
                "condition": lambda m: (
                    len(m.get("nwc_hist",[]))>=3 and
                    (m.get("nwc_days") or 0) > (sum(m.get("nwc_hist",[0,0,0])[:3])/3)+20
                ),
                "insight": lambda m: (
                    f"NWC deteriorated {(m.get('nwc_days',0)-sum(m.get('nwc_hist',[0,0,0])[:3])/3):.0f}d vs 3Y avg. "
                    "Dealer credit extended = AP funding distributor inventory. "
                    "Historically precedes volume slowdown by 1-2 quarters. "
                    "Check if Grasim pressure forcing channel credit to defend shelf space."
                ),
                "signal": "WARNING",
            },
            {
                "name": "capex_cycle_normal",
                "condition": lambda m: (
                    (m.get("roce") or 0)>25 and (m.get("cwip_pct") or 0)>12 and
                    m.get("roce_trend")=="DECLINING"
                ),
                "insight": lambda m: (
                    f"ROCE {m.get('roce',0):.1f}% declining with CWIP {m.get('cwip_pct',0):.0f}% of gross block. "
                    "Capex cycle compression — capital employed rises before revenue follows. "
                    "AP FY2015-18: ROCE fell 48%→37%, recovered 45% by FY2021 as plants utilised. "
                    "With Khandala/Kasna/Pithampur committed, trough likely FY2025, recovery FY2027."
                ),
                "signal": "NORMAL",
            },
            {
                "name": "structural_decline_not_capex",
                "condition": lambda m: (
                    (m.get("roce") or 0)>15 and (m.get("cwip_pct") or 0)<8 and
                    m.get("roce_trend")=="DECLINING"
                ),
                "insight": lambda m: (
                    f"ROCE {m.get('roce',0):.1f}% declining WITHOUT capex cycle (CWIP only {m.get('cwip_pct',0):.0f}%). "
                    "Not a timing issue — investigate pricing power loss or dealer incentive overspend. "
                    "If incentive spend is rising toward 4%+, competitive war is underway."
                ),
                "signal": "WARNING",
            },
            {
                "name": "inventory_days_stress",
                "condition": lambda m: (m.get("inventory_days") or 0)>155,
                "insight": lambda m: (
                    f"Inventory {m.get('inventory_days',0):.0f}d above normal (120-145 for AP). "
                    "Two explanations: demand softening OR strategic TiO2/resin pre-buy. "
                    "FY2022: AP stocked TiO2 ahead of 80% price spike (benign). "
                    "FY2020 COVID: hit 168d from demand collapse (bearish). "
                    "Annual report commentary distinguishes which scenario."
                ),
                "signal": "WARNING",
            },
            {
                "name": "margin_expansion_raw_material",
                "condition": lambda m: (
                    len(m.get("margin_hist",[]))>=3 and
                    (m.get("ebitda_margin") or 0)>(sum(m.get("margin_hist",[0,0,0])[1:4])/3)+2
                ),
                "insight": lambda m: (
                    f"Margin {m.get('ebitda_margin',0):.1f}% — "
                    f"{m.get('ebitda_margin',0)-sum(m.get('margin_hist',[0,0,0])[1:4])/3:.1f}pp above 3Y avg. "
                    "Either raw material tailwind (cyclical, check TiO2/crude) or "
                    "premiumisation into Royale/Eminence (durable). "
                    "Former normalises in 2-3 quarters. Latter compounds."
                ),
                "signal": "INFO",
            },
            {
                "name": "cfo_pat_gap",
                "condition": lambda m: (m.get("cfo_to_pat") or 1.0)<0.80,
                "insight": lambda m: (
                    f"CFO/PAT {m.get('cfo_to_pat',0):.2f} — below AP historical avg 1.05. "
                    "Paint sector red flag. Below 0.80 = working capital expansion or "
                    "channel loading ahead of price hike. "
                    "Two consecutive quarters below 0.75 = revenue quality degrading."
                ),
                "signal": "WARNING",
            },
            {
                "name": "roce_sector_dominance",
                "condition": lambda m: (m.get("roce") or 0)>35,
                "insight": lambda m: (
                    f"ROCE {m.get('roce',0):.1f}% — top 5% of Indian listed universe. "
                    "Even at this level, ROCE compression of 5-10pp is still exceptional. "
                    "The question is not the level but sustainability as Grasim builds "
                    "distribution through UltraTech's 65,000 dealer touchpoints."
                ),
                "signal": "STRENGTH",
            },
        ],
        "early_warnings": [
            {"metric":"inventory_days","label":"Inventory Days","threshold_warn":155,"threshold_crit":170,
             "calibration":"AP normal 120-145. COVID FY2020: 168. TiO2 prebuy FY2022: 158."},
            {"metric":"receivable_days","label":"Receivable Days","threshold_warn":55,"threshold_crit":65,
             "calibration":"AP normal 40-50. Above 55 = credit to defend share. FY2019 slowdown: 58.",
             "interpretation":"Credit extension ahead of revenue = channel stuffing signal."},
            {"metric":"cfo_to_pat","label":"CFO / PAT","threshold_warn":0.82,"threshold_crit":0.65,
             "calibration":"AP avg 1.05. Below 0.82 = WC stress. Below 0.65 = aggressive recognition.",
             "lower_is_worse":True},
            {"metric":"ebitda_margin","label":"EBITDA Margin %","threshold_warn":16.0,"threshold_crit":13.0,
             "calibration":"AP normal 18-24%. TiO2 crisis FY2022: 14.8%. Below 16% = structural problem.",
             "lower_is_worse":True},
        ],
        "scenarios": {
            "base":        {"label":"Compounder continues","probability":0.55,"rev_cagr_mult":1.00,"margin_delta":0.0,"pe_exit":50,
                            "trigger":"Historical 13% growth continues. Grasim gains <5% share by FY2027."},
            "disruption":  {"label":"Grasim takes share","probability":0.25,"rev_cagr_mult":0.55,"margin_delta":-4.5,"pe_exit":28,
                            "trigger":"Grasim 40,000 touchpoints. AP incentive spend >4.5%. Price war confirmed."},
            "acceleration":{"label":"Premiumisation re-rates","probability":0.20,"rev_cagr_mult":1.30,"margin_delta":2.5,"pe_exit":62,
                            "trigger":"Home decor hits 10% of Decorative. Rural recovery broadens volume base."},
        },
        "break_point": (
            "Dealer incentive spend crosses 4.2% of revenue for 2 consecutive quarters "
            "(currently ~3.2%). Signals AP buying market share, not earning it. "
            "Expect 300-400bps EBITDA compression and P/E de-rating 50x→28x. "
            "Downside at that point: 35-40%."
        ),
        "hidden_alpha": (
            "Negative working capital is a compounding asset invisible to standard screens. "
            "Growing revenue 13% annually also grows zero-cost dealer capital 13%. "
            "This does not appear in P/E, EV/EBITDA, or any ratio commonly screened."
        ),
    },

    "it_services": {
        "peers":       ["TCS","INFY","WIPRO","HCLTECH"],
        "peer_names":  ["TCS","Infosys","Wipro","HCL Tech"],
        "normal_roce": (25,45), "normal_margin": (20,28),
        "key_metrics": ["ebitda_margin","roce","cfo_to_pat","rev_cagr_5y"],
        "value_driver": (
            "Revenue per employee is the only metric that predicts long-term margin. "
            "Utilisation above 85% = pricing power. Attrition cost is hidden: replacing one "
            "engineer costs 6-9 months of lost productivity. "
            "Large deal TCV is a 12-18 month leading revenue indicator — most analysts ignore it."
        ),
        "causal_rules": [
            {
                "name": "utilisation_margin_link",
                "condition": lambda m: (
                    len(m.get("margin_hist",[]))>=3 and
                    (m.get("ebitda_margin") or 0)<(sum(m.get("margin_hist",[0,0,0])[:3])/3)-2.0
                ),
                "insight": lambda m: (
                    f"Margin {m.get('ebitda_margin',0):.1f}% — "
                    f"{sum(m.get('margin_hist',[0,0,0])[:3])/3-m.get('ebitda_margin',0):.1f}pp below 3Y avg. "
                    "IT margin compression = attrition spike or utilisation decline. "
                    "FY2022-23: TCS/Infy attrition 19-21% added 200-250bps cost. "
                    "Post-normalisation (now ~12%), margin recovery should lag 1-2 quarters."
                ),
                "signal": "WARNING",
            },
            {
                "name": "revenue_cagr_deceleration",
                "condition": lambda m: (m.get("rev_cagr_3y") or 0)<(m.get("rev_cagr_5y") or 0)*0.6,
                "insight": lambda m: (
                    f"Revenue CAGR: 3Y {m.get('rev_cagr_3y',0):.1f}% vs 5Y {m.get('rev_cagr_5y',0):.1f}%. "
                    "Significant deceleration. Either demand cycle (BFSI/retail tech cuts) or "
                    "market share loss. FY2024 industry: 4-6% vs FY2022: 14-18%. Demand-driven. "
                    "If GenAI adoption is displacing offshore FTEs, this becomes structural."
                ),
                "signal": "WARNING",
            },
            {
                "name": "deal_win_momentum",
                "condition": lambda m: (m.get("rev_cagr_3y") or 0)>(m.get("rev_cagr_5y") or 0)*1.1,
                "insight": lambda m: (
                    f"Revenue accelerating: 3Y {m.get('rev_cagr_3y',0):.1f}% vs 5Y {m.get('rev_cagr_5y',0):.1f}%. "
                    "Large deal wins from 12-18 months ago are ramping. "
                    "Sustainable only if deal TCV pipeline remains strong. "
                    "Check: is headcount growing proportionally or is productivity also rising?"
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "high_cfo_pat_quality",
                "condition": lambda m: (m.get("cfo_to_pat") or 0)>1.1,
                "insight": lambda m: (
                    f"CFO/PAT {m.get('cfo_to_pat',0):.2f} — excellent for IT services. "
                    "Low capital intensity + advance billing = cash-generative model. "
                    "Above 1.15 = strong client payment discipline or favourable milestone billing on large deals."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "ai_disruption_revenue_signal",
                "condition": lambda m: (m.get("rev_cagr_3y") or 0)<6 and (m.get("ebitda_margin") or 0)<22,
                "insight": lambda m: (
                    f"Revenue growth {m.get('rev_cagr_3y',0):.1f}% AND margin {m.get('ebitda_margin',0):.1f}% — both below normal. "
                    "Dual stress: demand drought + cost pressure simultaneously. "
                    "If revenue per employee is also stagnant: AI displacement risk is real, not cyclical. "
                    "If revenue per employee is rising: demand cycle, not structural."
                ),
                "signal": "WARNING",
            },
            {
                "name": "roce_capital_light",
                "condition": lambda m: (m.get("roce") or 0)>40,
                "insight": lambda m: (
                    f"ROCE {m.get('roce',0):.1f}% — exceptional, driven by capital-light model. "
                    "Sustainable as long as pricing power holds and AI does not compress the talent arbitrage. "
                    "The risk: GenAI enabling 30% more output per engineer = headcount falls = "
                    "revenue per employee rises but total revenue stagnates."
                ),
                "signal": "STRENGTH",
            },
        ],
        "early_warnings": [
            {"metric":"ebitda_margin","label":"EBITDA Margin %","threshold_warn":21,"threshold_crit":18,
             "calibration":"TCS/Infy normal 24-27%. FY2023 attrition peak: 22%. Below 21% = structural.",
             "lower_is_worse":True},
            {"metric":"rev_cagr_3y","label":"Revenue CAGR 3Y %","threshold_warn":8,"threshold_crit":4,
             "calibration":"Normal 10-18%. GFC FY2009: -3%. FY2024 slowdown: 5-7%.",
             "lower_is_worse":True},
            {"metric":"cfo_to_pat","label":"CFO / PAT","threshold_warn":0.85,"threshold_crit":0.70,
             "calibration":"Normal 0.95-1.15. Below 0.85 = unbilled revenue building.",
             "lower_is_worse":True},
        ],
        "scenarios": {
            "base":        {"label":"Steady recovery","probability":0.50,"rev_cagr_mult":1.00,"margin_delta":0,"pe_exit":25,
                            "trigger":"US tech spend stabilises. Deal TCV normalises $3-4B/quarter."},
            "disruption":  {"label":"AI displaces offshore","probability":0.25,"rev_cagr_mult":0.45,"margin_delta":-4.0,"pe_exit":14,
                            "trigger":"Revenue per employee declining YoY. Client FTE cuts confirmed."},
            "acceleration":{"label":"Vendor consolidation","probability":0.25,"rev_cagr_mult":1.35,"margin_delta":1.5,"pe_exit":30,
                            "trigger":"Large deal TCV >$5B two consecutive quarters."},
        },
        "break_point": (
            "Revenue per employee declining YoY for 2 consecutive years = AI displacement is structural. "
            "Sector de-rates 22-25x → 12-15x P/E. "
            "Early signal: company adding headcount while revenue stagnates. "
            "That combination means no productivity gain and the offshore FTE model is cracking."
        ),
        "hidden_alpha": (
            "Deal TCV in trailing 2 quarters is 12-18 month leading revenue indicator. "
            "Analysts track quarterly revenue. The right signal is deal pipeline. "
            "Strong TCV + weak current revenue = timing gap, not structural problem. "
            "Weak TCV + weak revenue = demand crisis."
        ),
    },

    "private_bank": {
        "peers":       ["HDFCBANK","ICICIBANK","KOTAKBANK","AXISBANK"],
        "peer_names":  ["HDFC Bank","ICICI Bank","Kotak Bank","Axis Bank"],
        "normal_roce": (12,18), "normal_margin": (None,None),
        "key_metrics": ["roe","debt_equity","cfo_to_pat"],
        "value_driver": (
            "CASA ratio → cost of funds → NIM → ROA → ROE. The entire thesis lives in that chain. "
            "45% CASA at 3% cost vs 30% CASA at 5% cost = 90bps structural NIM advantage. "
            "At 10:1 leverage: 9% ROE difference. "
            "CASA trajectory is the most important number in a bank's annual report."
        ),
        "causal_rules": [
            {
                "name": "casa_erosion_signal",
                "condition": lambda m: (
                    len(m.get("roce_arr",[]))>=3 and
                    (m.get("roe") or 0)<(sum(m.get("roce_arr",[0,0,0])[:3])/3)-2
                ),
                "insight": lambda m: (
                    f"ROE {m.get('roe',0):.1f}% below 3Y avg — NIM compression or rising credit costs. "
                    "FY2015-18 NPA cycle: private bank ROEs compressed 400-600bps. "
                    "Distinguish: funding cost pressure (fixable in 2-4 quarters) vs "
                    "asset quality (structural, takes 6-12 quarters to resolve)."
                ),
                "signal": "WARNING",
            },
            {
                "name": "high_roe_quality",
                "condition": lambda m: (m.get("roe") or 0)>17,
                "insight": lambda m: (
                    f"ROE {m.get('roe',0):.1f}% — top quartile Indian private banks. "
                    "Requires simultaneously: low cost of funds (CASA 40%+) + strong NIM (3%+) + "
                    "low credit costs (<1%). All three must hold. "
                    "Watch GNPA in MSME and unsecured retail — the weakest link historically."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "leverage_warning",
                "condition": lambda m: (m.get("debt_equity") or 0)>8,
                "insight": lambda m: (
                    f"D/E {m.get('debt_equity',0):.1f}x — normal for banks but high leverage means "
                    "small credit quality deterioration has large equity impact. "
                    "1% credit cost rise at 9x leverage = ~9% ROE hit in one quarter."
                ),
                "signal": "INFO",
            },
            {
                "name": "credit_cost_normalisation",
                "condition": lambda m: (m.get("pat_cagr_3y") or 0)>(m.get("rev_cagr_3y") or 0)*1.5,
                "insight": lambda m: (
                    f"PAT CAGR {m.get('pat_cagr_3y',0):.1f}% >> Revenue CAGR {m.get('rev_cagr_3y',0):.1f}%. "
                    "For a bank: provisions declining (credit costs normalising post-cycle). "
                    "Post-COVID FY2021-22: most private banks saw PAT grow 40-60% as provisions fell. "
                    "Sustainable only if book quality is genuinely clean — not deferred provisioning."
                ),
                "signal": "INFO",
            },
        ],
        "early_warnings": [
            {"metric":"roe","label":"Return on Equity %","threshold_warn":14,"threshold_crit":11,
             "calibration":"Top-tier: 15-20%. Below 14% = NIM or credit cost pressure.",
             "lower_is_worse":True},
            {"metric":"debt_equity","label":"Debt / Equity","threshold_warn":10,"threshold_crit":14,
             "calibration":"Banks normal 7-9x. Above 10x = aggressive lending. Above 12x = regulatory watch."},
        ],
        "scenarios": {
            "base":        {"label":"Credit cycle stable","probability":0.55,"rev_cagr_mult":1.00,"margin_delta":0,"pe_exit":3.2},
            "disruption":  {"label":"NPA cycle turns","probability":0.25,"rev_cagr_mult":0.70,"margin_delta":-2,"pe_exit":1.8,
                            "trigger":"Net slippage >1.5% for 2 quarters. GNPA rising in SME/unsecured."},
            "acceleration":{"label":"Credit re-rating","probability":0.20,"rev_cagr_mult":1.20,"margin_delta":0.5,"pe_exit":4.0,
                            "trigger":"ROE >18% sustained. CASA ratio rising YoY."},
        },
        "break_point": (
            "Net slippage above 1.5% for 2 consecutive quarters = credit cycle turned. "
            "Happened FY2016-18 (PSB stress spilled to private banks) and FY2020 (COVID). "
            "Provision coverage and CET-1 capital adequacy determine severity. "
            ">75% PCR and >16% CET-1: survives. Others: equity dilution."
        ),
        "hidden_alpha": (
            "CASA trend over 5 years predicts NIM 2-4 quarters ahead. "
            "HDFC Bank CASA fell 47%→38% post-merger — visible 6 quarters before NIM hit. "
            "Most analysts track current NIM. The right signal is CASA trajectory."
        ),
    },

    "fmcg": {
        "peers":       ["HINDUNILVR","NESTLEIND","DABUR","MARICO"],
        "peer_names":  ["HUL","Nestle India","Dabur","Marico"],
        "normal_roce": (30,55), "normal_margin": (18,28),
        "key_metrics": ["roce","ebitda_margin","nwc_days","rev_cagr_5y"],
        "value_driver": (
            "Volume growth in premium tier drives BOTH revenue and margin simultaneously. "
            "Value growth alone is inflation — revenues rise, quality does not. "
            "3% volume growth = brand health minimum. Below 3% for 2 years = structural problem."
        ),
        "causal_rules": [
            {
                "name": "premium_mix_margin_expansion",
                "condition": lambda m: (m.get("pat_cagr_3y") or 0)>(m.get("rev_cagr_3y") or 0)+3,
                "insight": lambda m: (
                    f"PAT CAGR {m.get('pat_cagr_3y',0):.1f}% >> Revenue CAGR {m.get('rev_cagr_3y',0):.1f}%. "
                    "Premiumisation working — consumers upgrading from mass (15-18% margin) "
                    "to premium (25-30% margin). Durable if volume-led. Cyclical if input-cost tailwind."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "pricing_led_growth_risk",
                "condition": lambda m: (
                    (m.get("rev_cagr_3y") or 0)>10 and
                    len(m.get("margin_hist",[]))>=3 and
                    (m.get("ebitda_margin") or 0)<(sum(m.get("margin_hist",[0,0,0])[:3])/3)-1
                ),
                "insight": lambda m: (
                    f"Revenue {m.get('rev_cagr_3y',0):.1f}% CAGR but margins declining. "
                    "Price-led growth without volume — reverses when inflation normalises. "
                    "Sustainable FMCG growth = volume up + margin up simultaneously."
                ),
                "signal": "WARNING",
            },
            {
                "name": "rural_stress_indicator",
                "condition": lambda m: (m.get("rev_cagr_3y") or 0)<7 and (m.get("ebitda_margin") or 0)>20,
                "insight": lambda m: (
                    f"Revenue CAGR {m.get('rev_cagr_3y',0):.1f}% but margin {m.get('ebitda_margin',0):.1f}% high. "
                    "Company protecting margins by reducing A&P — harvesting brand. "
                    "FY2019-20: rural slowdown hit mass FMCG. FY2019-21 HUL: cut A&P 12%→9%, "
                    "expanded margins. FY2022-24: rebuilt A&P to 11%, volumes recovered."
                ),
                "signal": "WARNING",
            },
            {
                "name": "fmcg_working_capital_strength",
                "condition": lambda m: (m.get("nwc_days") or 0)<-20,
                "insight": lambda m: (
                    f"Negative NWC {m.get('nwc_days',0):.0f}d = distributors funding operations. "
                    "HUL NWC: -30 to -45 days consistently. "
                    "Weakening toward 0 = brand losing channel power. Watch trend, not level."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "ad_spend_harvesting",
                "condition": lambda m: (m.get("ebitda_margin") or 0)>25 and (m.get("rev_cagr_3y") or 0)<8,
                "insight": lambda m: (
                    "High margin + slow growth = brand harvesting. "
                    "A&P cut to protect margins. Bullish short-term, bearish year 4-6 as brand equity depletes. "
                    "Check A&P as % of revenue trend in annual report."
                ),
                "signal": "INFO",
            },
        ],
        "early_warnings": [
            {"metric":"ebitda_margin","label":"EBITDA Margin %","threshold_warn":18,"threshold_crit":14,
             "calibration":"HUL normal 22-26%. Marico 18-22%. Below 18% = raw material crisis.",
             "lower_is_worse":True},
            {"metric":"rev_cagr_3y","label":"Revenue CAGR 3Y %","threshold_warn":7,"threshold_crit":4,
             "calibration":"Normal 8-14%. Below 7% = volume stagnation.",
             "lower_is_worse":True},
        ],
        "scenarios": {
            "base":        {"label":"Premiumisation steady","probability":0.55,"rev_cagr_mult":1.00,"margin_delta":0,"pe_exit":52},
            "disruption":  {"label":"D2C + q-commerce disruption","probability":0.20,"rev_cagr_mult":0.60,"margin_delta":-3,"pe_exit":32,
                            "trigger":"Volume growth <3% for 2 years. Quick commerce private labels gaining."},
            "acceleration":{"label":"Rural recovery + premiumisation","probability":0.25,"rev_cagr_mult":1.25,"margin_delta":2,"pe_exit":62,
                            "trigger":"Rural volume growth > urban 2 consecutive quarters."},
        },
        "break_point": (
            "Volume growth below 3% for 2 consecutive years (not 1 — that is rural cycle). "
            "Two years = structural. De-rates from 50-55x → 30-35x P/E. "
            "Structural signal: modern trade AND e-commerce ALSO slowing, not just general trade."
        ),
        "hidden_alpha": (
            "A&P spend % of revenue is a leading indicator of brand health — "
            "visible in annual report disclosure. Falling A&P + stable volumes = "
            "harvesting (bullish 2Y, bearish 5Y). Rising A&P + volume recovery = "
            "buy the dip signal."
        ),
    },

    "cement": {
        "peers":       ["ULTRACEMCO","SHREECEM","AMBUJACEM","ACC"],
        "peer_names":  ["UltraTech","Shree Cement","Ambuja","ACC"],
        "normal_roce": (10,22), "normal_margin": (18,28),
        "key_metrics": ["roce","ebitda_margin","net_debt_ebitda","rev_cagr_5y"],
        "value_driver": (
            "EBITDA per tonne is the only metric. Revenue conflates volume, price, and mix. "
            "EBITDA/tonne reveals: cost efficiency, pricing power, and down-cycle survival ability. "
            "Shree Cement ₹1,400+/tonne vs industry ₹900-1,000 = 30-35% structural cost advantage."
        ),
        "causal_rules": [
            {
                "name": "volume_growth_infrastructure",
                "condition": lambda m: (m.get("rev_cagr_3y") or 0)>12,
                "insight": lambda m: (
                    f"Revenue CAGR {m.get('rev_cagr_3y',0):.1f}% — strong for cement. "
                    "Verify: industry grew 8-9% → company at 12% = share gain (company-specific). "
                    "Industry grew 12% → company at 12% = macro tailwind, not alpha."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "leverage_downcycle_risk",
                "condition": lambda m: (m.get("net_debt_ebitda") or 0)>2.5,
                "insight": lambda m: (
                    f"Net Debt/EBITDA {m.get('net_debt_ebitda',0):.1f}x — elevated. "
                    "FY2016-17 oversupply: industry EBITDA/tonne fell 30%. Companies at 3x+ faced stress. "
                    "Shree Cement maintained 0-0.5x through cycle — structural survival advantage."
                ),
                "signal": "WARNING",
            },
            {
                "name": "capex_cycle_capacity",
                "condition": lambda m: (m.get("cwip_pct") or 0)>20 and (m.get("roce") or 0)<15,
                "insight": lambda m: (
                    f"CWIP {m.get('cwip_pct',0):.0f}% of gross block, ROCE {m.get('roce',0):.1f}%. "
                    "Heavy capacity addition. ROCE will compress further before recovering. "
                    "Key: capacity into deficit regions (South, East) recovers in 2 years. "
                    "Into surplus markets (North, West): 4-5 years."
                ),
                "signal": "INFO",
            },
            {
                "name": "energy_cost_sensitivity",
                "condition": lambda m: (
                    len(m.get("margin_hist",[]))>=3 and
                    abs((m.get("ebitda_margin") or 0)-sum(m.get("margin_hist",[0,0,0])[:3])/3)>4
                ),
                "insight": lambda m: (
                    f"Margin {m.get('ebitda_margin',0):.1f}% — large shift from 3Y avg. "
                    "Cement margin moves are almost always energy-driven (coal+petcoke = 35-40% cost). "
                    "If energy down: margin expansion sustainable 2-3 quarters. "
                    "If energy up: margin compression until pass-through or cost cuts."
                ),
                "signal": "INFO",
            },
            {
                "name": "utilisation_pricing_power",
                "condition": lambda m: (m.get("rev_cagr_5y") or 0)>10 and (m.get("ebitda_margin") or 0)>22,
                "insight": lambda m: (
                    f"Strong growth {m.get('rev_cagr_5y',0):.1f}% with high margin {m.get('ebitda_margin',0):.1f}% — "
                    "industry at high utilisation (>80%). "
                    "Pricing power rule: below 70% utilisation = no pricing power. "
                    "70-80% = neutral. Above 80% = pricing power exists."
                ),
                "signal": "STRENGTH",
            },
        ],
        "early_warnings": [
            {"metric":"net_debt_ebitda","label":"Net Debt/EBITDA","threshold_warn":2.5,"threshold_crit":4.0,
             "calibration":"UltraTech pre-capex: 1.5-2x. Shree: 0-0.5x. Above 2.5x = downcycle risk."},
            {"metric":"ebitda_margin","label":"EBITDA Margin %","threshold_warn":15,"threshold_crit":11,
             "calibration":"Normal 18-25%. Coal spike FY2021: fell to 12-14%. Below 15% = crisis.",
             "lower_is_worse":True},
            {"metric":"roce","label":"ROCE %","threshold_warn":10,"threshold_crit":7,
             "calibration":"Normal 12-22%. Below 10% = overcapacity or peak capex.",
             "lower_is_worse":True},
        ],
        "scenarios": {
            "base":        {"label":"Infrastructure demand holds","probability":0.55,"rev_cagr_mult":1.00,"margin_delta":0,"pe_exit":18},
            "disruption":  {"label":"Capacity glut compresses price","probability":0.30,"rev_cagr_mult":0.65,"margin_delta":-6,"pe_exit":10,
                            "trigger":"Industry utilisation <70% for 2 years. Additions >50MT in one year."},
            "acceleration":{"label":"Infra supercycle","probability":0.15,"rev_cagr_mult":1.40,"margin_delta":3,"pe_exit":24,
                            "trigger":"PM Gati Shakti absorbing 15% of annual cement demand."},
        },
        "break_point": (
            "Industry utilisation below 70% for 2 consecutive years. "
            "Rational pricing breaks down — marginal producers cut to fill capacity. "
            "Signal: monthly CMA dispatch data. 3+ consecutive months of decline = watch."
        ),
        "hidden_alpha": (
            "Quarry proximity to demand center is the only permanent advantage. "
            "Freight = 10-15% of cost. Shree Cement's Rajasthan quarries (low freight North India) "
            "= ₹100-150/tonne structural advantage no efficiency initiative can replicate."
        ),
    },

    "pharma": {
        "peers":       ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB"],
        "peer_names":  ["Sun Pharma","Dr Reddy's","Cipla","Divi's"],
        "normal_roce": (15,30), "normal_margin": (20,35),
        "key_metrics": ["ebitda_margin","roce","cfo_to_pat","rev_cagr_5y"],
        "value_driver": (
            "Three-segment model: Domestic branded (stability) + US generics (growth, but 5-10% annual erosion) "
            "+ Specialty (premium). US generics requires ANDA filing rate > price erosion rate to be sustainable. "
            "Most analysts look at revenue. The right signal is the ANDA filing pipeline."
        ),
        "causal_rules": [
            {
                "name": "us_generics_erosion",
                "condition": lambda m: (m.get("rev_cagr_3y") or 0)<(m.get("rev_cagr_5y") or 0)*0.65,
                "insight": lambda m: (
                    f"Revenue deceleration: 3Y {m.get('rev_cagr_3y',0):.1f}% vs 5Y {m.get('rev_cagr_5y',0):.1f}%. "
                    "US generics price erosion exceeding new launches. "
                    "FY2016-19: US erosion hit 15-20%/year — defined the period of pharma underperformance. "
                    "Sustainable US revenue = ANDA filing rate > erosion rate."
                ),
                "signal": "WARNING",
            },
            {
                "name": "high_margin_specialty",
                "condition": lambda m: (m.get("ebitda_margin") or 0)>28,
                "insight": lambda m: (
                    f"EBITDA {m.get('ebitda_margin',0):.1f}% — top tier pharma margin. "
                    "Requires specialty franchise (dermatology, ophthalmology, oncology) or "
                    "dominant API position (Divi's) or exceptional domestic branded portfolio. "
                    "FDA risk is the tail risk: one import alert = 30-40% US revenue cut overnight."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "r_and_d_investment",
                "condition": lambda m: (m.get("capex") or 0)>(m.get("revenue") or 1)*0.08,
                "insight": lambda m: (
                    f"Capex {((m.get('capex',0)/m.get('revenue',1))*100):.1f}% of revenue — "
                    "high investment. For pharma includes R&D + manufacturing capacity. "
                    "Quality of pipeline determines payoff: specialty vs commodity generics."
                ),
                "signal": "INFO",
            },
            {
                "name": "cfo_quality_signal",
                "condition": lambda m: (m.get("cfo_to_pat") or 0)>1.05,
                "insight": lambda m: (
                    f"CFO/PAT {m.get('cfo_to_pat',0):.2f} — strong cash conversion despite "
                    "export credit receivables. No aggressive revenue recognition. "
                    "Pharma with high export receivables often shows CFO/PAT 0.7-0.9. "
                    "Above 1.0 = working capital discipline."
                ),
                "signal": "STRENGTH",
            },
        ],
        "early_warnings": [
            {"metric":"ebitda_margin","label":"EBITDA Margin %","threshold_warn":18,"threshold_crit":14,
             "calibration":"Sun/Cipla normal 22-30%. Divi's 28-35%. Below 18% = US price erosion crisis.",
             "lower_is_worse":True},
            {"metric":"rev_cagr_3y","label":"Revenue CAGR 3Y %","threshold_warn":8,"threshold_crit":4,
             "calibration":"Normal 10-18%. Below 8% = US headwinds exceed domestic growth.",
             "lower_is_worse":True},
        ],
        "scenarios": {
            "base":        {"label":"Steady generic + domestic","probability":0.55,"rev_cagr_mult":1.00,"margin_delta":0,"pe_exit":28},
            "disruption":  {"label":"FDA action + price war","probability":0.20,"rev_cagr_mult":0.60,"margin_delta":-6,"pe_exit":16,
                            "trigger":"Import alert on key plant. US revenue cut 30%. Remediation 12-18 months."},
            "acceleration":{"label":"Specialty approval","probability":0.25,"rev_cagr_mult":1.30,"margin_delta":4,"pe_exit":40,
                            "trigger":"Key specialty ANDA approved in high-barrier US market."},
        },
        "break_point": (
            "FDA import alert on primary US manufacturing facility. Binary — not gradual. "
            "Revenue impact: 25-40% cut within one quarter. Remediation: 12-24 months. "
            "Signal: USFDA inspection database OAI vs VAI classification (publicly available)."
        ),
        "hidden_alpha": (
            "ANDA filing rate minus price erosion rate = sustainable US growth. "
            "If 30 ANDAs/year at 8% erosion, each ANDA needs ~0.3% revenue contribution. "
            "Most analysts look at revenue. The right signal is filing pipeline quality."
        ),
    },

    "auto_oem": {
        "peers":       ["MARUTI","M&M","BAJAJ-AUTO","TATAMOTORS"],
        "peer_names":  ["Maruti Suzuki","M&M","Bajaj Auto","Tata Motors"],
        "normal_roce": (12,22), "normal_margin": (10,18),
        "key_metrics": ["roce","ebitda_margin","rev_cagr_5y","debt_equity"],
        "value_driver": (
            "Market share in the fastest-growing segment determines whether you compound or decline. "
            "Leader in a declining segment (Maruti in hatchbacks) is a trap. "
            "Leader in a growing segment (M&M in SUVs) is compounding. "
            "Monthly wholesale vs retail divergence is the earliest demand signal."
        ),
        "causal_rules": [
            {
                "name": "ev_transition_capex",
                "condition": lambda m: (m.get("cwip_pct") or 0)>15 and m.get("roce_trend")=="DECLINING",
                "insight": lambda m: (
                    f"CWIP {m.get('cwip_pct',0):.0f}% of gross block — EV platform investment. "
                    "Tata Motors EV: ₹15,000Cr over 5 years. ROCE compresses during transition. "
                    "Question: is the EV portfolio gaining market share or just burning capital? "
                    "Tata Motors: EV share in PV market from 0% to 12% in 3 years = compounding."
                ),
                "signal": "INFO",
            },
            {
                "name": "inventory_cycle_signal",
                "condition": lambda m: (m.get("inventory_days") or 0)>40,
                "insight": lambda m: (
                    f"Inventory {m.get('inventory_days',0):.0f}d — elevated (normal 25-35d). "
                    "Wholesale > retail = dealer channel filling above demand. "
                    "Maruti: channel >30d → production cuts within 2 quarters historically. "
                    "Check Vahan retail registration data to confirm."
                ),
                "signal": "WARNING",
            },
            {
                "name": "margin_cycle_recovery",
                "condition": lambda m: (
                    len(m.get("margin_hist",[]))>=3 and
                    (m.get("ebitda_margin") or 0)>(sum(m.get("margin_hist",[0,0,0])[1:4])/3)+2
                ),
                "insight": lambda m: (
                    f"Margin {m.get('ebitda_margin',0):.1f}% — above 3Y avg. "
                    "Auto margin expansion from: (1) steel/aluminium tailwind — check commodity, "
                    "(2) utilisation above 80% — operating leverage, "
                    "(3) mix shift to SUVs/premium. Identify driver before assuming durability."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "roce_segment_mismatch",
                "condition": lambda m: (m.get("roce") or 0)<12,
                "insight": lambda m: (
                    f"ROCE {m.get('roce',0):.1f}% — below cost of capital. "
                    "Either heavy EV capex phase or CV in downcycle. "
                    "Maruti FY2023-24: 15-17%. M&M: 14-18%. Below 12% = capital allocation question."
                ),
                "signal": "WARNING",
            },
        ],
        "early_warnings": [
            {"metric":"ebitda_margin","label":"EBITDA Margin %","threshold_warn":10,"threshold_crit":7,
             "calibration":"Maruti normal 10-14%. M&M 12-16%. Below 10% = commodity spike or crash.",
             "lower_is_worse":True},
            {"metric":"inventory_days","label":"Inventory Days","threshold_warn":40,"threshold_crit":55,
             "calibration":"Normal 25-35d. FY2019 slowdown: 48-52d before production cuts."},
            {"metric":"net_debt_ebitda","label":"Net Debt/EBITDA","threshold_warn":2.0,"threshold_crit":3.5,
             "calibration":"Auto OEMs should be near net cash. Above 2x = EV capex overhang concern."},
        ],
        "scenarios": {
            "base":        {"label":"Steady market","probability":0.55,"rev_cagr_mult":1.00,"margin_delta":0,"pe_exit":20},
            "disruption":  {"label":"EV price war","probability":0.25,"rev_cagr_mult":0.65,"margin_delta":-4,"pe_exit":12,
                            "trigger":"Chinese OEMs enter India. BEV >10% PV market. ICE derating."},
            "acceleration":{"label":"EV dominance","probability":0.20,"rev_cagr_mult":1.30,"margin_delta":2,"pe_exit":28,
                            "trigger":"Company EV share >25% BEV market. Battery cost <$90/kWh."},
        },
        "break_point": (
            "BEV penetration crosses 8% of PV market for 2 consecutive years. "
            "ICE-heavy portfolios face structural derating. "
            "Current BEV share ~2.5%. Pace of change determines urgency. "
            "Maruti: most exposed. Tata Motors: best positioned."
        ),
        "hidden_alpha": (
            "Monthly wholesale (SIAM dispatches) vs retail (Vahan registrations) divergence. "
            "Wholesale > retail for 3+ months = dealer inventory building = demand softer than reported. "
            "This data is freely available and leads stock price by 1-2 quarters."
        ),
    },

    "nbfc": {
        "peers":       ["BAJFINANCE","CHOLAFIN","MUTHOOTFIN","SHRIRAMFIN"],
        "peer_names":  ["Bajaj Finance","Chola Finance","Muthoot Finance","Shriram Finance"],
        "normal_roce": (8,15), "normal_margin": (None,None),
        "key_metrics": ["roe","debt_equity","pat_cagr_3y"],
        "value_driver": (
            "Spread × AUM growth = revenue. Credit cost is the destroyer. "
            "1% credit cost spike at 5x leverage = 5% ROE hit in one quarter. "
            "The NBFCs that survived IL&FS (Sep 2018) and COVID (FY2020) intact have "
            "structural risk management advantage — only visible through a downcycle."
        ),
        "causal_rules": [
            {
                "name": "roe_above_sector",
                "condition": lambda m: (m.get("roe") or 0)>18,
                "insight": lambda m: (
                    f"ROE {m.get('roe',0):.1f}% — exceptional for NBFC. "
                    "Requires: high NIM (specialty yields) + low credit costs + moderate leverage. "
                    "Bajaj Finance: sustained 18-22% ROE through cycles. "
                    "Sustainable only with strong underwriting — credit costs are the critical variable."
                ),
                "signal": "STRENGTH",
            },
            {
                "name": "leverage_credit_risk",
                "condition": lambda m: (m.get("debt_equity") or 0)>6,
                "insight": lambda m: (
                    f"D/E {m.get('debt_equity',0):.1f}x — normal for NBFC but high leverage = "
                    "small credit quality deterioration magnified. "
                    "IL&FS Sep 2018: CP market froze. NBFCs at 8-9x leverage faced liquidity crisis. "
                    "Watch CP as % of total borrowings — high CP = rollover risk."
                ),
                "signal": "INFO",
            },
            {
                "name": "pat_growth_acceleration",
                "condition": lambda m: (m.get("pat_cagr_3y") or 0)>25,
                "insight": lambda m: (
                    f"PAT CAGR {m.get('pat_cagr_3y',0):.1f}% — rapid. "
                    "NBFC PAT compounds 25-35% in upcycles, then provisions surge 40-60% in one year. "
                    "COVID FY2020: most NBFCs' PAT fell 40-60% from provision surge. "
                    "Question: how much of current growth is being provisioned as it accumulates?"
                ),
                "signal": "INFO",
            },
            {
                "name": "cfo_pat_lending_nature",
                "condition": lambda m: (m.get("cfo_to_pat") or 1.0)<0.5,
                "insight": lambda m: (
                    f"CFO/PAT {m.get('cfo_to_pat',0):.2f} — low, but EXPECTED for NBFC. "
                    "Cash out = loan disbursement. Low CFO/PAT = AUM growing. Feature, not bug. "
                    "Monitor AUM growth rate and credit quality, not CFO/PAT."
                ),
                "signal": "NORMAL",
            },
        ],
        "early_warnings": [
            {"metric":"roe","label":"Return on Equity %","threshold_warn":14,"threshold_crit":10,
             "calibration":"Bajaj Finance normal 18-22%. Below 14% = credit cost or NIM pressure.",
             "lower_is_worse":True},
            {"metric":"debt_equity","label":"Debt / Equity","threshold_warn":7,"threshold_crit":10,
             "calibration":"NBFCs normal 4-7x. Above 7x = aggressive growth. Above 10x = regulatory watch."},
        ],
        "scenarios": {
            "base":        {"label":"AUM growth steady","probability":0.55,"rev_cagr_mult":1.00,"margin_delta":0,"pe_exit":30},
            "disruption":  {"label":"Credit cycle stress","probability":0.25,"rev_cagr_mult":0.60,"margin_delta":-4,"pe_exit":14,
                            "trigger":"Unsecured GNPA >3% two quarters. RBI tightening risk weights further."},
            "acceleration":{"label":"Consolidation beneficiary","probability":0.20,"rev_cagr_mult":1.35,"margin_delta":2,"pe_exit":42,
                            "trigger":"Weak NBFCs exit. Strong ones gain AUM share at lower CAC."},
        },
        "break_point": (
            "30-90 day DPD bucket rising 2 consecutive quarters = 90+ day NPA is 6-9 months away. "
            "This is the LEADING indicator. Most analysts watch GNPA (lagging). "
            "RBI risk weight tightening (done Nov 2023) + rising credit costs = "
            "ROE compression + multiple de-rating from 30-35x to 18-20x."
        ),
        "hidden_alpha": (
            "CP market spread over G-Sec is a real-time NBFC stress indicator. "
            "Normal: 50-80bps. IL&FS crisis Sep 2018: spiked 300bps. "
            "Above 150bps = NBFC liquidity stress beginning. "
            "This data is available daily from NSE/CCIL — most analysts check quarterly results."
        ),
    },

    "diversified": {
        "peers":[], "peer_names":[],
        "normal_roce": (8,15), "normal_margin": (10,20),
        "key_metrics": ["roce","ebitda_margin","net_debt_ebitda","cfo_to_pat"],
        "value_driver": "Sum-of-parts. Each segment valued independently. Conglomerate discount narrows on demerger.",
        "causal_rules": [],
        "early_warnings": [],
        "scenarios": {
            "base":        {"label":"Hold","probability":0.60,"rev_cagr_mult":1.0,"margin_delta":0,"pe_exit":20},
            "disruption":  {"label":"Capital misallocation","probability":0.20,"rev_cagr_mult":0.75,"margin_delta":-3,"pe_exit":12},
            "acceleration":{"label":"Demerger unlocks value","probability":0.20,"rev_cagr_mult":1.1,"margin_delta":2,"pe_exit":28},
        },
        "break_point": "Management allocates FCF from high-ROCE to low-ROCE businesses. Watch capital deployment annually.",
        "hidden_alpha": "Segment ROCE variance hides where value is created and destroyed. Blended ROCE is misleading.",
    },
}


def get_profile(sector: str) -> dict:
    """Return sector profile for the given sector key (falls back to 'diversified')."""
    return SECTOR_PROFILES.get(sector, SECTOR_PROFILES["diversified"])

# ============================================================================
# DATA FETCHERS
# ============================================================================

def fetch_pdf(bse_code, fy_year):
    """
    Fetch annual report PDF. Tries 3 sources in order — each with
    independent infra so different failure modes don't stack:
      1. BSE India API  — primary, fastest
      2. NSE EDGAR      — different exchange, different CDN
      3. BSE IR scan    — last resort scrape of company IR page
    Returns bytes on success, None if all three exhausted.
    Analysis continues without PDF — qualitative section notes the gap.
    """
    _log.info(f"fetch_pdf: {bse_code} FY{fy_year} — trying BSE")
    pdf = _fetch_pdf_bse(bse_code, fy_year)
    if pdf:
        return pdf
    _log.info(f"fetch_pdf: BSE failed — trying NSE EDGAR")
    pdf = _fetch_pdf_nse(bse_code, fy_year)
    if pdf:
        return pdf
    _log.info(f"fetch_pdf: NSE failed — trying IR page scan")
    pdf = _fetch_pdf_ir_scan(bse_code, fy_year)
    if pdf:
        return pdf
    _log.warning(f"fetch_pdf: all sources exhausted for {bse_code} FY{fy_year} — proceeding quant-only")
    return None


def _fetch_pdf_bse(bse_code, fy_year):
    """Source 1: BSE India annual report API."""
    HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/", "Accept": "application/json"}
    sess = requests.Session()
    sess.headers.update(HEADERS)
    try:
        sess.get("https://www.bseindia.com", timeout=10)
        time.sleep(0.5)
    except Exception:
        _log.debug("BSE warm-up failed", exc_info=True)
    try:
        r = sess.get(
            "https://api.bseindia.com/BseIndiaAPI/api/AnnualReport/w",
            params={"scripcode": bse_code, "pageno": "1", "strtype": "C"},
            timeout=15,
        )
        files = r.json().get("Table", []) if r.status_code == 200 else []
        matched = None
        for target in [str(fy_year), str(fy_year - 1)]:
            for f in files:
                if str(f.get("year", "")) == target:
                    matched = f
                    break
            if matched:
                break
        if not matched:
            return None
        fn = matched.get("file_name", "").strip()
        if fn.lower().endswith(".pdf.pdf"):
            fn = fn[:-4]
        for base in [
            "https://www.bseindia.com/xml-data/corpfiling/AttachLive/",
            "https://www.bseindia.com/xml-data/corpfiling/AttachHis/",
        ]:
            try:
                pdf_r = sess.get(base + fn, timeout=120, stream=True)
                if pdf_r.status_code == 200 and len(pdf_r.content) > 50_000:
                    _log.info(f"_fetch_pdf_bse: ✓ {len(pdf_r.content)/1_048_576:.1f} MB")
                    return pdf_r.content
            except Exception:
                continue
    except Exception as e:
        _log.info(f"_fetch_pdf_bse: {e}")
    return None


def _fetch_pdf_nse(bse_code, fy_year):
    """Source 2: NSE EDGAR corporate filings."""
    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        try:
            sess.get("https://www.nseindia.com", timeout=10,
                     headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
            time.sleep(1)
        except Exception:
            pass
        r = sess.get(f"https://www.nseindia.com/api/search-autocomplete?q={bse_code}", timeout=10)
        if r.status_code != 200:
            return None
        symbols = [i.get("symbol") for i in r.json().get("symbols", [])[:3] if i.get("symbol")]
        if not symbols:
            return None
        r2 = sess.get(
            f"https://www.nseindia.com/api/annual-reports?index=equities&symbol={symbols[0]}",
            timeout=15,
        )
        if r2.status_code != 200:
            return None
        for filing in r2.json().get("data", [])[:10]:
            year_str = str(filing.get("year", ""))
            if str(fy_year) in year_str or str(fy_year - 1) in year_str:
                pdf_url = filing.get("fileName", "")
                if pdf_url:
                    try:
                        pdf_r = sess.get(pdf_url, timeout=120, stream=True)
                        if pdf_r.status_code == 200 and len(pdf_r.content) > 50_000:
                            _log.info(f"_fetch_pdf_nse: ✓ {len(pdf_r.content)/1_048_576:.1f} MB")
                            return pdf_r.content
                    except Exception:
                        continue
    except Exception as e:
        _log.info(f"_fetch_pdf_nse: {e}")
    return None


def _fetch_pdf_ir_scan(bse_code, fy_year):
    """Source 3: Scrape BSE company page for PDF links."""
    try:
        import re as _re
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0"})
        r = sess.get(f"https://www.bseindia.com/bseplus/AnnualReport/{bse_code}/", timeout=15)
        if r.status_code == 200:
            links = _re.findall(r'href=["\']([^"\']+\.pdf)["\']', r.text, _re.IGNORECASE)
            for link in links[:5]:
                if str(fy_year) in link or str(fy_year - 1) in link:
                    full = link if link.startswith("http") else f"https://www.bseindia.com{link}"
                    try:
                        pdf_r = sess.get(full, timeout=60, stream=True)
                        if pdf_r.status_code == 200 and len(pdf_r.content) > 50_000:
                            _log.info(f"_fetch_pdf_ir_scan: ✓ {len(pdf_r.content)/1_048_576:.1f} MB")
                            return pdf_r.content
                    except Exception:
                        continue
    except Exception as e:
        _log.info(f"_fetch_pdf_ir_scan: {e}")
    return None





class Screener:
    BASE    = "https://www.screener.in"
    HEADERS = {"User-Agent":"Mozilla/5.0","Accept":"text/html","Referer":"https://www.screener.in/"}

    @staticmethod
    def fetch(symbol):
        result = {"available":False,"symbol":symbol,"pnl":{},"balance":{},"cashflow":{},"ratios":{},"years":[],"stock_info":{}}
        for url in [f"{Screener.BASE}/company/{symbol}/consolidated/",f"{Screener.BASE}/company/{symbol}/"]:
            try:
                sess = requests.Session(); sess.headers.update(Screener.HEADERS)
                r = sess.get(url, timeout=20)
                if r.status_code!=200: continue
                soup = BeautifulSoup(r.text,"lxml"); result["available"]=True
                for sid,key in [("profit-loss","pnl"),("balance-sheet","balance"),("cash-flow","cashflow"),("ratios","ratios")]:
                    sec=soup.find("section",{"id":sid})
                    if not sec: continue
                    tbl=sec.find("table")
                    if not tbl: continue
                    p=Screener._parse(tbl)
                    if p:
                        result[key]=p["data"]
                        if not result["years"] and p["years"]: result["years"]=p["years"]
                for sel in ["#top-ratios",".company-ratios"]:
                    info=soup.select_one(sel)
                    if info:
                        for li in info.find_all("li"):
                            spans=li.find_all("span")
                            if len(spans)>=2:
                                name=spans[0].get_text(strip=True)
                                val=spans[-1].get_text(strip=True)
                                try: result["stock_info"][name]=float(val.replace("₹","").replace(",","").replace("Cr.","").replace("%","").strip())
                                except: result["stock_info"][name]=val
                        break
                if result["years"]: return result
            except Exception as e:
                result["error"] = str(e)
                _log.error(
                    f"🚨 Screener.fetch BROKEN for {symbol} — HTML structure may have changed "
                    f"or site is blocking requests. URL: {url} | Error: {e}",
                    exc_info=True
                )
        if not result.get("years"):
            _log.error(
                f"🚨 Screener.fetch returned NO DATA for {symbol} — "
                f"both consolidated and standalone URLs failed. Equity brief will be degraded."
            )
        return result

    @staticmethod
    def _parse(table):
        rows=table.find_all("tr")
        if not rows: return None
        years,data=[],{}
        for i,row in enumerate(rows):
            cells=row.find_all(["th","td"])
            if not cells: continue
            texts=[c.get_text(strip=True) for c in cells]
            if not texts: continue
            if i==0 or (not years and any(re.match(r"(Mar|TTM|Sep|Dec|Jun)\s*\d{0,4}",t) for t in texts[1:])):
                years=texts[1:]; continue
            label=texts[0].strip().rstrip("+").strip()
            if not label: continue
            vals=[]
            for t in texts[1:]:
                s=t.replace(",","").replace("%","").strip()
                try: vals.append(float(s))
                except: vals.append(None)
            if label and vals:
                n=len(years); padded=(vals+[None]*n)[:n]
                data[label]=list(reversed(padded))
        return {"years":list(reversed(years)),"data":data} if years else None

    @staticmethod
    def val(data, labels, idx=0):
        d={**data.get("pnl",{}),**data.get("balance",{}),**data.get("cashflow",{}),**data.get("ratios",{})}
        for lbl in labels:
            for key in d:
                if lbl.lower() in key.lower():
                    arr=[x for x in d[key] if x is not None]
                    return arr[idx] if len(arr)>idx else None
        return None

    @staticmethod
    def fetch_search(query, top=12):
        """Search companies via Screener.in API. Returns list of dicts with bse_code etc."""
        try:
            import requests as _req
            r = _req.get(
                f"https://www.screener.in/api/company/search/?q={query}&v=3&fts=1",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            data = r.json()
            items = data if isinstance(data, list) else data.get("results", [])
            results = []
            for item in items[:top]:
                if not item.get("name"):
                    continue
                # Screener API returns "id" as BSE code (e.g. "500325")
                bse = str(item.get("bse_code") or item.get("id") or "")
                if not bse:
                    continue
                results.append({
                    "bse_code":     bse,
                    "nse_symbol":   item.get("symbol", ""),
                    "company_name": item.get("name", ""),
                    "sector":       item.get("industry", ""),
                    "screener_url": f"https://www.screener.in/company/{item.get('symbol','')}/",
                })
            _log.info(f"fetch_search: {len(results)} results for '{query}'")
            return results
        except Exception:
            _log.error(
                f"🚨 Screener.fetch_search BROKEN for '{query}' — "
                f"API endpoint may have changed. Check https://www.screener.in/api/company/search/",
                exc_info=True
            )
            return []

    @staticmethod
    def arr(data, labels):
        d={**data.get("pnl",{}),**data.get("balance",{}),**data.get("cashflow",{}),**data.get("ratios",{})}
        for lbl in labels:
            for key in d:
                if lbl.lower() in key.lower():
                    return [x for x in d[key] if x is not None]
        return []


def build_metrics(s):
    g=lambda labels,idx=0: Screener.val(s,labels,idx)
    a=lambda labels: Screener.arr(s,labels)
    si=s.get("stock_info",{})

    m={
        "revenue":     g(["Sales","Revenue"]),
        "ebitda":      g(["Operating Profit","EBITDA"]),
        "pat":         g(["Net Profit","PAT"]),
        "interest":    g(["Interest","Finance Costs"]),
        "depreciation":g(["Depreciation"]),
        "cfo":         g(["Cash from Operating Activity"]),
        "capex":       g(["Capital Expenditure","Capex"]),
        "borrowings":  g(["Borrowings"]),
        "cash":        g(["Cash Equivalents","Cash & Equivalents","Cash & Bank"]),
        "equity_cap":  g(["Equity Capital"]),
        "reserves":    g(["Reserves"]),
        "fixed_assets":g(["Fixed Assets","Net Fixed Assets"]),
        "cwip":        g(["CWIP","Capital Work in Progress"]),
        "roce":        g(["ROCE %","ROCE"]),
        "roe":         g(["ROE %","ROE"]),
        "receivable_days":g(["Debtor Days"]),
        "inventory_days": g(["Inventory Days"]),
        "payable_days":   g(["Days Payable","Payable Days"]),
        "eps":         g(["EPS in Rs","EPS"]),
        "rev_arr":     a(["Sales","Revenue"]),
        "pat_arr":     a(["Net Profit","PAT"]),
        "ebit_arr":    a(["Operating Profit","EBITDA"]),
        "roce_arr":    a(["ROCE %","ROCE"]),
        "cfo_arr":     a(["Cash from Operating Activity"]),
        "rd_arr":      a(["Debtor Days"]),
        "inv_arr":     a(["Inventory Days"]),
        "pay_arr":     a(["Days Payable","Payable Days"]),
    }

    # Stock info
    for k,labels in [("pe",["Stock P/E","P/E"]),("market_cap_cr",["Market Cap"]),
                     ("current_price",["Current Price"]),("book_value",["Book Value"])]:
        for lbl in labels:
            if lbl in si:
                try:
                    v=si[lbl]
                    if isinstance(v,str): v=float(v.replace("₹","").replace(",","").replace("Cr.","").replace("Cr","").strip())
                    m[k]=v; break
                except:

                    _log.debug("Suppressed exception", exc_info=True)

    # Derived
    eq=(m["equity_cap"] or 0)+(m["reserves"] or 0)
    m["total_equity"]=eq if eq>0 else None
    m["net_debt"]=(m["borrowings"] or 0)-(m["cash"] or 0)
    m["_net_cash"]=m["net_debt"]<0

    if m["ebitda"] and m["revenue"] and m["revenue"]>0:
        m["ebitda_margin"]=round(m["ebitda"]/m["revenue"]*100,1)
    if m["pat"] and m["revenue"] and m["revenue"]>0:
        m["pat_margin"]=round(m["pat"]/m["revenue"]*100,1)
    if m["cfo"] and m["pat"] and m["pat"]!=0:
        m["cfo_to_pat"]=round(m["cfo"]/m["pat"],2)
    if m["ebitda"] and m["interest"] and m["interest"]>0:
        m["interest_cov"]=round(m["ebitda"]/m["interest"],1)
    if m["net_debt"] and m["ebitda"] and m["ebitda"]!=0:
        m["net_debt_ebitda"]=round(m["net_debt"]/m["ebitda"],2)
    if m["total_equity"] and m["borrowings"] and m["total_equity"]>0:
        m["debt_equity"]=round(m["borrowings"]/m["total_equity"],2)
    if m["cfo"] and m["capex"]:
        m["fcf"]=round(m["cfo"]-abs(m["capex"]),0)

    # NWC
    rd=m.get("receivable_days") or 0; inv=m.get("inventory_days") or 0; pay=m.get("payable_days") or 0
    if rd or inv or pay:
        m["nwc_days"]=round(rd+inv-pay,1)
        nwc_hist=[]; rd_a=m["rd_arr"]; inv_a=m["inv_arr"]; pay_a=m["pay_arr"]
        n=min(len(rd_a),len(inv_a),len(pay_a))
        m["nwc_hist"]=[round(rd_a[i]+inv_a[i]-pay_a[i],1) for i in range(min(n,6)) if rd_a[i] is not None]

    # CWIP %
    fa=m.get("fixed_assets"); cwip=m.get("cwip")
    if fa and cwip and fa>0: m["cwip_pct"]=round(cwip/(fa+cwip)*100,1)

    # Margin history
    ra=m["rev_arr"]; ea=m["ebit_arr"]
    if ra and ea:
        n=min(len(ra),len(ea))
        m["margin_hist"]=[round(e/r*100,1) if r and r>0 and e is not None else None for r,e in zip(ra[:n],ea[:n])]

    # CAGRs
    def cagr(arr,yrs):
        v=[x for x in arr if x is not None and x>0]
        if len(v)>yrs: return round(((v[0]/v[yrs])**(1/yrs)-1)*100,1)
        return None
    m["rev_cagr_3y"]=cagr(m["rev_arr"],3); m["rev_cagr_5y"]=cagr(m["rev_arr"],5)
    m["rev_cagr_10y"]=cagr(m["rev_arr"],10)
    m["pat_cagr_3y"]=cagr(m["pat_arr"],3); m["pat_cagr_5y"]=cagr(m["pat_arr"],5)

    # Trend
    def trend(arr):
        v=[x for x in arr if x is not None]
        if len(v)<3: return "INSUFFICIENT_DATA"
        r=sum(v[:2])/2; o=sum(v[-2:])/2
        if o==0: return "INSUFFICIENT_DATA"
        c=(r-o)/abs(o)*100
        return "IMPROVING" if c>10 else "DECLINING" if c<-10 else "STABLE"

    m["roce_trend"]=trend(m["roce_arr"])
    m["rev_trend"]=trend(m["rev_arr"])
    m["margin_trend"]=trend(m.get("margin_hist",[]) or [])

    return m

# ============================================================================
# PATTERN RECOGNITION ENGINE — pure Python, no LLM
# ============================================================================

def run_pattern_recognition(m, profile):
    """
    Apply sector-specific causal rules to compute insights.
    This replaces LLM summaries of metrics with actual reasoning.
    """
    insights = []
    for rule in profile.get("causal_rules", []):
        try:
            if rule["condition"](m):
                insights.append({
                    "name":    rule["name"],
                    "insight": rule["insight"](m),
                    "signal":  rule.get("signal","INFO"),
                })
        except Exception:

            _log.warning("Suppressed exception", exc_info=True)
    return insights


def run_early_warnings(m, profile):
    """
    Check early warning thresholds.
    Returns list of warnings with current vs threshold.
    """
    warnings = []
    for ew in profile.get("early_warnings", []):
        metric  = ew["metric"]
        current = m.get(metric)
        if current is None: continue
        threshold_warn = ew.get("threshold_warn")
        threshold_crit = ew.get("threshold_critical")
        # For metrics where lower = worse (cfo_to_pat, roce)
        # For metrics where higher = worse (debt ratios, days)
        higher_is_worse = metric in ("inventory_days","receivable_days","payable_days",
                                      "net_debt_ebitda","debt_equity","incentive_spend_pct")
        if higher_is_worse:
            if threshold_crit and current >= threshold_crit:
                status = "CRITICAL"
            elif threshold_warn and current >= threshold_warn:
                status = "WARN"
            else:
                status = "OK"
        else:
            if threshold_crit and current <= threshold_crit:
                status = "CRITICAL"
            elif threshold_warn and current <= threshold_warn:
                status = "WARN"
            else:
                status = "OK"
        warnings.append({
            "label":     ew["label"],
            "current":   current,
            "threshold_warn": threshold_warn,
            "threshold_crit": threshold_crit,
            "status":    status,
            "interpretation": ew.get("interpretation", ew.get("calibration", "")),
        })
    return warnings


def compute_peer_spreads(m, peers, profile):
    spreads = {}
    for metric in profile.get("key_metrics", []):
        co_val = m.get(metric)
        peer_vals = [v[metric] for v in peers.values() if v.get(metric) is not None]
        if co_val is None or not peer_vals: continue
        peer_median = sorted(peer_vals)[len(peer_vals)//2]
        spread      = round(co_val - peer_median, 1)
        spreads[metric] = {
            "company":     co_val,
            "peer_median": round(peer_median, 1),
            "peer_best":   max(peer_vals) if metric not in ("nwc_days",) else min(peer_vals),
            "spread":      spread,
        }
    return spreads


def compute_dcf(m, sp):
    rev=m.get("revenue"); eq=m.get("total_equity")
    brr=m.get("borrowings") or 0; csh=m.get("cash") or 0
    cx=m.get("capex"); ie=m.get("interest"); em=m.get("ebitda_margin")
    if not rev or not eq or rev<=0 or eq<=0: return {"available":False}
    rfr=sp["risk_free_rate"]; erp=sp["equity_risk_premium"]; beta=sp["beta"]
    coe=rfr+beta*erp
    cod_pre=round(ie/brr*100,2) if ie and brr and brr>0 else sp["cost_of_debt_pretax"]
    tax=sp["tax_rate"]/100; cod_at=cod_pre*(1-tax)
    tc=eq+brr; we=eq/tc; wd=brr/tc; wacc=round(we*coe+wd*cod_at,2)
    c5=m.get("rev_cagr_5y"); c3=m.get("rev_cagr_3y"); c10=m.get("rev_cagr_10y")
    def pick(c5,c3,c10):
        for c,lbl in [(c5,"5Y"),(c3,"3Y"),(c10,"10Y")]:
            if c and c>2: return c,f"{lbl} CAGR {c:.1f}%"
        fb=max(c5 or 0,c3 or 0,c10 or 0,5.0)
        return fb,f"floor {fb:.1f}%"
    anchor,anchor_lbl=pick(c5,c3,c10); tg=sp["terminal_growth"]
    em_pct=em or 15; cp=abs(cx)/rev*100 if cx and rev else 5; da=3
    def make_gp(s,e,a):
        step=(e-s)/4
        return [max(round(a*(s+step*i)/100,1),1.0) for i in range(5)]
    base_g=make_gp(70,45,anchor); bull_g=make_gp(85,60,anchor); bear_g=make_gp(40,25,anchor)
    def _val(gp,md=0,ww=None,tt=None):
        w=ww or wacc; tg_=tt or tg; rv=rev; fcfs=[]
        am=em_pct+md
        for i,g in enumerate(gp):
            rv*=(1+g/100); nopat=(rv*am/100-rv*da/100)*(1-tax)
            fcf=nopat-rv*cp/100+rv*da/100-rv*0.005; fcfs.append(fcf/(1+w/100)**(i+1))
        fu=fcfs[-1]*(1+w/100)**5
        tv=fu*(1+tg_/100)/(w/100-tg_/100) if w/100>tg_/100 else 0
        return round(sum(fcfs)+tv/(1+w/100)**5+csh-brr,0)
    sens={}
    for wd_ in[-1,0,1]:
        row={}
        for td_ in[-1,0,1]:
            wt,tt=wacc+wd_,tg+td_
            if wt>tt: row[f"TG {tt:.1f}%"]=_val(base_g,0,wt,tt)
        sens[f"WACC {wacc+wd_:.1f}%"]=row
    return {"available":True,"bear_cr":_val(bear_g,-2),"base_cr":_val(base_g,0),"bull_cr":_val(bull_g,2),
            "wacc_pct":wacc,"cost_of_equity":round(coe,2),"cost_of_debt_pre":round(cod_pre,2),
            "cost_of_debt_post":round(cod_at,2),"equity_weight":round(we*100,1),
            "debt_weight":round(wd*100,1),"beta":beta,"risk_free_rate":rfr,"erp":erp,
            "terminal_growth":tg,"anchor_label":anchor_lbl,"base_growth":base_g,
            "ebitda_margin":round(em_pct,1),"capex_pct":round(cp,1),"sensitivity":sens}


def compute_implied_growth(m, sp):
    mktcap=m.get("market_cap_cr"); rev=m.get("revenue"); em=m.get("ebitda_margin")
    eq=m.get("total_equity"); brr=m.get("borrowings") or 0; csh=m.get("cash") or 0
    cx=m.get("capex"); ie=m.get("interest")
    if not all([mktcap,rev,em,eq]) or mktcap<=0 or rev<=0: return None
    rfr=sp["risk_free_rate"]; erp=sp["equity_risk_premium"]; beta=sp["beta"]
    coe=rfr+beta*erp
    cod_pre=round(ie/brr*100,2) if ie and brr and brr>0 else sp["cost_of_debt_pretax"]
    tax=sp["tax_rate"]/100; cod_at=cod_pre*(1-tax)
    tc=eq+brr; we=eq/tc; wd=brr/tc; wacc=we*coe+wd*cod_at
    tg=sp["terminal_growth"]/100; em_d=em/100; da=0.03
    cp=abs(cx)/rev if cx and rev else 0.05
    def dcf_eq(g):
        rv=rev; fcfs=[]
        for i in range(5):
            rv*=(1+g); nopat=(rv*em_d-rv*da)*(1-tax)
            fcf=nopat-rv*cp+rv*da-rv*0.005; fcfs.append(fcf/(1+wacc)**(i+1))
        fu=fcfs[-1]*(1+wacc)**5
        tv=fu*(1+tg)/(wacc-tg) if wacc>tg else 0
        return sum(fcfs)+tv/(1+wacc)**5+csh-brr
    lo,hi=0.0,0.45
    for _ in range(60):
        mid=(lo+hi)/2
        if dcf_eq(mid)<mktcap: lo=mid
        else: hi=mid
        if abs(hi-lo)<0.0001: break
    ig=round((lo+hi)/2*100,1)
    return ig if 0<=ig<=40 else None


def compute_probability_scenarios(m, sp, profile):
    """
    Compute scenario values and solve for implied market probabilities.
    Given current price, what probability distribution makes it rational?
    """
    rev=m.get("revenue"); eq=m.get("total_equity")
    if not rev or not eq: return {}
    brr=m.get("borrowings") or 0; csh=m.get("cash") or 0
    cx=m.get("capex"); ie=m.get("interest"); em=m.get("ebitda_margin") or 15
    base_cagr=m.get("rev_cagr_5y") or 10
    rfr=sp["risk_free_rate"]; erp=sp["equity_risk_premium"]; beta=sp["beta"]
    coe=rfr+beta*erp
    cod_pre=round(ie/brr*100,2) if ie and brr and brr>0 else sp["cost_of_debt_pretax"]
    tax=sp["tax_rate"]/100; cod_at=cod_pre*(1-tax)
    tc=eq+brr; we=eq/tc; wd=brr/tc; wacc=we*coe+wd*cod_at
    tg=sp["terminal_growth"]/100; da=0.03; cp=abs(cx)/rev if cx and rev else 0.05

    def simple_dcf(g_ann, em_adj, pe_exit):
        rv=rev; fcfs=[]
        em_d=(em+em_adj)/100
        for i in range(5):
            rv*=(1+g_ann/100); nopat=(rv*em_d-rv*da)*(1-tax)
            fcf=nopat-rv*cp+rv*da-rv*0.005; fcfs.append(fcf/(1+wacc)**(i+1))
        # Year 5 terminal via P/E
        pat_5y=rv*(em_d-0.05)*(1-tax)  # rough PAT
        tv_pe=pat_5y*pe_exit/(1+wacc)**5
        return round(sum(fcfs)+tv_pe+csh-brr,0)

    scenarios = profile.get("scenarios",{})
    results   = {}
    for key, sc in scenarios.items():
        cagr = base_cagr * sc["rev_cagr_mult"]
        val  = simple_dcf(cagr, sc["margin_delta"], sc["pe_exit"])
        results[key] = {
            "label":      sc["label"],
            "probability":sc["probability"],
            "rev_cagr":   round(cagr,1),
            "margin":     round(em+sc["margin_delta"],1),
            "value_cr":   val,
            "trigger":    sc.get("trigger",""),
        }

    # Weighted value
    weighted = sum(sc["probability"]*results[k]["value_cr"]
                   for k,sc in scenarios.items() if k in results)
    results["weighted_value_cr"] = round(weighted,0)

    # Implied disruption probability — solve for what p_disruption makes weighted = market cap
    mktcap = m.get("market_cap_cr")
    if mktcap and "base" in results and "disruption" in results and "acceleration" in results:
        vb=results["base"]["value_cr"]
        vd=results["disruption"]["value_cr"]
        va=results["acceleration"]["value_cr"]
        # market = pb*vb + pd*vd + pa*va, pb=0.6 fixed, pd+pa=0.4
        # market = 0.6*vb + x*vd + (0.4-x)*va
        # x = (market - 0.6*vb - 0.4*va) / (vd - va)
        denom = vd - va
        if abs(denom) > 100:
            x = (mktcap - 0.6*vb - 0.4*va) / denom
            x = max(0, min(0.4, x))
            results["implied_disruption_prob"] = round(x*100,0)
            results["implied_acceleration_prob"] = round((0.4-x)*100,0)

    return results


# ============================================================================
# GEMINI — reads PDF, extracts facts + the hidden insight
# ============================================================================

def gemini_read(pdf_bytes, co, yr, profile):
    _log.info(f"gemini_read: starting for {co} FY{yr}, PDF size {len(pdf_bytes)/1024:.0f}KB")
    """
    Gemini reads the full PDF and extracts:
    1. All financial statements (10Y)
    2. Qualitative facts from MD&A, governance, risks
    3. The ONE thing most analysts miss
    Two calls — financials first, qualitative second.
    """
    prompt_fin = f"""Read {co} Annual Report FY{yr}. Extract CONSOLIDATED financial statements.
All values ₹ Crores. Return ONLY valid JSON:
{{"years":["Mar 2024","Mar 2023"...],"revenue":[newest first],"ebitda":[...],"pat":[...],
"depreciation":[...],"interest":[...],"cfo":[...],"capex":[positive],"borrowings":[...],
"cash":[...],"equity_capital":[...],"reserves":[...],"fixed_assets":[...],"cwip":[...],
"total_assets":[...],"receivable_days":[...],"inventory_days":[...],"payable_days":[...],
"roce_pct":[...],"roe_pct":[...],"extraction_confidence":"HIGH/MEDIUM/LOW"}}"""

    value_driver = profile.get("value_driver","")
    thesis_risk  = profile.get("break_point","")

    prompt_qual = f"""You are a senior equity analyst reading {co} Annual Report FY{yr}.

Sector value driver to look for: {value_driver}
Key risk to assess: {thesis_risk}

Extract from MD&A, Board's Report, Governance, Risk sections. Return ONLY valid JSON:
{{
  "business_essence": "The single sentence that captures what this company actually is and why it earns what it earns. Not sector. The specific mechanism.",
  "how_it_earns": "Specific revenue mechanism with distribution channel and the moment of transaction.",
  "why_more_than_peers": "The specific operational advantage. Quote the passage from document.",
  "market_position": "Market share, rank, or leadership claim with evidence.",
  "segments": [{{"name":"...","revenue_pct":null,"margin_note":null}}],
  "competitors_named": ["exact names from document's own risk disclosures only"],
  "auditor_name": "exact name or null",
  "audit_opinion": "CLEAN/QUALIFIED/ADVERSE/UNKNOWN",
  "promoter_trend": "INCREASING/STABLE/DECREASING/UNKNOWN",
  "pledging": null,
  "mda_tone": "TRANSPARENT/NEUTRAL/DEFENSIVE/PROMOTIONAL",
  "owns_failures": null,
  "capital_allocation": "How FCF was deployed. Specific amounts and purposes.",
  "stated_targets": ["numeric targets management committed to — exact quotes"],
  "capex_amount_cr": null,
  "capex_purpose": null,
  "capacity_addition": null,
  "expansion_plans": ["specific with timelines"],
  "thesis_breaking_risk": "The ONE risk that most directly threatens the investment thesis. What management said. Is the response adequate.",
  "operational_risks": ["specific risks with document evidence"],
  "sector_cycle": "EARLY/MID/LATE/UNKNOWN",
  "cycle_evidence": null,
  "hidden_insight": "The single most important detail in this annual report that most analysts would miss — a footnote, a change in accounting, an operational metric, a management admission. Quote the specific passage.",
  "guidance_reliability": "HIGH/MEDIUM/LOW/NO_GUIDANCE",
  "overall_management_signal": "POSITIVE/NEUTRAL/CAUTION/RED_FLAG",
  "data_confidence": "HIGH/MEDIUM/LOW"
}}"""

    fin = {}; qual = {}

    # Financial extraction
    for attempt in range(3):
        try:
            r = _GEM.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Part.from_bytes(data=pdf_bytes,mime_type="application/pdf"),
                           types.Part.from_text(text=prompt_fin)],
                config=types.GenerateContentConfig(temperature=0.0,response_mime_type="application/json"))
            raw=re.sub(r"```(?:json)?|```","",r.text).strip()
            fin=json.loads(raw)
            years=fin.get("years",[]); rev=fin.get("revenue",[None])[0]; pat=fin.get("pat",[None])[0]
            _log.info(f"  PDF financials: {len(years)}Y | Revenue ₹{rev:,.0f}Cr | PAT ₹{pat:,.0f}Cr | {fin.get('extraction_confidence','?')}" if rev and pat else f"  PDF financials: {fin.get('extraction_confidence','?')}")
            break
        except Exception as e:
            if "429" in str(e) and attempt<2: w=30*(attempt+1); _log.info(f"  Wait {w}s..."); time.sleep(w)
            else: _log.info(f"  Gemini financials: {e}"); break

    time.sleep(8)  # rate limit between calls

    # Qualitative extraction
    for attempt in range(3):
        try:
            r = _GEM.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Part.from_bytes(data=pdf_bytes,mime_type="application/pdf"),
                           types.Part.from_text(text=prompt_qual)],
                config=types.GenerateContentConfig(temperature=0.0,response_mime_type="application/json"))
            raw=re.sub(r"```(?:json)?|```","",r.text).strip()
            qual=json.loads(raw)
            _log.info(f"  PDF qualitative: Mgmt={qual.get('overall_management_signal','?')} | "
                  f"Tone={qual.get('mda_tone','?')} | Confidence={qual.get('data_confidence','?')}")
            break
        except Exception as e:
            if "429" in str(e) and attempt<2: w=30*(attempt+1); _log.info(f"  Wait {w}s..."); time.sleep(w)
            else: _log.info(f"  Gemini qualitative: {e}"); break

    return fin, qual


# ============================================================================
# GROQ — ONE task: essence + verdict paragraph only
# ============================================================================

def groq_synthesis(m, qual, sec_d, dcf, peers, spreads, implied_g,
                   patterns, scenarios, early_w, profile, co, sector, yr,
                   macro_sigs=None):
    if not _GROQ: return {}

    mktcap=m.get("market_cap_cr"); roce=m.get("roce"); r5=m.get("rev_cagr_5y")
    r3=m.get("rev_cagr_3y"); em=m.get("ebitda_margin"); cfo_pat=m.get("cfo_to_pat")
    nwc=m.get("nwc_days"); nd_eb=m.get("net_debt_ebitda")

    # Build peer context string
    peer_str=""
    if spreads.get("roce"):
        s=spreads["roce"]; peer_str+=f"ROCE: co {s['company']:.1f}% vs median {s['peer_median']:.1f}% (+{s['spread']:.1f}pp). "
    if spreads.get("ebitda_margin"):
        s=spreads["ebitda_margin"]; peer_str+=f"Margin: co {s['company']:.1f}% vs median {s['peer_median']:.1f}% (+{s['spread']:.1f}pp). "

    scenario_str=""
    if scenarios:
        wv=scenarios.get("weighted_value_cr",0)
        idp=scenarios.get("implied_disruption_prob","?")
        scenario_str=f"Weighted value ₹{wv:,.0f}Cr vs market ₹{mktcap:,.0f}Cr. Market implying {idp}% disruption probability." if mktcap and wv else ""

    pattern_str="\n".join(f"  [{p['signal']}] {p['insight'][:120]}" for p in patterns[:3])

    macro_str = ""
    if macro_sigs:
        macro_str = "MACRO SIGNALS:\n" + "\n".join(
            f"  [{s['signal']}] {s['text'][:100]}" for s in macro_sigs
            if s.get("signal") != "NEUTRAL")

    sys_p="""Senior equity analyst. 2-3 paragraphs maximum. Every sentence must earn its place.
No hedging. No "may" or "could". No generic statements.
The verdict must state specifically whether to buy, hold, or avoid — with a price context.
Final sentence exactly: "Intelligence, not advice. All reasoning shown. The investor decides."
Output ONLY valid JSON."""

    user_p=f"""Company: {co} | Sector: {sector} | FY{yr}

KEY COMPUTED FACTS:
Revenue ₹{m.get('revenue',0):,.0f}Cr | EBITDA {em}% | PAT ₹{m.get('pat',0):,.0f}Cr
ROCE {roce}% (trend: {m.get('roce_trend','?')}) | CFO/PAT {cfo_pat} | NWC {nwc} days
Rev CAGR: 3Y {r3}% / 5Y {r5}%
{peer_str}
Implied perpetual CAGR at current price: {implied_g}% (historical 5Y: {r5}%)
{scenario_str}

PATTERN RECOGNITION (Python computed):
{pattern_str}

FROM ANNUAL REPORT (Gemini):
Business essence: {qual.get('business_essence','')}
Why earns more: {qual.get('why_more_than_peers','')}
Hidden insight: {qual.get('hidden_insight','')}
Thesis risk: {qual.get('thesis_breaking_risk','')}
Management signal: {qual.get('overall_management_signal','')}

{macro_str}

SECTOR BREAK POINT:
{profile.get('break_point','')}

Return JSON:
{{
  "the_essence": "One sentence. What is this company actually. Not sector. The specific mechanism.",
  "what_market_misses": "One specific insight that most analysts don't price in. Evidence-based.",
  "the_verdict_paragraph": "2-3 paragraphs. Business reality → what the numbers show → peer position → what the market is pricing → the one risk → the price at which it gets interesting. Final sentence exactly: Intelligence, not advice. All reasoning shown. The investor decides."
}}"""

    try:
        r=_GROQ.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"system","content":sys_p},{"role":"user","content":user_p}],
            max_tokens=1500,temperature=0.0)
        raw=re.sub(r"```(?:json)?|```","",r.choices[0].message.content).strip()
        return json.loads(raw)
    except Exception as e:
        _log.info(f"  Groq: {e}"); return {}


def compute_conviction(m, qual, sec_d, spreads):
    score=0; disq=[]
    moat_verdict = "UNPROVEN"
    # Derive moat from pattern recognition (ROCE spread vs sector)
    roce_s = spreads.get("roce",{})
    if roce_s.get("spread",0) > 15: moat_verdict="STRONG"
    elif roce_s.get("spread",0) > 5: moat_verdict="NARROW"
    elif roce_s.get("company",0) > 15: moat_verdict="NARROW"

    mgmt=qual.get("overall_management_signal","NEUTRAL")
    risk_level="MODERATE"  # default; will refine from early warnings

    score+={"STRONG":25,"NARROW":15,"NONE":5,"UNPROVEN":10}.get(moat_verdict,10)
    score+={"POSITIVE":20,"NEUTRAL":12,"CAUTION":5,"RED_FLAG":0}.get(mgmt,12)
    if mgmt=="RED_FLAG": disq.append("Management RED_FLAG")

    eq=sec_d.get("overall","MEDIUM")
    score+={"HIGH":20,"MEDIUM":14,"LOW":6,"POOR":0}.get(eq,14)

    roce=m.get("roce")
    if roce: score+=(15 if roce>25 else 10 if roce>15 else 5 if roce>8 else 0)

    score+=7  # risk neutral
    if len(disq)>=2: return "AVOID",f"Disqualified: {', '.join(disq)}"
    if qual.get("data_confidence","LOW")=="LOW": score=max(0,score-10)

    pct=score/107*100
    if pct>=78: return "STRONG BUY CASE",f"Score {score}/107 ({pct:.0f}%)"
    if pct>=62: return "BUY CASE",        f"Score {score}/107 ({pct:.0f}%)"
    if pct>=45: return "WATCHLIST",        f"Score {score}/107 ({pct:.0f}%)"
    return "AVOID",f"Score {score}/107 ({pct:.0f}%)"


def compute_section_D(m):
    cfo_pat=m.get("cfo_to_pat")
    if cfo_pat is not None:
        if cfo_pat>=0.85: cc,fl="HEALTHY",False; ce=f"CFO/PAT {cfo_pat:.2f}"
        elif cfo_pat>=0.60: cc,fl="WATCH",True; ce=f"CFO/PAT {cfo_pat:.2f} — cash below profits"
        else: cc,fl="POOR",True; ce=f"CFO/PAT {cfo_pat:.2f} — material gap"
    else: cc,fl,ce="INSUFFICIENT_DATA",False,"N/A"
    roce=m.get("roce"); roce_arr=m.get("roce_arr",[])
    if roce:
        if roce>=25: ra,rf="EXCELLENT",False
        elif roce>=15: ra,rf="GOOD",False
        elif roce>=8: ra,rf="WEAK",True
        else: ra,rf="VERY_WEAK",True
    else: ra,rf="UNKNOWN",False
    nc=m.get("_net_cash",False); nd_eb=m.get("net_debt_ebitda"); ic=m.get("interest_cov")
    dq_flags=[]
    if nc: da="NET_CASH"
    elif nd_eb is not None:
        if nd_eb<=1.5: da="CONSERVATIVE"
        elif nd_eb<=3.0: da="MANAGEABLE"
        elif nd_eb<=5.0: da="ELEVATED"; dq_flags.append(f"ND/EBITDA {nd_eb:.1f}x")
        else: da="STRESSED"; dq_flags.append(f"ND/EBITDA {nd_eb:.1f}x critical")
    else: da="UNKNOWN"
    if ic and ic<3: dq_flags.append(f"Int coverage {ic:.1f}x")
    score=0
    if cc=="HEALTHY": score+=3
    elif cc=="WATCH": score+=1
    if ra=="EXCELLENT": score+=3
    elif ra=="GOOD": score+=2
    elif ra=="WEAK": score+=1
    if da in("NET_CASH","CONSERVATIVE","MANAGEABLE"): score+=2
    elif da=="ELEVATED": score+=1
    score+=1
    overall=("HIGH" if score>=7 else "MEDIUM" if score>=5 else "LOW" if score>=3 else "POOR")
    return {"overall":overall,"score":score,
            "cash_conversion":{"assessment":cc,"flag":fl,"value":cfo_pat,"explanation":ce},
            "return_on_capital":{"assessment":ra,"flag":rf,"roce":roce},
            "debt_quality":{"assessment":da,"flag":len(dq_flags)>0,"flags":dq_flags}}

# ============================================================================
# OUTPUT — dense, compact, institutional
# ============================================================================

def _W(txt,w=62,i=4):
    if txt:
        for line in textwrap.wrap(str(txt),w): _log.info(" "*i+line)

def _SH(lt,t): _log.info(); _log.info(f"  {'─'*60}"); _log.info(f"  {lt}  {t}"); _log.info(f"  {'─'*60}")
def _H(t,c="═"): _log.info(); _log.info(c*65); _log.info(f"  {t}"); _log.info(c*65)
def _L(n=65): _log.info("─"*n)


def print_brief(co, bse, yr, sector, fin_raw, m, dcf, qual,
                peers, spreads, implied_g, patterns, scenarios,
                early_w, sec_d, sec_I, conviction, cv_reason, profile,
                macro_sigs=None):

    # ── HEADER ────────────────────────────────────────────────────────────────
    _log.info()
    _log.info("═"*65)
    _log.info(f"  FINTELLIGENCE  |  {co.upper()}  |  FY{yr}  |  {conviction}")
    _log.info(f"  {cv_reason}")
    _log.info("═"*65)
    _log.info(f"  BSE {bse}  |  Sector: {sector.upper()}  |  {datetime.now().strftime('%d %b %Y %H:%M')}")
    if implied_g:
        hist=m.get("rev_cagr_5y",0) or 0
        ctx = ("below historical delivery — market is conservative" if implied_g<hist*0.85
               else "above historical delivery — market prices acceleration" if implied_g>hist*1.15
               else "consistent with historical delivery")
        _log.info(f"  MARKET IMPLIES: {implied_g}% perpetual CAGR ({ctx})")
    _log.info("═"*65)

    # ── FINANCIAL SNAPSHOT ────────────────────────────────────────────────────
    _SH("", "FINANCIAL SNAPSHOT  (₹ Crores)")
    years=fin_raw.get("years",[])
    _log.info(f"  As of {years[0] if years else 'N/A'}  |  PDF extraction: {fin_raw.get('extraction_confidence','?')}")
    _log.info()

    # Two columns for compactness
    left  = [("Revenue",  m.get("revenue"),  "{:,.0f}"),
             ("EBITDA",   m.get("ebitda"),   "{:,.0f}"),
             ("EBITDA %", m.get("ebitda_margin"), "{:.1f}%"),
             ("PAT",      m.get("pat"),      "{:,.0f}"),
             ("PAT %",    m.get("pat_margin"),    "{:.1f}%"),
             ("CFO",      m.get("cfo"),      "{:,.0f}"),
             ("FCF",      m.get("fcf"),      "{:,.0f}"),]
    right = [("ROCE",     m.get("roce"),     "{:.1f}%"),
             ("ROE",      m.get("roe"),      "{:.1f}%"),
             ("CFO/PAT",  m.get("cfo_to_pat"),   "{:.2f}"),
             ("Int Cov",  m.get("interest_cov"), "{:.1f}x"),
             ("Net Debt", m.get("net_debt"),  "{:,.0f}"),
             ("ND/EBITDA",m.get("net_debt_ebitda"),"{:.2f}x"),
             ("D/E",      m.get("debt_equity"),   "{:.2f}x"),]

    for (ll,lv,lf),(rl,rv,rf) in zip(left,right):
        ls = f"{lf.format(lv)}" if lv is not None else "N/A"
        rs = f"{rf.format(rv)}" if rv is not None else "N/A"
        try: _log.info(f"  {ll:<14}: {ls:<16}  {rl:<14}: {rs}")
        except:

            _log.debug("Suppressed exception", exc_info=True)

    _log.info()
    for lbl,key in [("Rev CAGR","rev_cagr_3y"),("","rev_cagr_5y"),("","rev_cagr_10y"),
                    ("PAT CAGR","pat_cagr_3y"),("","pat_cagr_5y")]:
        v=m.get(key)
        if v is not None:
            suffix=key.replace("rev_cagr_","").replace("pat_cagr_","")
            _log.info(f"  {lbl if lbl else '        '} {suffix.upper()}: {v:.1f}%")

    # NWC
    nwc=m.get("nwc_days"); pe=m.get("pe"); mktcap=m.get("market_cap_cr")
    if nwc is not None: _log.info(f"  NWC Days: {nwc:.0f}" + (" (NET CASH POSITION — dealers fund operations)" if nwc<0 else ""))
    if pe:   _log.info(f"  P/E: {pe:.1f}x")
    if mktcap: _log.info(f"  Market Cap: ₹{mktcap:,.0f} Cr")

    # 10-year trend
    if len(years)>=5:
        n=min(10,len(years))
        _log.info(f"\n  10-YEAR TREND (most recent → oldest):")
        _log.info(f"  {'':10} " + " ".join(f"{str(y)[:7]:>9}" for y in years[:n]))
        _L()
        for key,lbl,sarr in [("rev_arr","Revenue","rev_arr"),("ebitda_margin_arr","EBITDA%","ebitda_margin_arr"),
                               ("pat_arr","PAT","pat_arr"),("roce_arr","ROCE%","roce_arr"),("cfo_arr","CFO","cfo_arr")]:
            arr=m.get(sarr) or m.get(key) or fin_raw.get(key.replace("_arr",""),[])
            if not isinstance(arr,list): arr=[]
            arr=arr[:n]
            if arr and any(x is not None for x in arr):
                vals=" ".join(f"{x:>9.1f}" if x is not None else f"{'N/A':>9}" for x in arr)
                _log.info(f"  {lbl:<10} {vals}")

    # ── PEER COMPARISON ───────────────────────────────────────────────────────
    if peers:
        _SH("", f"PEER COMPARISON — {sector.upper()}")
        _log.info(f"  {'Metric':<22} {co[:14]:>14}", end="")
        for nm in peers.keys(): _log.info(f" {nm[:12]:>13}", end="")
        _log.info(); _L()

        for metric,lbl,fmt in [
            ("roce","ROCE %","{:.1f}"),("ebitda_margin","EBITDA Margin %","{:.1f}"),
            ("pat_margin","PAT Margin %","{:.1f}"),("nwc_days","NWC Days","{:.0f}"),
            ("cfo_to_pat","CFO / PAT","{:.2f}"),("rev_cagr_5y","Rev CAGR 5Y %","{:.1f}"),
            ("pe","P / E","{:.1f}"),
        ]:
            co_v=m.get(metric)
            if co_v is None: continue
            try: cs=fmt.format(co_v)
            except: cs=str(co_v)
            _log.info(f"  {lbl:<22} {cs:>14}", end="")
            for nm in peers.keys():
                pv=peers[nm].get(metric)
                try: ps=fmt.format(pv) if pv is not None else "N/A"
                except: ps="N/A"
                _log.info(f" {ps:>13}", end="")
            _log.info()
        _log.info()
        for metric,lbl in [("roce","ROCE"),("ebitda_margin","EBITDA Margin"),("nwc_days","NWC Days")]:
            s=spreads.get(metric,{})
            if s.get("spread") is not None:
                sg="+" if s["spread"]>=0 else ""
                better = ("better" if (s["spread"]>0 and metric!="nwc_days") or (s["spread"]<0 and metric=="nwc_days") else "worse")
                _log.info(f"  {lbl} vs sector median: {sg}{s['spread']:.1f} ({better} than median {s['peer_median']:.1f})")

    # ── DCF ──────────────────────────────────────────────────────────────────
    if dcf.get("available"):
        _SH("", "DCF VALUATION  (₹ Crores)")
        _log.info(f"  Bear: ₹{dcf['bear_cr']:>13,.0f}   Bull: ₹{dcf['bull_cr']:>13,.0f}")
        _log.info(f"  Base: ₹{dcf['base_cr']:>13,.0f}   MCap: ₹{mktcap:>13,.0f}" if mktcap else f"  Base: ₹{dcf['base_cr']:>13,.0f}")
        if mktcap:
            if mktcap>dcf["bull_cr"]: _log.info(f"  → {mktcap/dcf['bull_cr']:.1f}x own bull case")
            elif mktcap<dcf["bear_cr"]: _log.info(f"  → BELOW bear case — significant discount")
        _log.info(f"\n  WACC {dcf['wacc_pct']}% | TG {dcf['terminal_growth']}% | Anchor: {dcf['anchor_label']}")
        _log.info(f"  EBITDA {dcf['ebitda_margin']}% | Capex {dcf['capex_pct']}% | Growth: {dcf['base_growth']}")
        sens=dcf.get("sensitivity",{})
        if sens:
            hk=list(list(sens.values())[0].keys()) if sens else []
            if hk:
                _hdr = 'WACC\\TG'
                _log.info(f"\n  {_hdr:<14} "+" ".join(f"{k:>14}" for k in hk))
                _L()
                for wk,row in sens.items():
                    vals=" ".join(f"{row.get(k,0):>14,.0f}" if isinstance(row.get(k),(int,float)) else f"{'N/A':>14}" for k in hk)
                    _log.info(f"  {wk:<14} {vals}")

    # ── PROBABILITY SCENARIOS ─────────────────────────────────────────────────
    if scenarios and any(k in scenarios for k in ["base","disruption","acceleration"]):
        _SH("", "PROBABILITY-WEIGHTED SCENARIOS")
        _log.info(f"  {'Scenario':<25} {'Prob':>5} {'CAGR':>6} {'Margin':>7} {'Value (₹Cr)':>14}")
        _L()
        for key,sc_data in [(k,scenarios[k]) for k in ["base","disruption","acceleration"] if k in scenarios]:
            _log.info(f"  {sc_data['label']:<25} {sc_data['probability']*100:>4.0f}% "
                  f"{sc_data['rev_cagr']:>5.1f}% {sc_data['margin']:>6.1f}% "
                  f"{sc_data['value_cr']:>14,.0f}")
        _L()
        wv=scenarios.get("weighted_value_cr",0)
        _log.info(f"  {'Weighted value':<25} {'':>5} {'':>6} {'':>7} {wv:>14,.0f}")
        idp=scenarios.get("implied_disruption_prob")
        iap=scenarios.get("implied_acceleration_prob")
        if idp is not None and mktcap:
            _log.info(f"\n  At ₹{mktcap:,.0f}Cr market cap, market implies:")
            _log.info(f"    Disruption: {idp:.0f}% | Base: 60% | Acceleration: {iap:.0f}%")
            if idp > 25:
                _log.info(f"  → Market is pricing more disruption risk than warranted at {idp:.0f}%")
            elif idp < 15:
                _log.info(f"  → Market assumes smooth sailing at only {idp:.0f}% disruption probability")

    # ── PATTERN RECOGNITION ───────────────────────────────────────────────────
    if patterns:
        _SH("", "PATTERN RECOGNITION  [Python computed]")
        for p in patterns:
            icon={"STRENGTH":"✓","WARNING":"⚠","NORMAL":"→","INFO":"·"}.get(p["signal"],"·")
            _log.info(f"  [{p['signal']:<8}] {icon} ", end="")
            _W(p["insight"],w=56,i=15)

    # ── EARLY WARNING SYSTEM ──────────────────────────────────────────────────
    if early_w:
        _SH("", "EARLY WARNING SYSTEM")
        _log.info(f"  {'Metric':<25} {'Current':>9} {'Warn':>8} {'Critical':>9} {'Status':>9}")
        _L()
        for ew in early_w:
            curr=f"{ew['current']:.1f}"
            warn=f"{ew['threshold_warn']:.1f}" if ew.get("threshold_warn") else "—"
            crit=f"{ew['threshold_crit']:.1f}" if ew.get("threshold_crit") else "—"
            icon={"OK":"✓","WARN":"⚠","CRITICAL":"✗"}.get(ew["status"],"·")
            _log.info(f"  {ew['label']:<25} {curr:>9} {warn:>8} {crit:>9} {icon} {ew['status']}")
        _log.info()
        for ew in early_w:
            if ew["status"] in ("WARN","CRITICAL"):
                _log.info(f"  ⚠ {ew['label']}: {ew['interpretation']}")

    # ── MACRO SIGNALS ────────────────────────────────────────────────────────
    if macro_sigs:
        relevant = [s for s in macro_sigs if s.get("signal") != "NEUTRAL"]
        if relevant:
            _SH("", f"MACRO SIGNALS — {sector.upper()}")
            for s in relevant:
                icon = {"WARNING":"⚠","POSITIVE":"↑","INFO":"·"}.get(s.get("signal",""),"·")
                _log.info(f"  [{s.get('signal','?'):<8}] {icon} ", end="")
                _W(s.get("text","")[:100], w=55, i=15)

    # ── SECTIONS A-H ─────────────────────────────────────────────────────────
    _SH("A", "BUSINESS UNDERSTANDING")
    if qual.get("business_essence"): _W(qual["business_essence"])
    if qual.get("how_it_earns"): _log.info(); _log.info("    HOW IT EARNS:"); _W(qual["how_it_earns"],w=60,i=6)
    if qual.get("why_more_than_peers"): _log.info(); _log.info("    WHY MORE THAN PEERS:"); _W(qual["why_more_than_peers"],w=60,i=6)
    if qual.get("market_position"): _log.info(); _W(f"Market position: {qual['market_position']}")
    segs=qual.get("segments") or []
    if segs:
        _log.info("    Segments:")
        for s in segs:
            pct=f" ({s['revenue_pct']:.0f}%)" if s.get("revenue_pct") else ""
            _log.info(f"      - {s.get('name','?')}{pct}")
    comps=qual.get("competitors_named") or []
    if comps: _log.info(f"    Competitors (named in document): {', '.join(comps)}")

    _SH("B", "MOAT ASSESSMENT")
    roce_s=spreads.get("roce",{})
    em_s=spreads.get("ebitda_margin",{})
    nwc_s=spreads.get("nwc_days",{})
    if roce_s.get("spread") is not None:
        sp_v=roce_s["spread"]
        if sp_v>20: verdict="STRONG — ROCE premium of +{:.0f}pp vs sector is structural, not cyclical".format(sp_v)
        elif sp_v>8: verdict="NARROW — ROCE premium of +{:.0f}pp exists but not dominant".format(sp_v)
        elif sp_v>0: verdict="WEAK PREMIUM — marginal advantage"
        else: verdict="NO PREMIUM — trades at sector level or below"
        _log.info(f"    Moat verdict (Python — ROCE spread): {verdict}")
    if qual.get("why_more_than_peers"): _W(qual["why_more_than_peers"],w=60,i=4)
    _log.info(f"\n    Sector value driver: {profile['value_driver'][:100]}")
    _log.info(f"    Hidden alpha: {profile['hidden_alpha'][:100]}")

    _SH("C", "MANAGEMENT QUALITY")
    mgmt_signal=qual.get("overall_management_signal","N/A")
    _log.info(f"    Signal: {mgmt_signal}")
    if qual.get("capital_allocation"): _log.info(f"    Capital allocation: {str(qual['capital_allocation'])[:100]}")
    targets=qual.get("stated_targets",[]) or []
    if targets:
        _log.info("    Stated targets:")
        for t in targets[:3]: _log.info(f"      → {t}")
    aud=qual.get("auditor_name"); op=qual.get("audit_opinion")
    if aud or op: _log.info(f"    Auditor: {aud or 'N/A'} | Opinion: {op or 'N/A'}")
    _log.info(f"    Promoter: {qual.get('promoter_trend','N/A')} | "
          f"Tone: {qual.get('mda_tone','N/A')} | "
          f"Owns failures: {qual.get('owns_failures','N/A')}")

    _SH("D", "EARNINGS QUALITY  [computed]")
    _log.info(f"    Overall: {sec_d.get('overall','N/A')} (score {sec_d.get('score','?')}/9)")
    for key,lbl in [("cash_conversion","Cash Conversion"),("return_on_capital","Return on Capital"),("debt_quality","Debt Quality")]:
        s=sec_d.get(key,{})
        if s:
            flag=" ⚠" if s.get("flag") else ""
            _log.info(f"    {lbl:<22}: {s.get('assessment','N/A')}{flag}")
            for f in (s.get("flags") or []): _log.info(f"      ⚠ {f}")

    _SH("E", "FINANCIAL PERFORMANCE  [computed]")
    r3=m.get("rev_cagr_3y"); r5=m.get("rev_cagr_5y"); r10=m.get("rev_cagr_10y")
    p3=m.get("pat_cagr_3y"); p5=m.get("pat_cagr_5y"); em=m.get("ebitda_margin")
    em_arr=m.get("margin_hist",[]) or []
    roce=m.get("roce"); cfo_pat=m.get("cfo_to_pat")
    _log.info(f"    Revenue CAGR: 3Y {r3}% | 5Y {r5}% | 10Y {r10}%")
    _log.info(f"    PAT CAGR:     3Y {p3}% | 5Y {p5}%")
    _log.info(f"    EBITDA margin: {em}% (5Y range {min(em_arr[:6]):.0f}%-{max(em_arr[:6]):.0f}%)" if len(em_arr)>=3 else f"    EBITDA margin: {em}%")
    _log.info(f"    ROCE: {roce}% (trend: {m.get('roce_trend','?')}) | CFO/PAT: {cfo_pat}")
    if m.get("_net_cash"): _log.info(f"    Balance sheet: NET CASH — ₹{abs(m.get('net_debt',0)):,.0f}Cr net cash position")
    elif m.get("net_debt_ebitda"): _log.info(f"    Leverage: Net Debt/EBITDA {m['net_debt_ebitda']:.2f}x")

    _SH("F", "FINANCIAL MODEL")
    if dcf.get("available"):
        _log.info(f"    Base DCF: ₹{dcf['base_cr']:,.0f}Cr | Anchor: {dcf['anchor_label']}")
        _log.info(f"    EBITDA margin: {dcf['ebitda_margin']}% | Capex: {dcf['capex_pct']}% of revenue")
    cap=qual.get("capex_amount_cr"); purp=qual.get("capex_purpose")
    if cap: _log.info(f"    Stated capex: ₹{cap}Cr{' — '+purp if purp else ''}")
    plans=qual.get("expansion_plans",[]) or []
    for p in plans[:3]: _log.info(f"      · {p}")
    _log.info(f"    Guidance reliability: {qual.get('guidance_reliability','N/A')}")

    _SH("G", "VALUATION")
    pe=m.get("pe"); mktcap=m.get("market_cap_cr")
    if pe: _log.info(f"    P/E: {pe:.1f}x")
    bv=m.get("book_value"); cp_raw=m.get("current_price")
    if bv and cp_raw and bv>0:
        try:
            cp_f=float(str(cp_raw).replace("₹","").replace(",",""))
            _log.info(f"    P/B: {cp_f/bv:.2f}x")
        except:

            _log.debug("Suppressed exception", exc_info=True)
    if mktcap: _log.info(f"    Market Cap: ₹{mktcap:,.0f}Cr")
    if implied_g:
        hist=m.get("rev_cagr_5y",0) or 0
        _log.info(f"    Implied CAGR at current price: {implied_g}% (historical 5Y: {hist:.1f}%)")
    if dcf.get("available") and mktcap:
        base=dcf["base_cr"]; bull=dcf["bull_cr"]; bear=dcf["bear_cr"]
        if mktcap>bull*1.05: vd=f"ABOVE BULL CASE ({mktcap/bull:.1f}x bull)"
        elif mktcap>base*1.15: vd=f"PREMIUM to base case"
        elif mktcap<base*0.85: vd=f"DISCOUNT to base case"
        elif mktcap<bear: vd=f"BELOW BEAR CASE"
        else: vd=f"AT FAIR VALUE vs base"
        _log.info(f"    DCF position: {vd}")

    _SH("H", "RISK FLAGS")
    tbr=qual.get("thesis_breaking_risk","")
    if tbr: _log.info("    THESIS RISK:"); _W(tbr,w=60,i=6)
    ops=qual.get("operational_risks",[]) or []
    for r in ops[:3]: _log.info(f"    WATCH: {str(r)[:80]}")
    sc=qual.get("sector_cycle")
    if sc and sc!="UNKNOWN": _log.info(f"    Sector cycle: {sc} — {qual.get('cycle_evidence','')}")
    _log.info(f"\n    SECTOR BREAK POINT:")
    _W(profile.get("break_point",""),w=60,i=6)

    # ── INTELLIGENCE ──────────────────────────────────────────────────────────
    if sec_I:
        _SH("I", "INTELLIGENCE BRIEF  [Groq synthesis]")
        essence=sec_I.get("the_essence","")
        miss=sec_I.get("what_market_misses","")
        verdict=sec_I.get("the_verdict_paragraph","")

        if essence:
            _log.info("\n  THE ESSENCE:")
            _W(essence,w=63,i=4)

        if qual.get("hidden_insight"):
            _log.info("\n  WHAT THE ANNUAL REPORT HIDES:")
            _W(qual["hidden_insight"],w=63,i=4)

        if miss:
            _log.info("\n  WHAT THE MARKET MISSES:")
            _W(miss,w=63,i=4)

        if verdict:
            _L()
            _log.info("\n  VERDICT:")
            _log.info()
            for para in str(verdict).split("\n\n"):
                para=para.strip()
                if para: _W(para,63); _log.info()

    _log.info("═"*65)
    _log.info(f"  Data: Annual report (Gemini) + Screener peers + Python computation")
    _log.info(f"  Intelligence, not advice. The investor decides.")
    _log.info("═"*65)

# ============================================================================
# MAIN
# ============================================================================

# ============================================================================
# END OF MODULE
# Use initialize() to connect API clients before calling any analysis function.
# main.py (FastAPI service) imports this module and manages the lifecycle.
# ============================================================================