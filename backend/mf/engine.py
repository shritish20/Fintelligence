# ============================================================================
# FINTELLIGENCE — Mutual Fund Intelligence Engine
#
# Phase 1 : Quantitative performance engine (NAV-based metrics)
# Phase 2 : Metadata + AI conviction brief (Groq / Claude)
# Phase 3 : Portfolio holdings + overlap detection (AMFI data)
# Phase 4 : Live market regime context (VIX, FII, macro, news)
# Phase 5 : Debt fund intelligence (separate framework)
#
# USAGE:
#   analyse_fund(122639)              — equity fund full brief
#   analyse_debt_fund(119016)         — debt fund full brief
#   analyse_portfolio([122639,120503])— multi-fund overlap
#   get_regime_context(...)           — standalone macro regime
#   find_fund("parag parikh flexi")   — search scheme codes
#   find_debt_fund("HDFC short term") — search debt scheme codes
# ============================================================================


# Dependencies are managed via requirements.txt


# ============================================================================
# IMPORTS & LLM SETUP
# ============================================================================

import requests
import logging
import pandas as pd
_log = logging.getLogger("mf_engine")
import numpy as np
from scipy import stats
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import warnings
import time
import os
import io
import re
warnings.filterwarnings('ignore')

try:
    from pyxirr import xirr as _xirr
    PYXIRR = True
except ImportError:
    PYXIRR = False

# yfinance removed — blocked on server/datacenter IPs.
# Replaced by Stooq (global macro) + NSE JSON API (India VIX).
YFINANCE = False  # kept as dead flag for any residual guards

try:
    import feedparser
    FEEDPARSER = True
except ImportError:
    FEEDPARSER = False

# LLM: Anthropic (Claude) → Groq → rule-based fallback
_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
_GROQ_KEY      = os.environ.get("GROQ_API_KEY", "").strip()
_LLM_PROVIDER  = "none"
_LLM_CLIENT    = None

if _ANTHROPIC_KEY:
    try:
        import anthropic as _ant
        _LLM_CLIENT   = _ant.Anthropic(api_key=_ANTHROPIC_KEY)
        _LLM_PROVIDER = "claude"
    except Exception:

        _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)

if _LLM_PROVIDER == "none" and _GROQ_KEY:
    try:
        from groq import Groq as _Groq
        _LLM_CLIENT   = _Groq(api_key=_GROQ_KEY)
        _LLM_PROVIDER = "groq"
    except Exception:

        _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)

if _LLM_PROVIDER == "none":
    import logging as _log; _log.getLogger(__name__).warning("No LLM key — rule-based fallback active")


# ============================================================================
# CONFIGURATION
# ============================================================================

RISK_FREE_RATE = 0.065
TRADING_DAYS   = 252
SIP_AMOUNT     = 10000

# Benchmark map: fund category → (scheme_code, name)
BENCHMARK_MAP = {
    'flexi cap':     ('120716', 'UTI Nifty 50 Index Direct (TRI Proxy)'),
    'large cap':     ('120716', 'UTI Nifty 50 Index Direct (TRI Proxy)'),
    'multi cap':     ('120716', 'UTI Nifty 50 Index Direct (TRI Proxy)'),
    'large and mid': ('120716', 'UTI Nifty 50 Index Direct (TRI Proxy)'),
    'focused':       ('120716', 'UTI Nifty 50 Index Direct (TRI Proxy)'),
    'mid cap':       ('145552', 'Motilal Oswal Nifty Midcap 150 Index Direct (TRI Proxy)'),
    'small cap':     ('148496', 'Motilal Oswal Nifty Smallcap 250 Index Direct (TRI Proxy)'),
    'elss':          ('120716', 'UTI Nifty 50 Index Direct (TRI Proxy)'),
    'tax saver':     ('120716', 'UTI Nifty 50 Index Direct (TRI Proxy)'),
    'sectoral':      ('120716', 'UTI Nifty 50 Index Direct (note: sector TRI ideal)'),
    'thematic':      ('120716', 'UTI Nifty 50 Index Direct (note: sector TRI ideal)'),
    'debt':          (None,     'Debt — benchmark N/A in Phase 1'),
    'default':       ('120716', 'UTI Nifty 50 Index Direct (TRI Proxy)'),
}

def get_benchmark(category):
    cat = (category or '').lower()
    for k, v in BENCHMARK_MAP.items():
        if k in cat:
            return v
    return BENCHMARK_MAP['default']

def is_debt_fund(category):
    kw = ['debt', 'bond', 'duration', 'liquid', 'overnight', 'gilt',
          'credit risk', 'floater', 'money market', 'banking and psu',
          'corporate bond', 'dynamic bond', 'fixed income']
    cat = (category or '').lower()
    return any(k in cat for k in kw)

# Debt category profiles
DEBT_PROFILES = {
    'overnight fund':         {'duration_band':(0.003,0.010),'credit_profile':'AAA_ONLY',
                               'rate_sensitivity':'NEGLIGIBLE','primary_risk':'opportunity_cost',
                               'benchmark_return':6.0,'return_ceiling':7.0,'stress_risk':'MINIMAL',
                               'suitable_for':'Parking surplus 1-7 days.',
                               'avoid_if':'Holding more than 30 days.'},
    'liquid fund':            {'duration_band':(0.04,0.08),'credit_profile':'AAA_DOMINANT',
                               'rate_sensitivity':'VERY_LOW','primary_risk':'credit_event_on_cp',
                               'benchmark_return':6.5,'return_ceiling':7.5,'stress_risk':'LOW',
                               'suitable_for':'Emergency corpus, up to 90 days.',
                               'avoid_if':'Holding for returns over FD.'},
    'ultra short duration':   {'duration_band':(0.25,0.50),'credit_profile':'AAA_AA_MIX',
                               'rate_sensitivity':'LOW','primary_risk':'credit_downgrade',
                               'benchmark_return':6.8,'return_ceiling':8.0,'stress_risk':'LOW_MODERATE',
                               'suitable_for':'3-12 months surplus.',
                               'avoid_if':'Chasing yield via AA- or lower.'},
    'low duration':           {'duration_band':(0.50,1.0),'credit_profile':'AAA_AA_MIX',
                               'rate_sensitivity':'LOW','primary_risk':'credit_and_mild_rate',
                               'benchmark_return':7.0,'return_ceiling':8.5,'stress_risk':'LOW_MODERATE',
                               'suitable_for':'6-12 month holding, FD alternative at higher brackets.',
                               'avoid_if':'Rate cut cycle — short duration is more efficient.'},
    'money market':           {'duration_band':(0.25,1.0),'credit_profile':'AAA_DOMINANT',
                               'rate_sensitivity':'LOW','primary_risk':'reinvestment_rate',
                               'benchmark_return':7.0,'return_ceiling':8.0,'stress_risk':'LOW',
                               'suitable_for':'Parking Rs10L+ for 3-12 months.',
                               'avoid_if':'Retail seeking returns — short duration beats this.'},
    'short duration':         {'duration_band':(1.0,3.0),'credit_profile':'AAA_AA_MIX',
                               'rate_sensitivity':'MODERATE','primary_risk':'rate_and_credit_combined',
                               'benchmark_return':7.0,'return_ceiling':9.0,'stress_risk':'MODERATE',
                               'suitable_for':'2-3 year core debt allocation.',
                               'avoid_if':'Rising rate cycle.'},
    'medium duration':        {'duration_band':(3.0,4.0),'credit_profile':'AAA_AA_MIX',
                               'rate_sensitivity':'MODERATE_HIGH','primary_risk':'rate_cycle_timing',
                               'benchmark_return':7.5,'return_ceiling':10.0,'stress_risk':'MODERATE_HIGH',
                               'suitable_for':'Rate cut expectation play, 3-5 year horizon.',
                               'avoid_if':'Uncertain rate cycle.'},
    'medium to long duration':{'duration_band':(4.0,7.0),'credit_profile':'GSEC_DOMINANT',
                               'rate_sensitivity':'HIGH','primary_risk':'interest_rate_risk',
                               'benchmark_return':7.5,'return_ceiling':12.0,'stress_risk':'HIGH',
                               'suitable_for':'Strong rate cut conviction, 5+ years, can tolerate 8-10% NAV swings.',
                               'avoid_if':'No clear rate cut view.'},
    'long duration':          {'duration_band':(7.0,15.0),'credit_profile':'GSEC_DOMINANT',
                               'rate_sensitivity':'VERY_HIGH','primary_risk':'interest_rate_risk',
                               'benchmark_return':7.5,'return_ceiling':15.0,'stress_risk':'VERY_HIGH',
                               'suitable_for':'Rate cut cycle play only.',
                               'avoid_if':'Anyone who thinks this is a safe debt fund.'},
    'dynamic bond':           {'duration_band':(1.0,10.0),'credit_profile':'GSEC_AAA_MIX',
                               'rate_sensitivity':'VARIABLE','primary_risk':'manager_call_risk',
                               'benchmark_return':7.5,'return_ceiling':12.0,'stress_risk':'MODERATE_HIGH',
                               'suitable_for':'Investor who trusts manager to time rate cycles.',
                               'avoid_if':'Passive investors.'},
    'corporate bond':         {'duration_band':(1.0,4.0),'credit_profile':'AA_PLUS_DOMINANT',
                               'rate_sensitivity':'MODERATE','primary_risk':'credit_spread_widening',
                               'benchmark_return':7.5,'return_ceiling':9.5,'stress_risk':'MODERATE',
                               'suitable_for':'Core debt, 2-3 year horizon.',
                               'avoid_if':'Fund holding below AA paper.'},
    'credit risk fund':       {'duration_band':(1.0,3.0),'credit_profile':'AA_BELOW_DOMINANT',
                               'rate_sensitivity':'MODERATE','primary_risk':'default_and_illiquidity',
                               'benchmark_return':8.5,'return_ceiling':11.0,'stress_risk':'HIGH',
                               'suitable_for':'High-conviction credit analysts only.',
                               'avoid_if':'Anyone who cannot analyse individual bond credit.'},
    'banking and psu':        {'duration_band':(1.0,4.0),'credit_profile':'AAA_PSU_BANK_DOMINANT',
                               'rate_sensitivity':'MODERATE','primary_risk':'rate_and_spread',
                               'benchmark_return':7.0,'return_ceiling':9.0,'stress_risk':'LOW_MODERATE',
                               'suitable_for':'Conservative, slightly higher yield than overnight.',
                               'avoid_if':'Lower-rated PSU bonds chased for yield.'},
    'gilt fund':              {'duration_band':(5.0,15.0),'credit_profile':'SOVEREIGN_ONLY',
                               'rate_sensitivity':'VERY_HIGH','primary_risk':'interest_rate_risk_pure',
                               'benchmark_return':7.0,'return_ceiling':14.0,'stress_risk':'HIGH',
                               'suitable_for':'Rate cut play, zero credit risk.',
                               'avoid_if':'Stable rate environment.'},
    'floater fund':           {'duration_band':(0.0,1.0),'credit_profile':'AAA_DOMINANT',
                               'rate_sensitivity':'INVERSE','primary_risk':'credit_on_floater_paper',
                               'benchmark_return':6.5,'return_ceiling':8.0,'stress_risk':'LOW',
                               'suitable_for':'Rising rate environment.',
                               'avoid_if':'Rate cut cycle.'},
    'default':                {'duration_band':(1.0,4.0),'credit_profile':'MIXED',
                               'rate_sensitivity':'MODERATE','primary_risk':'unknown',
                               'benchmark_return':7.0,'return_ceiling':9.0,'stress_risk':'MODERATE',
                               'suitable_for':'Assess based on actual holdings.',
                               'avoid_if':'Without understanding holdings and duration.'},
}

def get_debt_profile(category):
    cat = (category or '').lower()
    priority = ['overnight fund','liquid fund','ultra short duration','low duration',
                'money market','short duration','medium to long duration','medium duration',
                'long duration','dynamic bond','corporate bond','credit risk fund',
                'banking and psu','gilt fund','floater fund']
    for k in priority:
        if k in cat:
            return DEBT_PROFILES[k]
    return DEBT_PROFILES['default']

SD_RANGES = {
    'NEGLIGIBLE':(0.0,0.3),'VERY_LOW':(0.2,0.8),'LOW':(0.5,1.5),
    'MODERATE':(1.5,4.0),'MODERATE_HIGH':(3.0,6.0),'HIGH':(5.0,10.0),
    'VERY_HIGH':(8.0,15.0),'VARIABLE':(1.0,10.0),'INVERSE':(0.5,2.0),
}


# ============================================================================
# DATA FETCHING (NAV + Metadata + AMFI Holdings)
# ============================================================================

class MFDataFetcher:
    MFAPI        = "https://api.mfapi.in/mf"
    CAPTNO_BASE  = "https://mf.captnemo.in"
    AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
    AMFI_PORT_URL= "https://portal.amfiindia.com/DownloadPortfolioDetails.aspx"

    _isin_cache:  dict = {}
    _amfi_loaded: bool = False

    @staticmethod
    def _load_amfi_isin_map():
        if MFDataFetcher._amfi_loaded:
            return
        try:
            r = requests.get(MFDataFetcher.AMFI_NAV_URL, timeout=20)
            r.raise_for_status()
            for line in r.text.splitlines():
                parts = line.strip().split(';')
                if len(parts) < 3:
                    continue
                try:
                    code  = int(parts[0].strip())
                    isin1 = parts[1].strip()
                    isin2 = parts[2].strip()
                    isin  = isin1 if (isin1.startswith('INF') and len(isin1)==12) else isin2
                    if isin.startswith('INF') and len(isin)==12:
                        MFDataFetcher._isin_cache[code] = isin
                except (ValueError, IndexError):
                    continue
            MFDataFetcher._amfi_loaded = True
        except Exception as e:
            _log.error(
                f"🚨 AMFI NAV URL fetch FAILED — MF ISIN mapping unavailable. "
                f"Fund briefs will be degraded. Error: {e}",
                exc_info=True
            )

    @staticmethod
    def get_isin(scheme_code):
        MFDataFetcher._load_amfi_isin_map()
        return MFDataFetcher._isin_cache.get(scheme_code, '')

    @staticmethod
    def search(query, top=10):
        try:
            r = requests.get(f"{MFDataFetcher.MFAPI}/search",
                             params={"q": query}, timeout=15)
            r.raise_for_status()
            data = r.json()
            if not data:
                return pd.DataFrame()
            df = pd.DataFrame(data[:top])
            df = df.rename(columns={'schemeCode':'scheme_code','schemeName':'scheme_name'})
            for col in ['scheme_code','scheme_name']:
                if col not in df.columns:
                    df[col] = ''
            # Add optional metadata columns if present
            for src, dst in [('fundHouse','fund_house'),('schemeType','scheme_type'),('schemeCategory','scheme_category')]:
                df[dst] = df[src] if src in df.columns else ''
            return df[['scheme_code','scheme_name','fund_house','scheme_type','scheme_category']]
        except Exception as e:
            _log.error(f"MF search error: {e}", exc_info=True)
            return pd.DataFrame()

    @staticmethod
    def get_nav_history(scheme_code):
        try:
            r = requests.get(f"{MFDataFetcher.MFAPI}/{scheme_code}", timeout=20)
            r.raise_for_status()
            data = r.json()
            meta = data.get('meta', {})
            raw  = data.get('data', [])
            if not raw:
                return {}, pd.DataFrame()
            df = pd.DataFrame(raw)
            df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
            df['nav']  = pd.to_numeric(df['nav'], errors='coerce')
            df = df.dropna(subset=['nav']).sort_values('date').reset_index(drop=True)
            return meta, df
        except Exception as e:
            _log.error(f"NAV fetch error: {e}", exc_info=True)
            return {}, pd.DataFrame()

    @staticmethod
    def get_fund_metadata(scheme_code):
        result = {'aum_crore':None,'expense_ratio':None,'fund_manager':None,
                  'launch_date':None,'isin':None,'meta_source':'unavailable'}
        isin = MFDataFetcher.get_isin(scheme_code)
        if not isin:
            return result
        result['isin'] = isin
        for url in [f"{MFDataFetcher.CAPTNO_BASE}/mf/{isin}",
                    f"{MFDataFetcher.CAPTNO_BASE}/{isin}"]:
            try:
                r = requests.get(url, timeout=12)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and data:
                        data = data[0]
                    if isinstance(data, dict) and data:
                        result['aum_crore']    = _sf(data.get('aum'))
                        result['expense_ratio']= _sf(data.get('expense_ratio'))
                        result['fund_manager'] = data.get('fund_manager')
                        result['launch_date']  = data.get('launch_date') or data.get('start_date')
                        result['meta_source']  = 'mf.captnemo.in'
                        break
            except Exception:
                continue
        return result

    @staticmethod
    def get_portfolio_holdings(scheme_code):
        """
        Phase 3: Fetch monthly portfolio holdings from AMFI.
        AMFI mandates monthly disclosure for all schemes.
        Returns list of holdings with company, sector, weight.
        """
        result = {
            'available':     False,
            'as_of':         None,
            'holdings':      [],        # list of {name, isin, sector, pct_nav, value_cr}
            'sector_alloc':  {},        # {sector: pct_nav}
            'top10_pct':     None,
            'top5_pct':      None,
            'cash_pct':      None,
            'total_stocks':  0,
            'source':        None,
        }

        isin = MFDataFetcher.get_isin(scheme_code)
        if not isin:
            return result

        # Try AMFI portfolio download
        # AMFI monthly portfolio disclosure text format
        try:
            today = datetime.now()
            # Try current month first, then previous month
            for offset in [0, 1, 2]:
                month_date = today - relativedelta(months=offset)
                month_str  = month_date.strftime('%b-%Y')

                url = (f"{MFDataFetcher.AMFI_PORT_URL}"
                       f"?mf={scheme_code}&tp=1")
                headers = {"User-Agent": "Mozilla/5.0"}
                r = requests.get(url, headers=headers, timeout=15)

                if r.status_code == 200 and len(r.content) > 500:
                    parsed = MFDataFetcher._parse_amfi_portfolio(
                        r.content.decode('utf-8', errors='ignore'), scheme_code)
                    if parsed['available']:
                        return parsed

            # Fallback: try the scheme-specific URL pattern
            isin_url = (f"https://www.amfiindia.com/modules/"
                        f"PortfolioDetails?pmfId={scheme_code}")
            r = requests.get(isin_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if r.status_code == 200 and len(r.content) > 500:
                parsed = MFDataFetcher._parse_amfi_portfolio(
                    r.content.decode('utf-8', errors='ignore'), scheme_code)
                if parsed['available']:
                    return parsed

        except Exception:


            _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)

        return result

    @staticmethod
    def _parse_amfi_portfolio(text, scheme_code):
        """
        Parses AMFI monthly portfolio disclosure text.
        AMFI format varies by AMC but common patterns exist.
        Returns structured holdings dict.
        """
        result = {
            'available':False,'as_of':None,'holdings':[],
            'sector_alloc':{},'top10_pct':None,'top5_pct':None,
            'cash_pct':None,'total_stocks':0,'source':'amfi',
        }

        if not text or len(text) < 100:
            return result

        lines   = [l.strip() for l in text.splitlines() if l.strip()]
        holdings= []
        sectors = {}

        # Detect delimiter
        delim = '|' if any('|' in l for l in lines[:20]) else ','

        for line in lines:
            parts = [p.strip() for p in line.split(delim)]
            if len(parts) < 4:
                continue

            # Skip header lines
            if any(kw in parts[0].lower() for kw in
                   ['scheme','isin','instrument','company name','name of','sr no']):
                continue

            # Try to extract: name, sector, % to nav
            name    = parts[0] if parts[0] else None
            sector  = None
            pct_nav = None
            value   = None

            # Look for percentage in columns
            for p in parts:
                p_clean = p.replace('%','').replace(',','').strip()
                try:
                    val = float(p_clean)
                    if 0.01 < val < 50:   # reasonable % of NAV
                        pct_nav = val
                    elif val > 50:        # market value in crores
                        value = val
                except ValueError:
                    if len(p) > 3 and name and p != name:
                        sector = p

            if name and pct_nav and pct_nav > 0:
                holdings.append({
                    'name':    name[:60],
                    'isin':    parts[1] if len(parts[1]) == 12 else None,
                    'sector':  sector,
                    'pct_nav': round(pct_nav, 2),
                    'value_cr':round(value, 0) if value else None,
                })
                if sector:
                    sectors[sector] = sectors.get(sector, 0) + pct_nav

        if len(holdings) < 3:
            return result

        # Sort by weight
        holdings.sort(key=lambda x: x['pct_nav'], reverse=True)

        result['available']    = True
        result['holdings']     = holdings
        result['sector_alloc'] = dict(sorted(sectors.items(),
                                             key=lambda x: x[1], reverse=True))
        result['total_stocks'] = len(holdings)
        result['top5_pct']     = round(sum(h['pct_nav'] for h in holdings[:5]),  1)
        result['top10_pct']    = round(sum(h['pct_nav'] for h in holdings[:10]), 1)

        # Look for cash/other
        for h in holdings:
            if any(kw in h['name'].lower() for kw in
                   ['cash', 'cblo', 'net receivable', 'money market']):
                result['cash_pct'] = h['pct_nav']
                break

        return result


def _sf(val):
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


# ============================================================================
# PORTFOLIO OVERLAP ENGINE (Phase 3)
# ============================================================================

class PortfolioOverlapEngine:
    """
    Phase 3: Detects true diversification between funds.
    The question it answers: if I hold Fund A and Fund B together,
    am I actually diversified or just paying two expense ratios
    for the same exposure?
    """

    @staticmethod
    def calculate_overlap(holdings_a, holdings_b, fund_a_name, fund_b_name):
        """
        Computes stock-level and sector-level overlap.
        Overlap score = sum of min(wt_A, wt_B) for each common stock.
        100% = identical portfolios. 0% = no common holdings.
        """
        if not holdings_a or not holdings_b:
            return {'available': False, 'reason': 'Holdings data unavailable for one or both funds'}

        # Build weight dicts: name → pct_nav
        def build_dict(holdings):
            d = {}
            for h in holdings:
                name = h['name'].lower().strip()
                # Normalise common suffixes
                for sfx in [' ltd', ' limited', ' ltd.', ' inc', ' corp']:
                    name = name.replace(sfx, '')
                d[name] = h['pct_nav']
            return d

        dict_a = build_dict(holdings_a)
        dict_b = build_dict(holdings_b)

        # ISIN-based match (more accurate)
        isin_a = {h['isin']: h['pct_nav'] for h in holdings_a if h.get('isin')}
        isin_b = {h['isin']: h['pct_nav'] for h in holdings_b if h.get('isin')}

        common_isins = set(isin_a.keys()) & set(isin_b.keys())
        common_names = set(dict_a.keys()) & set(dict_b.keys())

        # Use ISIN if available, else name match
        if common_isins:
            common_stocks = [
                {'identifier': isin,
                 'weight_a':   isin_a[isin],
                 'weight_b':   isin_b[isin],
                 'overlap_contribution': min(isin_a[isin], isin_b[isin])}
                for isin in common_isins
            ]
        else:
            # Find holding name for display
            name_to_display_a = {
                h['name'].lower().strip().replace(' ltd','').replace(' limited',''): h['name']
                for h in holdings_a
            }
            common_stocks = [
                {'identifier': name_to_display_a.get(name, name),
                 'weight_a':   dict_a[name],
                 'weight_b':   dict_b[name],
                 'overlap_contribution': min(dict_a[name], dict_b[name])}
                for name in common_names
            ]

        common_stocks.sort(key=lambda x: x['overlap_contribution'], reverse=True)
        overlap_score = round(sum(s['overlap_contribution'] for s in common_stocks), 1)

        # Sector overlap
        def sector_dict(holdings):
            d = {}
            for h in holdings:
                if h.get('sector'):
                    d[h['sector']] = d.get(h['sector'], 0) + h['pct_nav']
            return d

        sec_a = sector_dict(holdings_a)
        sec_b = sector_dict(holdings_b)
        common_sectors = set(sec_a) & set(sec_b)
        sector_overlap  = round(
            sum(min(sec_a[s], sec_b[s]) for s in common_sectors), 1)

        # Interpretation
        if overlap_score >= 60:
            div_grade = 'VERY_HIGH_OVERLAP'
            div_note  = (f"These two funds share {overlap_score}% of their effective "
                         f"portfolio weight. You are paying two expense ratios for "
                         f"essentially the same exposure. One of them is redundant.")
        elif overlap_score >= 40:
            div_grade = 'HIGH_OVERLAP'
            div_note  = (f"Overlap of {overlap_score}% is significant. "
                         f"Meaningful diversification is limited. "
                         f"Consider whether both funds serve different purposes.")
        elif overlap_score >= 20:
            div_grade = 'MODERATE_OVERLAP'
            div_note  = (f"Overlap of {overlap_score}% is moderate. "
                         f"Some diversification benefit exists but is partial.")
        else:
            div_grade = 'LOW_OVERLAP'
            div_note  = (f"Overlap of {overlap_score}% is low. "
                         f"These funds provide genuine diversification.")

        return {
            'available':      True,
            'fund_a_name':    fund_a_name,
            'fund_b_name':    fund_b_name,
            'overlap_score':  overlap_score,
            'sector_overlap': sector_overlap,
            'common_stocks':  common_stocks[:15],
            'n_common':       len(common_stocks),
            'n_total_a':      len(holdings_a),
            'n_total_b':      len(holdings_b),
            'div_grade':      div_grade,
            'div_note':       div_note,
        }

    @staticmethod
    def print_overlap(overlap_data):
        if not overlap_data.get('available'):
            _log.info(f"Overlap unavailable: {overlap_data.get('reason','')}")
            return

        sep = "-" * 70
        _log.info("\n" + "=" * 70)
        _log.info("  FINTELLIGENCE — PORTFOLIO OVERLAP ANALYSIS")
        _log.info("=" * 70)
        _log.info(f"  Fund A : {overlap_data['fund_a_name'][:55]}")
        _log.info(f"  Fund B : {overlap_data['fund_b_name'][:55]}")
        _log.info("=" * 70)
        _log.info(f"\n  OVERLAP SCORE  : {overlap_data['overlap_score']}%")
        _log.info(f"  SECTOR OVERLAP : {overlap_data['sector_overlap']}%")
        _log.info(f"  GRADE          : {overlap_data['div_grade'].replace('_',' ')}")
        _log.info(f"\n  {overlap_data['div_note']}")
        _log.info(f"\n  Common holdings: {overlap_data['n_common']} "
              f"(A has {overlap_data['n_total_a']}, B has {overlap_data['n_total_b']})")

        if overlap_data['common_stocks']:
            _log.info(f"\n  TOP OVERLAPPING STOCKS:")
            _log.info(f"  {'Stock':<35} {'Wt in A':>8} {'Wt in B':>8} {'Overlap':>8}")
            _log.info(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8}")
            for s in overlap_data['common_stocks'][:10]:
                name = str(s['identifier'])[:34]
                _log.info(f"  {name:<35} {s['weight_a']:>7.1f}% {s['weight_b']:>7.1f}% "
                      f"{s['overlap_contribution']:>7.1f}%")
        _log.info("=" * 70)


# ============================================================================
# RETURN ENGINE (Phase 1)
# ============================================================================

class ReturnEngine:

    @staticmethod
    def cagr(nav_df, years=None):
        if len(nav_df) < 2:
            return np.nan
        df = nav_df
        if years:
            cutoff = nav_df['date'].max() - timedelta(days=int(years*365))
            df = nav_df[nav_df['date'] >= cutoff]
            if len(df) < 10:
                return np.nan
        s, e = df['nav'].iloc[0], df['nav'].iloc[-1]
        n = (df['date'].iloc[-1] - df['date'].iloc[0]).days / 365.25
        if n <= 0 or s <= 0:
            return np.nan
        return round(((e/s)**(1/n)-1)*100, 2)

    @staticmethod
    def rolling_returns(nav_df, window_years, bench_ret=8.0):
        wd = int(window_years*365)
        results = []
        for i in range(len(nav_df)):
            end_row = nav_df[nav_df['date'] >= nav_df['date'].iloc[i]+timedelta(days=wd)]
            if end_row.empty:
                break
            s, e = nav_df['nav'].iloc[i], end_row['nav'].iloc[0]
            y = (end_row['date'].iloc[0]-nav_df['date'].iloc[i]).days/365.25
            if y > 0 and s > 0:
                results.append(((e/s)**(1/y)-1)*100)
        if len(results) < 5:
            return {'available':False,'window':f'{int(window_years)}Y','n_obs':len(results)}
        a = np.array(results)
        return {
            'available':True,'window':f'{int(window_years)}Y','n_obs':len(a),
            'mean':round(float(np.mean(a)),2),'median':round(float(np.median(a)),2),
            'min':round(float(np.min(a)),2),'max':round(float(np.max(a)),2),
            'pct_positive':round(float((a>0).mean()*100),1),
            'pct_above_8': round(float((a>8).mean()*100),1),
            'pct_above_12':round(float((a>12).mean()*100),1),
        }

    @staticmethod
    def std_dev(nav_df, years=3):
        cutoff = nav_df['date'].max()-timedelta(days=int(years*365))
        df = nav_df[nav_df['date'] >= cutoff]
        if len(df) < 30:
            df = nav_df
        r = np.log(df['nav']/df['nav'].shift(1)).dropna()
        return round(float(r.std()*np.sqrt(TRADING_DAYS)*100),2)

    @staticmethod
    def max_drawdown(nav_df):
        nav=nav_df['nav'].values; peak=np.maximum.accumulate(nav)
        dd=(nav-peak)/peak*100; idx=int(np.argmin(dd)); pidx=int(np.argmax(nav[:idx+1]))
        return {'max_drawdown_pct':round(float(np.min(dd)),2),
                'peak_date':nav_df['date'].iloc[pidx].strftime('%b %Y'),
                'trough_date':nav_df['date'].iloc[idx].strftime('%b %Y')}

    @staticmethod
    def drawdown_in_period(nav_df, start, end):
        df=nav_df[(nav_df['date']>=start)&(nav_df['date']<=end)]
        if len(df)<2: return np.nan
        return round((df['nav'].min()-df['nav'].max())/df['nav'].max()*100,2)

    @staticmethod
    def sip_xirr(nav_df, amount=SIP_AMOUNT):
        end=nav_df['date'].max(); start=end-relativedelta(years=3)
        df=nav_df[nav_df['date']>=start].copy()
        if len(df)<30: return np.nan
        dates,cfs,units=[],[],0.0
        for d in pd.date_range(start=start,end=end,freq='MS'):
            cl=df.iloc[(df['date']-d).abs().argsort()[:1]]
            if cl.empty: continue
            u=amount/cl['nav'].iloc[0]; units+=u
            cfs.append(-amount); dates.append(cl['date'].iloc[0].to_pydatetime())
        if units<=0: return np.nan
        cfs.append(units*df['nav'].iloc[-1]); dates.append(df['date'].iloc[-1].to_pydatetime())
        try:
            if PYXIRR:
                r=_xirr(dates,cfs); return round(float(r)*100,2) if r else np.nan
            ti=amount*(len(dates)-1); ny=(end-start).days/365.25
            return round(((cfs[-1]/ti)**(1/ny)-1)*100,2) if ti and ny else np.nan
        except Exception:
            return np.nan


# ============================================================================
# RISK ENGINE (Phase 1)
# ============================================================================

class RiskEngine:

    @staticmethod
    def _align(f_df, b_df):
        f=f_df.set_index('date')['nav']; b=b_df.set_index('date')['nav']
        ci=f.index.intersection(b.index)
        if len(ci)<30: return pd.Series(dtype=float),pd.Series(dtype=float)
        fr=np.log(f.loc[ci]/f.loc[ci].shift(1)).dropna()
        br=np.log(b.loc[ci]/b.loc[ci].shift(1)).dropna()
        ci2=fr.index.intersection(br.index); return fr.loc[ci2],br.loc[ci2]

    @staticmethod
    def sharpe(nav_df, years=3):
        c=nav_df['date'].max()-timedelta(days=int(years*365))
        r=np.log(nav_df[nav_df['date']>=c]['nav']/nav_df[nav_df['date']>=c]['nav'].shift(1)).dropna()
        if len(r)<30: return np.nan
        av=r.std()*np.sqrt(TRADING_DAYS)
        return round(float((r.mean()*TRADING_DAYS-RISK_FREE_RATE)/av),2) if av else np.nan

    @staticmethod
    def sortino(nav_df, years=3):
        c=nav_df['date'].max()-timedelta(days=int(years*365))
        r=np.log(nav_df[nav_df['date']>=c]['nav']/nav_df[nav_df['date']>=c]['nav'].shift(1)).dropna()
        if len(r)<30: return np.nan
        dn=r[r<0].std()*np.sqrt(TRADING_DAYS)
        return round(float((r.mean()*TRADING_DAYS-RISK_FREE_RATE)/dn),2) if dn else np.nan

    @staticmethod
    def beta_alpha(fund_df, bench_df, years=3):
        end=fund_df['date'].max(); start=end-timedelta(days=int(years*365))
        fr,br=RiskEngine._align(fund_df[fund_df['date']>=start],bench_df[bench_df['date']>=start])
        if len(fr)<30: return {'beta':np.nan,'alpha':np.nan,'r_squared':np.nan}
        sl,_,rv,_,_=stats.linregress(br.values,fr.values)
        alpha=(fr.mean()*TRADING_DAYS-(RISK_FREE_RATE+sl*(br.mean()*TRADING_DAYS-RISK_FREE_RATE)))*100
        return {'beta':round(float(sl),3),'alpha':round(float(alpha),2),'r_squared':round(float(rv**2),3)}

    @staticmethod
    def information_ratio(fund_df, bench_df, years=3):
        end=fund_df['date'].max(); start=end-timedelta(days=int(years*365))
        fr,br=RiskEngine._align(fund_df[fund_df['date']>=start],bench_df[bench_df['date']>=start])
        if len(fr)<30: return np.nan
        ar=fr-br; te=ar.std()*np.sqrt(TRADING_DAYS)
        return round(float(ar.mean()*TRADING_DAYS/te),2) if te else np.nan

    @staticmethod
    def capture_ratios(fund_df, bench_df, years=3):
        end=fund_df['date'].max(); start=end-timedelta(days=int(years*365))
        f=(fund_df[fund_df['date']>=start].set_index('date')['nav']
           .resample('ME').last().pct_change().dropna())
        b=(bench_df[bench_df['date']>=start].set_index('date')['nav']
           .resample('ME').last().pct_change().dropna())
        ci=f.index.intersection(b.index)
        if len(ci)<12: return {'upside_capture':np.nan,'downside_capture':np.nan}
        f,b=f.loc[ci],b.loc[ci]; up,dn=b>0,b<0
        if up.sum()==0 or dn.sum()==0: return {'upside_capture':np.nan,'downside_capture':np.nan}
        return {'upside_capture':round(float(f[up].mean()/b[up].mean()*100),1),
                'downside_capture':round(float(f[dn].mean()/b[dn].mean()*100),1)}


# ============================================================================
# DEBT ENGINES (Phase 5)
# ============================================================================

class DebtReturnEngine:

    @staticmethod
    def cagr(nav_df, years=None):
        return ReturnEngine.cagr(nav_df, years)

    @staticmethod
    def rolling_returns(nav_df, window_years, benchmark_return=7.0):
        wd=int(window_years*365); results=[]
        for i in range(len(nav_df)):
            end_row=nav_df[nav_df['date']>=nav_df['date'].iloc[i]+timedelta(days=wd)]
            if end_row.empty: break
            s,e=nav_df['nav'].iloc[i],end_row['nav'].iloc[0]
            y=(end_row['date'].iloc[0]-nav_df['date'].iloc[i]).days/365.25
            if y>0 and s>0: results.append(((e/s)**(1/y)-1)*100)
        if len(results)<5:
            return {'available':False,'window':f'{int(window_years)}Y','n_obs':len(results)}
        a=np.array(results)
        return {
            'available':True,'window':f'{int(window_years)}Y','n_obs':len(a),
            'mean':round(float(np.mean(a)),2),'median':round(float(np.median(a)),2),
            'min':round(float(np.min(a)),2),'max':round(float(np.max(a)),2),
            'pct_positive':round(float((a>0).mean()*100),1),
            'pct_above_rf': round(float((a>RISK_FREE_RATE*100).mean()*100),1),
            'pct_above_bench':round(float((a>benchmark_return).mean()*100),1),
            'benchmark_used':benchmark_return,
        }

    @staticmethod
    def std_dev(nav_df, years=3):
        return ReturnEngine.std_dev(nav_df, years)

    @staticmethod
    def sharpe(nav_df, years=3):
        return RiskEngine.sharpe(nav_df, years)

    @staticmethod
    def max_drawdown(nav_df):
        return ReturnEngine.max_drawdown(nav_df)

    @staticmethod
    def drawdown_in_period(nav_df, start, end):
        return ReturnEngine.drawdown_in_period(nav_df, start, end)

    @staticmethod
    def negative_months(nav_df, years=3):
        c=nav_df['date'].max()-timedelta(days=int(years*365))
        m=(nav_df[nav_df['date']>=c].set_index('date')['nav']
           .resample('ME').last().pct_change().dropna())
        if len(m)<6: return np.nan
        return round(float((m<0).mean()*100),1)

    @staticmethod
    def ytm_estimate(nav_df):
        c=nav_df['date'].max()-timedelta(days=180)
        df=nav_df[nav_df['date']>=c]
        if len(df)<20: return {'ytm_estimate':np.nan,'note':'Insufficient data'}
        s,e=df['nav'].iloc[0],df['nav'].iloc[-1]
        days=(df['date'].iloc[-1]-df['date'].iloc[0]).days
        if days<=0 or s<=0: return {'ytm_estimate':np.nan,'note':'Calc error'}
        ann=((e/s)**(365/days)-1)*100
        return {'ytm_estimate':round(ann,2),
                'note':'6M annualised NAV return (YTM proxy)',
                'period':f"{df['date'].iloc[0].strftime('%b %Y')} to {df['date'].iloc[-1].strftime('%b %Y')}"}

    @staticmethod
    def rate_sensitivity_test(nav_df):
        periods = {
            'rate_hike_2022_23': ('2022-05-01','2023-01-31','RBI hike +250bps'),
            'rate_cut_2019_20':  ('2019-02-01','2020-03-31','RBI cut -210bps'),
            'taper_tantrum_2013':('2013-05-01','2013-08-31','Taper tantrum'),
            'il_fs_2018':        ('2018-09-01','2018-12-31','IL&FS crisis'),
            'franklin_2020':     ('2020-04-01','2020-05-31','Franklin closure'),
        }
        results = {}
        for key,(start,end,label) in periods.items():
            dd = ReturnEngine.drawdown_in_period(nav_df, start, end)
            df = nav_df[(nav_df['date']>=start)&(nav_df['date']<=end)]
            tr = round((df['nav'].iloc[-1]/df['nav'].iloc[0]-1)*100,2) if len(df)>=5 else np.nan
            results[key] = {'label':label,'drawdown':dd,'total_return':tr}
        return results

    @staticmethod
    def sip_xirr(nav_df, amount=SIP_AMOUNT):
        return ReturnEngine.sip_xirr(nav_df, amount)


class DebtAnomalyDetector:

    @staticmethod
    def check_sd(sd, rate_sensitivity):
        if np.isnan(sd):
            return {'flag':'DATA_MISSING','message':'','severity':'UNKNOWN'}
        exp = SD_RANGES.get(rate_sensitivity,(0.5,5.0))
        if sd > exp[1]*1.5:
            return {'flag':'HIGH_VOLATILITY','severity':'RED',
                    'message':f"SD {sd:.1f}% well above {exp[1]:.1f}% ceiling — hidden duration/credit risk"}
        elif sd > exp[1]:
            return {'flag':'ELEVATED','severity':'AMBER',
                    'message':f"SD {sd:.1f}% above {exp[1]:.1f}% ceiling — monitor holdings"}
        else:
            return {'flag':'NORMAL','severity':'GREEN',
                    'message':f"SD {sd:.1f}% within expected range for this category"}

    @staticmethod
    def check_expense_efficiency(cagr3, expense_ratio, benchmark_return):
        if np.isnan(cagr3) or expense_ratio is None:
            return {'flag':'DATA_MISSING','severity':'UNKNOWN','message':''}
        spread = cagr3 - RISK_FREE_RATE*100
        er = expense_ratio
        if spread < er:
            return {'flag':'EXPENSE_EATING_SPREAD','severity':'RED',
                    'message':f"Spread over RF {spread:.1f}% barely covers ER {er:.2f}% — direct plan or passive is better"}
        elif spread < er*2:
            return {'flag':'THIN_SPREAD','severity':'AMBER',
                    'message':f"Spread over RF {spread:.1f}% is only {spread/er:.1f}x the ER {er:.2f}% — thin margin"}
        return {'flag':'ADEQUATE','severity':'GREEN',
                'message':f"3Y return {cagr3:.1f}% generates {spread:.1f}% above RF after {er:.2f}% ER"}


# ============================================================================
# INDIA MACRO FETCHER (Phase 4)
# ============================================================================

class IndiaMacroFetcher:

    WB_API = "https://api.worldbank.org/v2/country/IN/indicator"

    @staticmethod
    def fetch():
        result = {
            'repo_rate':6.25,'reverse_repo':3.35,'crr':4.0,
            'rbi_stance':'NEUTRAL','cpi_latest':None,'cpi_month':None,
            'rbi_cpi_target':4.0,'gdp_growth_latest':None,'gdp_quarter':None,
            'cpi_vs_target':None,'rate_cut_room':'UNKNOWN',
            'growth_momentum':'UNKNOWN','macro_stance':'UNKNOWN',
            'source':'fallback',
            'note':'RBI cut repo 25bps to 6.25% in Feb 2025. Stance neutral.',
        }
        try:
            r=requests.get(f"{IndiaMacroFetcher.WB_API}/FP.CPI.TOTL.ZG",
                           params={"format":"json","mrv":4,"per_page":4},timeout=10)
            if r.status_code==200:
                data=r.json()
                if len(data)>=2 and data[1]:
                    for entry in data[1]:
                        if entry.get('value') is not None:
                            result['cpi_latest']=round(float(entry['value']),1)
                            result['cpi_month']=entry.get('date','')
                            break
        except Exception:

            _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)
        try:
            r=requests.get(f"{IndiaMacroFetcher.WB_API}/NY.GDP.MKTP.KD.ZG",
                           params={"format":"json","mrv":2,"per_page":2},timeout=10)
            if r.status_code==200:
                data=r.json()
                if len(data)>=2 and data[1]:
                    for entry in data[1]:
                        if entry.get('value') is not None:
                            result['gdp_growth_latest']=round(float(entry['value']),1)
                            result['gdp_quarter']=entry.get('date','')
                            break
        except Exception:

            _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)

        cpi=result['cpi_latest']; repo=result['repo_rate']; gdp=result['gdp_growth_latest']
        if cpi is not None:
            result['cpi_vs_target']=round(cpi-result['rbi_cpi_target'],1)
        if cpi is not None and repo is not None:
            if cpi<4.5 and cpi>2.0:   result['rate_cut_room']='AVAILABLE';  result['macro_stance']='ACCOMMODATIVE_POSSIBLE'
            elif cpi<5.5:              result['rate_cut_room']='LIMITED';    result['macro_stance']='ON_HOLD'
            else:                      result['rate_cut_room']='NONE';       result['macro_stance']='HAWKISH_BIAS'
        if gdp is not None:
            result['growth_momentum']=('STRONG' if gdp>=7 else 'MODERATE' if gdp>=5.5
                                       else 'SLUGGISH' if gdp>=4 else 'WEAK')
        return result


# ============================================================================
# INDIA VIX FETCHER (Phase 4)
# ============================================================================

class IndiaVIXFetcher:
    """
    India VIX — NSE public JSON API.
    No API key. No rate limit. Works on any server.
    """
    _HDR = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept':     'application/json',
        'Referer':    'https://www.nseindia.com',
    }

    @staticmethod
    def get_live() -> float:
        """Returns current India VIX from NSE allIndices endpoint."""
        try:
            s = requests.Session()
            s.get('https://www.nseindia.com', headers=IndiaVIXFetcher._HDR, timeout=8)
            time.sleep(0.3)
            r = s.get('https://www.nseindia.com/api/allIndices',
                      headers=IndiaVIXFetcher._HDR, timeout=8)
            if r.status_code == 200:
                for item in r.json().get('data', []):
                    if item.get('index') == 'INDIA VIX':
                        return float(item.get('last', 0))
        except Exception:

            _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)
        return np.nan

    @staticmethod
    def get_percentile(vix, days=365) -> dict:
        """Returns VIX percentile using NSE historical VIX data."""
        if (isinstance(vix, float) and np.isnan(vix)) or vix is None:
            return {'percentile_1y': np.nan, 'regime': 'UNKNOWN',
                    '1y_min': np.nan, '1y_max': np.nan, '1y_mean': np.nan}
        vals = np.array([])
        try:
            end   = datetime.now()
            start = end - timedelta(days=days + 30)
            url = (
                f'https://www.nseindia.com/api/historical/vixHistory'
                f'?startDate={start.strftime("%d-%b-%Y")}'
                f'&endDate={end.strftime("%d-%b-%Y")}'
            )
            s = requests.Session()
            s.get('https://www.nseindia.com', headers=IndiaVIXFetcher._HDR, timeout=8)
            r = s.get(url, headers=IndiaVIXFetcher._HDR, timeout=15)
            if r.status_code == 200:
                data = r.json().get('data', [])
                vals = np.array(
                    [float(row['EOD_CLOSE_PRICE']) for row in data
                     if row.get('EOD_CLOSE_PRICE')],
                    dtype=float
                )
        except Exception:

            _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)
        if len(vals) < 20:
            return {'percentile_1y': np.nan, 'regime': 'UNKNOWN',
                    '1y_min': np.nan, '1y_max': np.nan, '1y_mean': np.nan}
        pct    = round(float((vals < vix).mean() * 100), 1)
        regime = ('RICH'     if pct >= 80 else
                  'ELEVATED' if pct >= 60 else
                  'NORMAL'   if pct >= 35 else 'CHEAP')
        return {
            'percentile_1y': pct, 'regime': regime,
            '1y_min':  round(float(vals.min()), 2),
            '1y_max':  round(float(vals.max()), 2),
            '1y_mean': round(float(vals.mean()), 2),
        }


# ============================================================================
# FII DATA FETCHER (Phase 4) — Cash + Futures
# ============================================================================

class FIIDataFetcher:

    NSE_HDR = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    @staticmethod
    def _recent_dates(n=5):
        dates=[]; d=datetime.now()
        if d.hour<16: d-=timedelta(days=1)
        while len(dates)<n:
            if d.weekday()<5: dates.append(d)
            d-=timedelta(days=1)
        return dates

    @staticmethod
    def fetch_cash():
        result={'available':False,'date':None,'fii_net_cr':np.nan,
                'dii_net_cr':np.nan,'direction':'UNKNOWN','5d_net_cr':np.nan}
        try:
            session=requests.Session()
            session.get("https://www.nseindia.com",headers=FIIDataFetcher.NSE_HDR,timeout=8)
            time.sleep(0.5)
            r=session.get("https://www.nseindia.com/api/fiidiiTradeReact",
                          headers={**FIIDataFetcher.NSE_HDR,
                                   "Referer":"https://www.nseindia.com/"},timeout=10)
            if r.status_code==200:
                data=r.json()
                if data:
                    latest=data[0] if isinstance(data,list) else data
                    fb=float(str(latest.get('fiiBuy','0')).replace(',',''))
                    fs=float(str(latest.get('fiiSell','0')).replace(',',''))
                    db=float(str(latest.get('diiBuy','0')).replace(',',''))
                    ds=float(str(latest.get('diiSell','0')).replace(',',''))
                    if fb==0 and fs==0:
                        result['available']=False
                    else:
                        fn=round(fb-fs,0); dn=round(db-ds,0)
                        result.update({'available':True,'date':latest.get('date',''),
                                       'fii_net_cr':fn,'dii_net_cr':dn})
                        if isinstance(data,list) and len(data)>=5:
                            fd=sum(float(str(d.get('fiiBuy','0')).replace(',',''))-
                                   float(str(d.get('fiiSell','0')).replace(',',''))
                                   for d in data[:5])
                            result['5d_net_cr']=round(fd,0)
                        result['direction']=('STRONG_BUYING' if fn>2000 else 'BUYING' if fn>500
                                             else 'NEUTRAL' if fn>-500 else 'SELLING'
                                             if fn>-2000 else 'STRONG_SELLING')
        except Exception:

            _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)
        return result

    @staticmethod
    def fetch_futures():
        result={'available':False,'date':None,'fii_fut_net':np.nan,
                'fii_call_net':np.nan,'fii_put_net':np.nan,
                'flow_regime':'UNKNOWN','sentiment':'NEUTRAL','conviction':'LOW'}
        for date_obj in FIIDataFetcher._recent_dates():
            ds=date_obj.strftime('%d%m%Y')
            url=f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{ds}.csv"
            try:
                r=requests.get(url,headers=FIIDataFetcher.NSE_HDR,timeout=10)
                if r.status_code!=200: continue
                content=r.content.decode('utf-8')
                if "Future Index Long" not in content: continue
                lines=content.splitlines(); skip=0
                for i,line in enumerate(lines[:20]):
                    if "Future Index Long" in line: skip=i; break
                df=pd.read_csv(io.StringIO(content),skiprows=skip)
                df.columns=df.columns.str.strip()
                def g(row,col):
                    try: return float(str(row[col]).replace(',','').strip())
                    except: return 0.0
                mask=df['Client Type'].astype(str).str.contains('FII',case=False,na=False)
                if mask.sum()==0: continue
                fii_row=df[mask].iloc[0]
                fl=g(fii_row,'Future Index Long'); fs_=g(fii_row,'Future Index Short')
                cl=g(fii_row,'Option Index Call Long'); cs=g(fii_row,'Option Index Call Short')
                pl=g(fii_row,'Option Index Put Long'); ps=g(fii_row,'Option Index Put Short')
                fn=fl-fs_; cn=cl-cs; pn=pl-ps
                result.update({'available':True,'date':date_obj.strftime('%d-%b-%Y'),
                                'fii_fut_net':round(fn,0),'fii_call_net':round(cn,0),
                                'fii_put_net':round(pn,0)})
                fb=fn>0; ob=cn>pn
                if fb and ob:    result['flow_regime']='AGGRESSIVE_BULL'
                elif not fb and not ob: result['flow_regime']='AGGRESSIVE_BEAR'
                elif fb and not ob:     result['flow_regime']='GUARDED_BULL'
                else:                   result['flow_regime']='CONTRARIAN_TRAP'
                result['sentiment']='BULLISH' if fn>0 else 'BEARISH'
                an=abs(fn)
                result['conviction']=('VERY_HIGH' if an>150000 else 'HIGH' if an>80000
                                      else 'MODERATE' if an>40000 else 'LOW')
                break
            except Exception:
                continue
        return result

    @staticmethod
    def fetch():
        cash=FIIDataFetcher.fetch_cash(); fut=FIIDataFetcher.fetch_futures()
        ca=cash.get('available',False); cd=cash.get('direction','UNKNOWN')
        fr=fut.get('flow_regime','UNKNOWN')
        if not ca:
            sig=('FUTURES_ONLY_BEARISH' if fr=='AGGRESSIVE_BEAR'
                 else 'FUTURES_ONLY_BULLISH' if fr=='AGGRESSIVE_BULL'
                 else 'CONTRARIAN_TRAP' if fr=='CONTRARIAN_TRAP'
                 else 'FUTURES_ONLY_NEUTRAL')
        elif cd in ('STRONG_SELLING','SELLING') and fr=='AGGRESSIVE_BEAR': sig='GENUINE_BEARISH'
        elif cd in ('STRONG_BUYING','BUYING')   and fr=='AGGRESSIVE_BULL': sig='GENUINE_BULLISH'
        elif cd in ('STRONG_SELLING','SELLING') and fr in ('AGGRESSIVE_BULL','GUARDED_BULL'): sig='SELLING_CASH_HEDGED'
        elif cd in ('STRONG_BUYING','BUYING')   and fr=='AGGRESSIVE_BEAR': sig='BUYING_CASH_HEDGED'
        else: sig='NEUTRAL'
        return {'cash':cash,'futures':fut,'combined_signal':sig}


# ============================================================================
# GLOBAL MACRO FETCHER (Phase 4)
# ============================================================================


# ── Stooq ticker map (free, no key, no rate limit, works on any server) ──────
_STOOQ_TICKERS = {
    'sp500':     '^spx',
    'nasdaq':    '^ndx',
    'us_vix':    '^vix',
    'dxy':       'dxy.f',
    'us_10y':    '10yt.b',
    'crude_wti': 'cl.f',
    'gold':      'gc.f',
    'nikkei':    '^nkx',
    'hang_seng': '^hsi',
    'usd_inr':   'usdinr',
}

def _stooq_fetch(ticker: str, days: int = 10) -> pd.DataFrame:
    """Fetch recent daily OHLCV from Stooq. No key, no rate limit."""
    try:
        url = f'https://stooq.com/q/d/l/?s={ticker}&i=d'
        df  = pd.read_csv(url,
                          storage_options={'User-Agent': 'Mozilla/5.0'},
                          parse_dates=['Date'])
        df  = df.sort_values('Date').dropna(subset=['Close'])
        return df.tail(days).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


class GlobalMacroFetcher:
    """
    Global macro signals via Stooq.
    Free · No API key · No rate limit · Works on any server / datacenter.
    Replaces yfinance which is blocked on AWS/datacenter IPs.
    Tickers: SP500, NASDAQ, US VIX, DXY, US 10Y, Crude, Gold, Nikkei, HSI, USD/INR
    """

    @staticmethod
    def fetch() -> dict:
        result = {}
        for name, ticker in _STOOQ_TICKERS.items():
            try:
                df = _stooq_fetch(ticker, days=5)
                if df.empty or len(df) < 2:
                    result[name] = {'price': np.nan, 'change_pct': np.nan, 'direction': 'UNKNOWN'}
                    continue
                price = float(df['Close'].iloc[-1])
                prev  = float(df['Close'].iloc[-2])
                chg   = round((price - prev) / prev * 100, 2) if prev > 0 else np.nan
                dirn  = ('UP'   if not np.isnan(chg) and chg >  0.3 else
                         'DOWN' if not np.isnan(chg) and chg < -0.3 else 'FLAT')
                result[name] = {
                    'price':      round(price, 4),
                    'change_pct': chg,
                    'direction':  dirn,
                }
            except Exception:
                result[name] = {'price': np.nan, 'change_pct': np.nan, 'direction': 'UNKNOWN'}

        # Global tone scoring
        ro = ron = 0
        sp  = result.get('sp500', {})
        vix = result.get('us_vix', {})
        gld = result.get('gold', {})
        oil = result.get('crude_wti', {})
        t10 = result.get('us_10y', {})
        dxy = result.get('dxy', {})

        def _safe(d, k): v = d.get(k, np.nan); return None if (isinstance(v,float) and np.isnan(v)) else v

        sp_chg = _safe(sp, 'change_pct')
        if sp_chg is not None:
            if sp_chg < -0.7: ro  += 1
            if sp_chg >  0.7: ron += 1
        vix_p = _safe(vix, 'price')
        if vix_p is not None:
            if vix_p > 25: ro += 2
            elif vix_p > 20: ro += 1
        gld_chg = _safe(gld, 'change_pct')
        if gld_chg and gld_chg > 1.0: ro += 1
        oil_chg = _safe(oil, 'change_pct')
        if oil_chg and oil_chg > 2.5: ro += 1
        t10_p = _safe(t10, 'price')
        if t10_p and t10_p > 4.5: ro += 1
        dxy_chg = _safe(dxy, 'change_pct')
        if dxy_chg and dxy_chg > 0.5: ro += 1

        tone = ('CLEAR'           if ro == 0 and ron >= 1 else
                'CAUTIOUS_NEUTRAL' if ro <= 1                else
                'CAUTIOUS'         if ro == 2                else
                'RISK_OFF')
        result['_meta'] = {
            'available':      True,
            'global_tone':    tone,
            'risk_off_count': ro,
            'risk_on_count':  ron,
            'us_10y_elevated': bool(t10_p and t10_p > 4.5),
            'timestamp':      datetime.now().strftime('%d %b %Y %H:%M'),
            'source':         'Stooq',
        }
        return result


class NewsScanner:

    RSS_FEEDS = {
        'et_markets':       'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
        'et_economy':       'https://economictimes.indiatimes.com/economy/rssfeeds/1373380680.cms',
        'google_rbi':       'https://news.google.com/rss/search?q=RBI+repo+rate+monetary+policy+India&hl=en&gl=IN',
        'google_fed':       'https://news.google.com/rss/search?q=federal+reserve+rate+decision+powell&hl=en&gl=US',
        'google_india_macro':'https://news.google.com/rss/search?q=india+GDP+inflation+CPI+economy&hl=en&gl=IN',
        'google_fii':       'https://news.google.com/rss/search?q=FII+foreign+investors+india+outflow+inflow&hl=en&gl=IN',
        'google_oil':       'https://news.google.com/rss/search?q=crude+oil+opec+price+supply&hl=en&gl=US',
        'ap_business':      'https://feeds.apnews.com/apnews/business',
        'mint_markets':     'https://www.livemint.com/rss/markets',
    }
    VETO_KW = [
        'rbi cuts rate','rbi hikes rate','repo rate cut','repo rate hike','mpc decision',
        'emergency rate','fomc decision','fed raises','fed cuts','circuit breaker',
        'trading halted','market crash','bank collapse','default declared','war declared',
        'nuclear','union budget','us-iran war','iran war','israel iran',
        'rupee record low','rupee all time low','rupee historic low','rupee hits record',
        'oil at $150','oil at $200','crude at $150','crude at $200',
        'emergency meeting','rbi emergency',
    ]
    HIGH_KW = [
        'india cpi','india inflation','india gdp','india growth','non-farm payroll',
        'nfp','us cpi','us inflation','fomc minutes','fed speech','powell speech',
        'rupee falls','rupee hits','fii outflow','fii inflow','nifty falls',
        'sebi order','trade war','tariff','crude spike','oil price',
    ]

    @staticmethod
    def scan(hours=6):
        result={'available':FEEDPARSER,'veto_items':[],'high_items':[],
                'has_veto':False,'has_high':False,'total_scanned':0,'errors':[]}
        if not FEEDPARSER: return result
        from datetime import timezone as _tz; import email.utils
        from concurrent.futures import ThreadPoolExecutor, as_completed
        cutoff=datetime.now(_tz.utc)-timedelta(hours=hours)
        def _fetch(src_url):
            src,url=src_url; import socket; old=socket.getdefaulttimeout()
            try: socket.setdefaulttimeout(8); return src,feedparser.parse(url)
            finally: socket.setdefaulttimeout(old)
        feeds={}
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs={ex.submit(_fetch,(s,u)):s for s,u in NewsScanner.RSS_FEEDS.items()}
            for fut in as_completed(futs,timeout=15):
                try: src,feed=fut.result(timeout=1); feeds[src]=feed
                except Exception as e: result['errors'].append(str(e)[:50])
        for src,feed in feeds.items():
            if not feed: continue
            for entry in feed.entries:
                result['total_scanned']+=1
                pub=getattr(entry,'published',None)
                if pub:
                    try:
                        pt=email.utils.parsedate_to_datetime(pub)
                        if pt.tzinfo is None: pt=pt.replace(tzinfo=_tz.utc)
                        if pt<cutoff: continue
                    except Exception:

                        _log.warning("External data fetch failed — MF brief may be degraded", exc_info=True)
                title=getattr(entry,'title','')
                text=(title+' '+getattr(entry,'summary','')[:300]).lower()
                mv=[kw for kw in NewsScanner.VETO_KW if kw in text]
                if mv:
                    result['veto_items'].append({'title':title,'source':src,'keywords':mv[:2]})
                    result['has_veto']=True; continue
                mh=[kw for kw in NewsScanner.HIGH_KW if kw in text]
                if mh:
                    result['high_items'].append({'title':title,'source':src,'keywords':mh[:2]})
                    result['has_high']=True
        return result


# ============================================================================
# REGIME CONTEXT ENGINE (Phase 4)
# ============================================================================

class RegimeContextEngine:

    @staticmethod
    def build(fund_category, fund_type='equity'):
        _log.info("   India macro..."); im=IndiaMacroFetcher.fetch()
        _log.info("   India VIX...")
        vix=IndiaVIXFetcher.get_live(); vix_p=IndiaVIXFetcher.get_percentile(vix)
        _log.info("   FII (cash + futures)..."); fii=FIIDataFetcher.fetch()
        _log.info("   Global macro (yfinance)..."); macro=GlobalMacroFetcher.fetch()
        _log.info("   News scan..."); news=NewsScanner.scan()
        interp=RegimeContextEngine._interpret(vix,vix_p,fii,macro,im,news,fund_category,fund_type)
        return {'india_macro':im,'india_vix':vix,'vix_percentile':vix_p,
                'fii':fii,'macro':macro,'news':news,'interpretation':interp,
                'timestamp':datetime.now().strftime('%d %b %Y %H:%M IST')}

    @staticmethod
    def _interpret(vix,vix_p,fii,macro,im,news,fund_category,fund_type):
        tone=macro.get('_meta',{}).get('global_tone','UNKNOWN')
        cash=fii.get('cash',{}); futures=fii.get('futures',{})
        combined=fii.get('combined_signal','UNKNOWN')
        repo=im.get('repo_rate'); cpi=im.get('cpi_latest')
        rate_room=im.get('rate_cut_room','UNKNOWN')
        gdp=im.get('gdp_growth_latest'); vix_regime=vix_p.get('regime','UNKNOWN')
        vix_pval=vix_p.get('percentile_1y',np.nan)
        risk_flags=[]; opportunities=[]; implications=[]

        # VIX
        vix_ok = vix is not None and not (isinstance(vix,float) and np.isnan(vix))
        if vix_ok:
            if fund_type=='equity':
                if vix_regime=='RICH':
                    opportunities.append(
                        f"VOLATILITY OPPORTUNITY: VIX {vix:.1f} at {vix_pval:.0f}th percentile — "
                        f"fear is at institutional levels. When VIX exceeds 80th percentile, "
                        f"12-month forward Nifty returns historically average 18-24%. "
                        f"This is when patient equity investors build positions, not reduce them — "
                        f"provided no fundamental deterioration exists.")
                elif vix_regime=='CHEAP':
                    risk_flags.append(
                        f"COMPLACENCY: VIX {vix:.1f} at {vix_pval:.0f}th percentile — "
                        f"market pricing in very little risk. Historically precedes largest drawdowns.")
            else:
                if vix_regime in ('RICH','ELEVATED'):
                    risk_flags.append(
                        f"CREDIT SPREAD RISK: VIX {vix:.1f} elevated — "
                        f"equity volatility historically widens corporate spreads 20-40bps within 2-4 weeks.")

        # FII cash + futures
        cash_net=cash.get('fii_net_cr',np.nan); five_d=cash.get('5d_net_cr',np.nan)
        fut_net=futures.get('fii_fut_net',np.nan); fut_conv=futures.get('conviction','LOW')
        if combined=='GENUINE_BEARISH':
            risk_flags.append(
                f"GENUINE FII BEARISH: Cash selling "
                f"Rs{abs(cash_net):,.0f}Cr AND futures net short {abs(fut_net):,.0f} contracts — "
                f"both confirm capital exit from India. Pattern sustains weakness 2-4 weeks.")
        elif combined=='GENUINE_BULLISH':
            opportunities.append(
                f"GENUINE FII BULLISH: Cash buying Rs{cash_net:,.0f}Cr AND "
                f"futures net long {fut_net:,.0f} contracts — real institutional conviction.")
        elif combined=='FUTURES_ONLY_BEARISH':
            risk_flags.append(
                f"FII FUTURES BEARISH (cash data unavailable): "
                f"Futures net short {abs(fut_net):,.0f} contracts, {fut_conv} conviction. "
                f"Cannot confirm genuine exit without cash market data — "
                f"futures short alone could be a hedge.")
        elif futures.get('flow_regime')=='CONTRARIAN_TRAP':
            risk_flags.append(
                f"CONTRARIAN TRAP: FII long futures {fut_net:+,.0f} but put buying "
                f"exceeds calls. Long market but heavily hedged — often precedes corrections.")
        elif not np.isnan(fut_net) if isinstance(fut_net,(int,float)) else False:
            implications.append(
                f"FII futures: {fut_net:+,.0f} contracts ({futures.get('sentiment','?')}, "
                f"{fut_conv} conviction)")

        # India macro
        if repo is not None:
            if rate_room=='AVAILABLE':
                msg=(f"RATE CUT SPACE: Repo {repo}%, CPI "
                     f"{cpi:.1f}% near target {im.get('rbi_cpi_target',4.0)}%. ")
                if fund_type=='equity':
                    opportunities.append(msg+
                        f"Rate cuts expand equity P/E multiples — 12-18 month re-rating possible.")
                else:
                    opportunities.append(msg+
                        f"50bps cut from {repo}% adds ~2.5-4% capital gain for 3-5Y duration funds.")
            elif rate_room=='NONE' and cpi:
                msg=(f"NO RATE CUT ROOM: CPI {cpi:.1f}% is "
                     f"{cpi-im.get('rbi_cpi_target',4.0):.1f}pp above target. "
                     f"Repo {repo}%. RBI cannot ease. ")
                risk_flags.append(msg+(
                    "Duration funds have no policy tailwind." if fund_type=='debt'
                    else "Equity market corrections lack policy backstop."))
            elif rate_room=='LIMITED' and cpi:
                implications.append(
                    f"LIMITED RATE CUT ROOM: CPI {cpi:.1f}% vs target "
                    f"{im.get('rbi_cpi_target',4.0)}%. Repo {repo}% — 25-50bps room, no more.")

        # GDP
        if gdp is not None:
            gm=im.get('growth_momentum','UNKNOWN')
            if gm=='STRONG' and fund_type=='equity':
                opportunities.append(
                    f"GROWTH BACKDROP: GDP {gdp}% — strong earnings cycle context for equity.")
            elif gm=='WEAK':
                risk_flags.append(
                    f"GROWTH SLOWDOWN: GDP {gdp}% compresses corporate margins and earnings.")

        # Crude and DXY
        crude=macro.get('crude_wti',{}); us10y=macro.get('us_10y',{})
        cp=crude.get('price',np.nan)
        if not np.isnan(cp) if isinstance(cp,(int,float)) else False:
            if cp>90:
                risk_flags.append(
                    f"CRUDE PRESSURE: WTI ${cp:.0f} — above $90, every $10 rise adds "
                    f"~Rs70,000Cr to India's annual import bill, widens CAD ~0.3% GDP. "
                    f"Creates INR pressure and inflation — constrains RBI.")
            elif cp<70:
                opportunities.append(
                    f"CRUDE TAILWIND: WTI ${cp:.0f} — lower import bill, lower inflation, "
                    f"more rate cut room. Positive for both equity and debt.")

        if not np.isnan(us10y.get('price',np.nan)) if isinstance(us10y.get('price'),float) else us10y.get('price'):
            y10=us10y.get('price',0)
            if y10>4.5:
                risk_flags.append(
                    f"US 10Y at {y10:.2f}% — elevated US yields attract global capital "
                    f"away from EM including India, creating FII outflow pressure.")

        # News
        if news.get('has_veto'):
            for item in news.get('veto_items',[])[:2]:
                risk_flags.insert(0,
                    f"VETO EVENT: {item['title'][:80]} — "
                    f"Do not add new positions until this resolves.")

        tone_desc={
            'CLEAR':'Global macro CLEAR — no major risk-off signals.',
            'CAUTIOUS_NEUTRAL':'Global macro CAUTIOUS NEUTRAL — mixed signals.',
            'CAUTIOUS':'Global macro CAUTIOUS — multiple risk signals, size conservatively.',
            'RISK_OFF':'Global macro RISK_OFF — avoid new positions, protect existing.',
            'MIXED':'Global macro MIXED — contradictory signals.',
        }
        implications.append(tone_desc.get(tone,f'Global tone: {tone}'))

        n=len(risk_flags); o=len(opportunities)
        if news.get('has_veto') or n>=4:
            overall='RISK_OFF'; entry='HOLD — do not add new positions until veto event resolves.'
        elif n>=2 and o==0:
            overall='CAUTIOUS'; entry='PROCEED WITH CAUTION — reduce new entry size.'
        elif n>=2 and o>=2:
            overall='CONFLICTED'; entry='MIXED SIGNALS — stagger entry if adding.'
        elif o>=2 and n<=1:
            overall='OPPORTUNITY'; entry='FAVOURABLE — signals aligned for building positions.'
        else:
            overall='NEUTRAL'; entry='NEUTRAL — no strong conviction signal either way.'

        return {'overall':overall,'entry_view':entry,'global_tone':tone,
                'risk_flags':risk_flags,'opportunities':opportunities,'implications':implications}


# ============================================================================
# AI SYNTHESIS ENGINES
# ============================================================================

def _llm_call(system_prompt, user_prompt, max_tokens=700, temperature=0.2):
    """Unified LLM call: Claude → Groq → None."""
    if _LLM_PROVIDER=='claude' and _LLM_CLIENT:
        try:
            r=_LLM_CLIENT.messages.create(
                model="claude-sonnet-4-5",max_tokens=max_tokens,
                messages=[{"role":"user","content":f"{system_prompt}\n\n{user_prompt}"}])
            return r.content[0].text.strip(),'claude'
        except Exception as e:
            _log.error(f"Claude error: {e}")
    if _LLM_PROVIDER=='groq' and _LLM_CLIENT:
        try:
            r=_LLM_CLIENT.chat.completions.create(
                model="llama-3.3-70b-versatile",max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role":"system","content":system_prompt},
                          {"role":"user","content":user_prompt}])
            return r.choices[0].message.content.strip(),'groq'
        except Exception as e:
            _log.error(f"Groq error: {e}")
    return None,'none'


class EquityAISynthesis:

    SYSTEM = """You are a senior Indian equity fund analyst. Write for a sophisticated investor.

OUTPUT: Exactly 5 sections, each 2-3 sentences:

**ANOMALY** - The most unusual metric combination and WHY it exists structurally.
**ALPHA DECODED** - What alpha + IR means in Rs per lakh per year. Structural or cyclical?
**AUM REALITY** - At this AUM, what stocks are off-limits? What does mandate say vs portfolio reality?
**BREAK SCENARIO** - One specific scenario (name exact conditions) that breaks the track record.
**WHO OWNS / WHO AVOIDS** - Specific investor situation, not a risk profile label.

RULES: Every sentence needs a number from data. No: may/could/might/suggests/likely/past performance/suitable for. Never invent numbers. 220-280 words max."""

    @staticmethod
    def synthesise(fund_meta, mf_meta, metrics):
        def f(v,s='%',fmt='.1f'):
            if v is None or (isinstance(v,float) and np.isnan(v)): return 'N/A'
            return f"{v:{fmt}}{s}"
        ba=metrics.get('beta_alpha',{}); cr=metrics.get('capture_ratios',{})
        rr3=metrics.get('rolling_3Y',{}); rr5=metrics.get('rolling_5Y',{})
        mdd=metrics.get('max_drawdown',{}); aum=mf_meta.get('aum_crore')
        alpha=ba.get('alpha',np.nan); ir=metrics.get('information_ratio',np.nan)
        alpha_per_lakh=round(abs(alpha)*1000,0) if not np.isnan(alpha) else None
        c3=metrics.get('cagr',{}).get('3Y',np.nan); b3=metrics.get('benchmark_cagr',{}).get('3Y',np.nan)

        prompt=f"""FUND: {fund_meta.get('scheme_name','N/A')}
CATEGORY: {fund_meta.get('scheme_category','N/A')} | AMC: {fund_meta.get('fund_house','N/A')}
AUM: {'Rs{:,.0f}Cr'.format(aum) if aum else 'Not available'} | ER: {f(mf_meta.get('expense_ratio'),'%','.2f') if mf_meta.get('expense_ratio') else 'N/A'}
MANAGER: {mf_meta.get('fund_manager') or 'N/A'}

RETURNS: 1Y {f(metrics.get('cagr',{}).get('1Y'))} | 3Y {f(c3)} | 5Y {f(metrics.get('cagr',{}).get('5Y'))} | Full {f(metrics.get('cagr',{}).get('Full'))}
BENCHMARK: 1Y {f(metrics.get('benchmark_cagr',{}).get('1Y'))} | 3Y {f(b3)} | 5Y {f(metrics.get('benchmark_cagr',{}).get('5Y'))}
OUTPERFORMANCE 3Y: {f((c3-b3) if not np.isnan(c3) and not np.isnan(b3) else np.nan)}
SIP XIRR 3Y: {f(metrics.get('sip_xirr',np.nan))}

Beta: {f(ba.get('beta'),'','.3f')} | Alpha: {f(alpha)} ann | IR: {f(ir,'','.3f')}
Alpha per Rs1L/year: {'Rs{:,.0f}'.format(alpha_per_lakh) if alpha_per_lakh else 'N/A'}
Sharpe: {f(metrics.get('sharpe',np.nan),'','.3f')} | Sortino: {f(metrics.get('sortino',np.nan),'','.3f')}
Upside Capture: {f(cr.get('upside_capture'))} | Downside Capture: {f(cr.get('downside_capture'))}
SD 3Y: {f(metrics.get('std_dev',np.nan))}

3Y Rolling: mean {f(rr3.get('mean',np.nan))} | >8%: {rr3.get('pct_above_8','N/A')}% of {rr3.get('n_obs','?')} windows
5Y Rolling: mean {f(rr5.get('mean',np.nan))} | >8%: {rr5.get('pct_above_8','N/A')}% of {rr5.get('n_obs','?')} windows

Max DD: {f(mdd.get('max_drawdown_pct',np.nan))} ({mdd.get('peak_date','?')}→{mdd.get('trough_date','?')})
COVID crash: {f(metrics.get('dd_covid',np.nan))} | 2022: {f(metrics.get('dd_2022',np.nan))} | IL&FS: {f(metrics.get('dd_ilfs',np.nan))}

Write the 5-section brief. Every sentence needs a number. No filler. 220-280 words."""

        text,provider=_llm_call(EquityAISynthesis.SYSTEM,prompt)
        if text: return {'narrative':text,'provider':provider}
        return {'narrative':EquityAISynthesis._rule_based(fund_meta,mf_meta,metrics),'provider':'rule-based'}

    @staticmethod
    def _rule_based(fund_meta,mf_meta,metrics):
        ba=metrics.get('beta_alpha',{}); cr=metrics.get('capture_ratios',{})
        alpha=ba.get('alpha',np.nan); beta=ba.get('beta',np.nan)
        ir=metrics.get('information_ratio',np.nan)
        uc=cr.get('upside_capture',np.nan); dc=cr.get('downside_capture',np.nan)
        aum=mf_meta.get('aum_crore'); parts=[]
        if not np.isnan(beta) and not np.isnan(uc) and beta<0.75 and uc>85:
            parts.append(f"**ANOMALY**: Beta {beta:.2f} with {uc:.0f}% upside capture is unusual — "
                         f"likely international/decorrelated allocation reducing benchmark correlation "
                         f"without capping upside participation.")
        if not np.isnan(alpha) and not np.isnan(ir):
            parts.append(f"**ALPHA DECODED**: {alpha:+.1f}% annualised, IR {ir:.2f} — "
                         f"Rs{abs(alpha)*1000:,.0f} extra per Rs10L per year, consistently. "
                         f"IR above 0.5 confirms structural, not lucky.")
        if aum and aum>50000:
            parts.append(f"**AUM REALITY**: At Rs{aum:,.0f}Cr the fund cannot take meaningful "
                         f"positions in sub-Rs5,000Cr stocks. Flexi-cap mandate is functionally large-cap.")
        parts.append("[Rule-based — set GROQ_API_KEY for AI narrative]")
        return "\n\n".join(parts)


class DebtAISynthesis:

    SYSTEM = """You are a senior fixed income analyst covering Indian debt mutual funds.

OUTPUT: Exactly 5 sections, 2-3 sentences each:

**DURATION REALITY** - What rate sensitivity does NAV behaviour show in 2022 hike cycle? Match stated category?
**CREDIT PICTURE** - What does return pattern say about credit quality? Is premium worth the risk?
**EXPENSE EFFICIENCY** - What is investor keeping after fees vs direct FD or passive? Name Rs difference on Rs10L.
**THE REAL RISK** - One specific mechanism (not "rising rates") that breaks this fund. Tie to a metric anomaly.
**WHO USES / WHO DOESN'T** - Specific investor situation: holding period, tax bracket context, alternative option.

RULES: Never use equity framing (no alpha/beta/outperform index). No: past performance/conservative investors/risk tolerance. Every sentence needs a number. 220-280 words max."""

    @staticmethod
    def synthesise(fund_meta, mf_meta, debt_profile, metrics):
        def f(v,s='%',fmt='.1f'):
            if v is None or (isinstance(v,float) and np.isnan(v)): return 'N/A'
            return f"{v:{fmt}}{s}"
        aum=mf_meta.get('aum_crore'); exp=mf_meta.get('expense_ratio')
        rs=metrics.get('rate_sensitivity_test',{})
        hike22=rs.get('rate_hike_2022_23',{}); ytm=metrics.get('ytm_estimate',{})
        c3=metrics.get('cagr',{}).get('3Y',np.nan)
        spread_fd=round(c3-7.0,2) if not np.isnan(c3) else None
        rupee_10l=round(spread_fd*1000,0) if spread_fd else None

        prompt=f"""FUND: {fund_meta.get('scheme_name','N/A')}
CATEGORY: {fund_meta.get('scheme_category','N/A')} | AMC: {fund_meta.get('fund_house','N/A')}
AUM: {'Rs{:,.0f}Cr'.format(aum) if aum else 'N/A'} | ER: {f(exp,'%','.2f') if exp else 'N/A'}
MANAGER: {mf_meta.get('fund_manager') or 'N/A'}

DEBT PROFILE: {debt_profile.get('rate_sensitivity','?')} sensitivity | Credit: {debt_profile.get('credit_profile','?')}
Primary risk: {debt_profile.get('primary_risk','?')} | Expected return: {debt_profile.get('benchmark_return','?')}-{debt_profile.get('return_ceiling','?')}%

RETURNS: 1Y {f(metrics.get('cagr',{}).get('1Y'))} | 3Y {f(c3)} | 5Y {f(metrics.get('cagr',{}).get('5Y'))}
Spread over 7% FD (3Y): {f(spread_fd,'pp') if spread_fd else 'N/A'}
Extra per Rs10L vs FD/year: {'Rs{:,.0f}'.format(rupee_10l) if rupee_10l else 'N/A'}

SD 3Y: {f(metrics.get('std_dev',np.nan))} | SD check: {metrics.get('sd_anomaly',{}).get('message','')}
Sharpe: {f(metrics.get('sharpe',np.nan),'','.3f')} | Negative months: {f(metrics.get('negative_months',np.nan),'%','.1f')}
YTM proxy: {ytm.get('ytm_estimate','N/A')}% | Expense efficiency: {metrics.get('expense_efficiency',{}).get('message','')}

Rate hike cycle 2022-23: return {f(hike22.get('total_return',np.nan))} | drawdown {f(hike22.get('drawdown',np.nan))}
Max drawdown ever: {f(metrics.get('max_drawdown',{}).get('max_drawdown_pct',np.nan))}

Write the 5-section debt brief. No equity framing. Every sentence needs a number. 220-280 words."""

        text,provider=_llm_call(DebtAISynthesis.SYSTEM,prompt)
        if text: return {'narrative':text,'provider':provider}
        return {'narrative':DebtAISynthesis._rule_based(fund_meta,mf_meta,debt_profile,metrics),'provider':'rule-based'}

    @staticmethod
    def _rule_based(fund_meta,mf_meta,debt_profile,metrics):
        rs=metrics.get('rate_sensitivity_test',{}); hike22=rs.get('rate_hike_2022_23',{})
        ytm=metrics.get('ytm_estimate',{}); exp=mf_meta.get('expense_ratio')
        hike_ret=hike22.get('total_return',np.nan); parts=[]
        if not np.isnan(hike_ret):
            sensitivity=abs(hike_ret)
            parts.append(f"**DURATION REALITY**: During 250bps RBI hike cycle (May22-Jan23) "
                         f"this fund returned {hike_ret:+.1f}% — "
                         f"{'near-zero sensitivity confirms short duration profile.' if sensitivity<1 else 'moderate sensitivity, ~1.5-3Y effective duration.' if sensitivity<5 else 'significant rate sensitivity — fund holds longer duration than category suggests.'}")
        ytm_val=ytm.get('ytm_estimate',np.nan)
        if not np.isnan(ytm_val) and exp:
            net=round(ytm_val-exp,2)
            parts.append(f"**EXPENSE EFFICIENCY**: YTM proxy {ytm_val:.1f}% minus ER {exp:.2f}% "
                         f"leaves ~{net:.1f}% for investor — Rs{net*1000:,.0f}/year per Rs10L.")
        parts.append("[Rule-based — set GROQ_API_KEY for AI narrative]")
        return "\n\n".join(parts)


class RegimeAISynthesis:

    SYSTEM = """You are a macro analyst. Write exactly 3 sentences. No more.

SENTENCE 1: State the single most important thing happening right now. One cause, one consequence. No hedging.
SENTENCE 2: State what sentence 1 means for this specific fund category. Name the exact mechanism. One number from the data.
SENTENCE 3: Start with the exact regime verdict word provided. Then one reason with one number.

IRON RULES:
1. Exactly 3 sentences. Not paragraphs.
2. Never use: may/could/might/suggests/likely/perhaps
3. Never invent a number not in the data provided
4. Sentence 3 verdict must match the pre-computed regime verdict exactly
5. Never mention beta/alpha/Sharpe or any fund performance metric
6. Under 120 words total"""

    @staticmethod
    def synthesise(regime_ctx, fund_name, fund_category, fund_type):
        fii=regime_ctx.get('fii',{}); macro=regime_ctx.get('macro',{})
        vix=regime_ctx.get('india_vix',np.nan); vix_p=regime_ctx.get('vix_percentile',{})
        im=regime_ctx.get('india_macro',{}); news=regime_ctx.get('news',{})
        interp=regime_ctx.get('interpretation',{})
        cash=fii.get('cash',{}); futures=fii.get('futures',{})
        def fv(v,fmt='.1f',prefix=''):
            if v is None or (isinstance(v,float) and np.isnan(v)): return 'N/A'
            return f"{prefix}{v:{fmt}}"
        m=macro
        prompt=f"""FUND: {fund_name} | CATEGORY: {fund_category} | TYPE: {fund_type}
VIX: {fv(vix)} | {vix_p.get('percentile_1y','N/A')}th pct 1Y | regime: {vix_p.get('regime','?')}
FII cash: {fv(cash.get('fii_net_cr',np.nan),'.0f','Rs')}Cr ({cash.get('direction','N/A')}) | 5d: {fv(cash.get('5d_net_cr',np.nan),'.0f','Rs')}Cr
FII futures: {fv(futures.get('fii_fut_net',np.nan),'.0f')} contracts | {futures.get('sentiment','?')} | {futures.get('conviction','?')}
Combined FII: {fii.get('combined_signal','N/A')}
RBI Repo: {im.get('repo_rate','N/A')}% | CPI: {im.get('cpi_latest','N/A')}% vs target {im.get('rbi_cpi_target',4.0)}% | GDP: {im.get('gdp_growth_latest','N/A')}% | Rate cut room: {im.get('rate_cut_room','N/A')}
S&P: {fv(m.get('sp500',{}).get('price',np.nan),',.0f')} ({fv(m.get('sp500',{}).get('change_pct',np.nan),'+.2f')}%) | US VIX: {fv(m.get('us_vix',{}).get('price',np.nan))} | Crude: ${fv(m.get('crude_wti',{}).get('price',np.nan),'.1f')} | DXY: {fv(m.get('dxy',{}).get('price',np.nan))} | USD/INR: {fv(m.get('usd_inr',{}).get('price',np.nan))}
Global tone: {m.get('_meta',{}).get('global_tone','?')} | Risk-off signals: {m.get('_meta',{}).get('risk_off_count','?')}
News veto items: {len(news.get('veto_items',[]))} | {('VETO: '+news['veto_items'][0]['title'][:60]) if news.get('has_veto') else 'No veto news'}
REGIME VERDICT (use exactly): {interp.get('overall','?')} — {interp.get('entry_view','?')}
Write 3 sentences. Use ONLY numbers above. 120 words max."""

        text,provider=_llm_call(RegimeAISynthesis.SYSTEM,prompt,max_tokens=250,temperature=0.15)
        if text: return {'narrative':text,'provider':provider}
        return {'narrative':RegimeAISynthesis._rule_based(regime_ctx,fund_type),'provider':'rule-based'}

    @staticmethod
    def _rule_based(regime_ctx,fund_type):
        fii=regime_ctx.get('fii',{}); macro=regime_ctx.get('macro',{})
        vix=regime_ctx.get('india_vix',np.nan); vix_p=regime_ctx.get('vix_percentile',{})
        im=regime_ctx.get('india_macro',{}); interp=regime_ctx.get('interpretation',{})
        cash=fii.get('cash',{}); futures=fii.get('futures',{})
        combined=fii.get('combined_signal','UNKNOWN')
        cpi=im.get('cpi_latest'); repo=im.get('repo_rate',6.25)
        fut_net=futures.get('fii_fut_net',np.nan); cash_net=cash.get('fii_net_cr',np.nan)
        parts=[]
        story="**MARKET NOW**: "
        vix_ok=not (isinstance(vix,float) and np.isnan(vix)) and vix is not None
        if vix_ok: story+=f"India VIX at {vix:.1f} is at the {vix_p.get('percentile_1y','?')}th percentile. "
        crude_p=macro.get('crude_wti',{}).get('price',np.nan)
        crude_ok=not (isinstance(crude_p,float) and np.isnan(crude_p)) if isinstance(crude_p,float) else crude_p is not None
        if crude_ok and crude_p>90 and cpi:
            story+=(f"Crude at ${crude_p:.0f} with CPI {cpi}% above RBI's "
                    f"{im.get('rbi_cpi_target',4.0)}% target — imported inflation is "
                    f"constraining RBI from cutting rates to defend the market.")
        elif cpi and repo:
            story+=(f"CPI {cpi}% vs RBI target {im.get('rbi_cpi_target',4.0)}%, "
                    f"repo at {repo}% — "
                    f"{'RBI has limited rate cut room.' if im.get('rate_cut_room')!='AVAILABLE' else 'RBI retains rate cut flexibility.'}")
        parts.append(story)
        meaning=f"**WHAT IT MEANS**: "
        if fund_type=='equity' and vix_ok and vix_p.get('percentile_1y',0)>80:
            meaning+=(f"VIX at {vix_p.get('percentile_1y','?')}th percentile historically "
                      f"means good 12-month forward equity returns — but FII futures net "
                      f"{fut_net:+,.0f} contracts means near-term NAV headwinds persist 2-4 weeks.")
        elif fund_type=='debt' and cpi:
            meaning+=(f"CPI {cpi}% constrains rate cuts — the primary driver of medium "
                      f"duration debt returns. Without rate cut tailwind, returns rely on carry alone.")
        else:
            meaning+=f"Global tone {macro.get('_meta',{}).get('global_tone','?')} with {macro.get('_meta',{}).get('risk_off_count',0)} risk-off signals active."
        parts.append(meaning)
        parts.append(f"**VERDICT**: {interp.get('entry_view','No verdict computed.')}")
        parts.append("[Rule-based — set GROQ_API_KEY for AI narrative]")
        return "\n\n".join(parts)


# ============================================================================
# BRIEF GENERATORS
# ============================================================================

def _f(v,s='%',fmt='.2f'):
    if v is None or (isinstance(v,float) and np.isnan(v)): return "N/A"
    return f"{v:+{fmt}}{s}" if s=='%' else f"{v:{fmt}}{s}"

def _conviction_equity(metrics):
    score=0; ba=metrics.get('beta_alpha',{}); cr=metrics.get('capture_ratios',{})
    alpha=ba.get('alpha',np.nan); sortino=metrics.get('sortino',np.nan)
    ir=metrics.get('information_ratio',np.nan)
    uc=cr.get('upside_capture',np.nan); dc=cr.get('downside_capture',np.nan)
    rr3=metrics.get('rolling_3Y',{})
    if not np.isnan(alpha): score+=(2 if alpha>2 else 1 if alpha>0 else -1)
    if not np.isnan(sortino): score+=(2 if sortino>1 else 1 if sortino>0.5 else 0)
    if not np.isnan(ir): score+=(2 if ir>0.5 else 1 if ir>0 else -1)
    if not np.isnan(uc) and not np.isnan(dc):
        if uc>=85 and dc<60: score+=3
        elif uc>=85 and dc<85: score+=2
        elif uc>100 and dc<100: score+=1
        elif uc<85 and dc>=100: score-=2
    if rr3.get('available') and rr3.get('pct_above_8',0)>70: score+=1
    if score>=8: return "HIGH ★★★★","Strong across return, risk, consistency, and benchmark comparison."
    elif score>=5: return "MODERATE ★★★☆","Solid with some areas to monitor."
    elif score>=2: return "LOW ★★☆☆","Mixed signals — examine carefully."
    else: return "AVOID ★☆☆☆","Weak risk-adjusted performance."

def _flags_equity(metrics):
    green,amber,red=[],[],[]
    ba=metrics.get('beta_alpha',{}); cr=metrics.get('capture_ratios',{})
    alpha=ba.get('alpha',np.nan); beta=ba.get('beta',np.nan)
    sortino=metrics.get('sortino',np.nan); ir=metrics.get('information_ratio',np.nan)
    uc=cr.get('upside_capture',np.nan); dc=cr.get('downside_capture',np.nan)
    rr3=metrics.get('rolling_3Y',{}); rr5=metrics.get('rolling_5Y',{})
    if not np.isnan(alpha):
        (green if alpha>2 else amber if alpha>0 else red).append(f"Alpha {alpha:+.1f}%")
    if not np.isnan(beta):
        (green if beta<0.85 else amber if beta<1.05 else red).append(f"Beta {beta:.2f}")
    if not np.isnan(sortino):
        (green if sortino>1 else amber if sortino>0.5 else red).append(f"Sortino {sortino:.2f}")
    if not np.isnan(ir):
        (green if ir>0.5 else amber if ir>0 else red).append(f"Info Ratio {ir:.2f}")
    if not np.isnan(uc) and not np.isnan(dc):
        if uc>=85 and dc<60: green.append(f"Capture {uc:.0f}%up/{dc:.0f}%dn — exceptional asymmetry")
        elif uc>=85 and dc<85: green.append(f"Capture {uc:.0f}%up/{dc:.0f}%dn — good asymmetry")
        elif uc<85 and dc>=100: red.append(f"Capture {uc:.0f}%up/{dc:.0f}%dn — underperforms both ways")
        else: amber.append(f"Capture {uc:.0f}%up/{dc:.0f}%dn")
    if rr3.get('available'):
        p=rr3.get('pct_above_8',0)
        (green if p>75 else amber if p>50 else red).append(f"3Y rolling: {p:.0f}% of windows >8%")
    if rr5.get('available'):
        p=rr5.get('pct_above_8',0)
        (green if p>75 else amber if p>50 else red).append(f"5Y rolling: {p:.0f}% of windows >8%")
    return {'green':green,'amber':amber,'red':red}

def _conviction_debt(metrics,debt_profile):
    score=0; cagr3=metrics.get('cagr',{}).get('3Y',np.nan)
    sharpe=metrics.get('sharpe',np.nan); rr1=metrics.get('rolling_1Y',{})
    exp_eff=metrics.get('expense_efficiency',{}); sd_anom=metrics.get('sd_anomaly',{})
    bench=debt_profile.get('benchmark_return',7.0)
    if not np.isnan(cagr3):
        if cagr3>=bench: score+=2
        elif cagr3>=RISK_FREE_RATE*100: score+=1
        else: score-=1
    if rr1.get('available'):
        p=rr1.get('pct_above_rf',0)
        if p>=85: score+=2
        elif p>=70: score+=1
        else: score-=1
    if sd_anom.get('severity')=='GREEN': score+=1
    elif sd_anom.get('severity')=='RED': score-=2
    if exp_eff.get('severity')=='GREEN': score+=1
    elif exp_eff.get('severity')=='RED': score-=2
    if not np.isnan(sharpe):
        if sharpe>=1.0: score+=1
        elif sharpe<0: score-=1
    if score>=6: return "SOUND ★★★★","Delivers on mandate — consistent, efficient, risk appropriate."
    elif score>=3: return "ADEQUATE ★★★☆","Reasonable with some efficiency or consistency gaps."
    elif score>=1: return "REVIEW ★★☆☆","Questions on risk-adjusted value. Check alternatives."
    else: return "AVOID ★☆☆☆","Inadequate return for risk taken."

def _flags_debt(metrics,debt_profile,mf_meta):
    green,amber,red=[],[],[]
    cagr3=metrics.get('cagr',{}).get('3Y',np.nan); sd_anom=metrics.get('sd_anomaly',{})
    exp_eff=metrics.get('expense_efficiency',{}); rr1=metrics.get('rolling_1Y',{})
    neg_m=metrics.get('negative_months',np.nan); ytm=metrics.get('ytm_estimate',{})
    exp=mf_meta.get('expense_ratio'); bench=debt_profile.get('benchmark_return',7.0)
    if not np.isnan(cagr3):
        d=cagr3-bench
        (green if d>=0 else amber).append(f"3Y CAGR {cagr3:.2f}% vs category {bench:.1f}% ({d:+.1f}%)")
    if rr1.get('available'):
        p=rr1.get('pct_above_rf',0)
        (green if p>=85 else amber if p>=70 else red).append(f"1Y rolling: {p:.0f}% of windows >RF")
    sev=sd_anom.get('severity','')
    if sev=='GREEN': green.append(f"SD {metrics.get('std_dev',0):.1f}% — within expected range")
    elif sev=='AMBER': amber.append(f"SD slightly elevated — monitor")
    elif sev=='RED': red.append(f"SD anomalously high for category — hidden risk")
    if not np.isnan(neg_m):
        (green if neg_m<15 else amber if neg_m<25 else red).append(f"Negative months: {neg_m:.0f}%")
    esev=exp_eff.get('severity','')
    if esev=='GREEN': green.append("Expense ratio — adequate spread above costs")
    elif esev=='AMBER': amber.append("Expense ratio — thin spread, verify direct plan")
    elif esev=='RED': red.append("Expense ratio eating most of the spread")
    ytm_val=ytm.get('ytm_estimate',np.nan)
    if not np.isnan(ytm_val) and exp:
        net=ytm_val-exp
        (green if net>7 else amber if net>6 else red).append(
            f"Net yield est {net:.2f}% (YTM {ytm_val:.2f}% - ER {exp:.2f}%)")
    return {'green':green,'amber':amber,'red':red}


def _print_brief_equity(fund_meta,mf_meta,metrics,ai,bench_name,portfolio=None):
    L=[]; sep="-"*70
    L+=["","="*70,"  FINTELLIGENCE — FUND CONVICTION BRIEF","="*70,
        f"  Fund     : {fund_meta.get('scheme_name','N/A')}",
        f"  Category : {fund_meta.get('scheme_category','N/A')}",
        f"  AMC      : {fund_meta.get('fund_house','N/A')}",
        f"  As of    : {metrics.get('as_of','N/A')}",
        f"  Benchmark: {bench_name}","="*70]
    conv,reason=_conviction_equity(metrics)
    L+=[f"\n  CONVICTION: {conv}",f"  {reason}\n"]

    # G: Fund Profile
    L+=[sep,"  G. FUND PROFILE",sep]
    aum=mf_meta.get('aum_crore'); exp=mf_meta.get('expense_ratio')
    L+=[f"  Manager  : {mf_meta.get('fund_manager') or 'Not available'}",
        f"  AUM      : {'Rs{:,.0f}Cr'.format(aum) if aum else 'Not available'}",
        f"  Exp Ratio: {'{:.2f}%'.format(exp) if exp else 'Not available'}",
        f"  ISIN     : {mf_meta.get('isin') or 'N/A'}",
        f"  Source   : {mf_meta.get('meta_source','N/A')}"]
    if aum and aum>50000:
        L+=["",f"  AUM Watch: Rs{aum:,.0f}Cr — structurally large-cap regardless of mandate."]

    # A: Returns
    L+=["",sep,"  A. RETURN PERFORMANCE",sep]
    cd=metrics.get('cagr',{}); bd=metrics.get('benchmark_cagr',{})
    for p in ['1Y','3Y','5Y','Full']:
        fr,br=cd.get(p,np.nan),bd.get(p,np.nan)
        if not np.isnan(fr):
            bs=f"  Bench: {br:+.1f}%" if not np.isnan(br) else ""
            ds=f"  ({(fr-br):+.1f}% vs bench)" if not np.isnan(br) else ""
            L.append(f"  {p:8}: Fund {fr:+.1f}%{bs}{ds}")
    L.append(f"\n  SIP XIRR (3Y Rs{SIP_AMOUNT:,}/month): {_f(metrics.get('sip_xirr',np.nan),'%')}")

    # B: Rolling
    L+=["",sep,"  B. ROLLING RETURN CONSISTENCY",sep,"  (Every possible entry point)"]
    for w in ['1Y','3Y','5Y']:
        rr=metrics.get(f'rolling_{w}',{})
        if rr.get('available'):
            L+=[f"\n  {w} Rolling ({rr['n_obs']:,} obs):",
                f"    Range: {rr['min']:.1f}% to {rr['max']:.1f}%  |  Avg: {rr['mean']:.1f}%  |  Median: {rr['median']:.1f}%",
                f"    >0%: {rr['pct_positive']:.0f}%  |  >8%: {rr['pct_above_8']:.0f}%  |  >12%: {rr['pct_above_12']:.0f}%"]

    # C: Risk
    L+=["",sep,"  C. RISK METRICS",sep]
    sd=metrics.get('std_dev',np.nan); sh=metrics.get('sharpe',np.nan); so=metrics.get('sortino',np.nan)
    L+=[f"  Std Dev (3Y): {_f(sd,'%')}  — expect NAV to swing ~±{sd:.0f}% per year" if not np.isnan(sd) else f"  Std Dev (3Y): N/A",
        f"  Sharpe (3Y) : {_f(sh,'','.3f')}",
        f"  Sortino (3Y): {_f(so,'','.3f')}"]

    # D: Benchmark
    L+=["",sep,"  D. BENCHMARK COMPARISON",sep]
    ba=metrics.get('beta_alpha',{}); cr=metrics.get('capture_ratios',{})
    beta=ba.get('beta',np.nan); alpha=ba.get('alpha',np.nan)
    ir=metrics.get('information_ratio',np.nan); rsq=ba.get('r_squared',np.nan)
    uc=cr.get('upside_capture',np.nan); dc=cr.get('downside_capture',np.nan)
    L+=[f"  Beta (3Y)  : {_f(beta,'','.3f')}",
        f"  Alpha (3Y) : {_f(alpha,'%')}"]
    if not np.isnan(alpha) and not np.isnan(ir):
        L.append(f"    Rs{abs(alpha)*1000:,.0f}/Rs10L/year  |  IR {ir:.2f} — {'consistent' if ir>0.5 else 'moderate'}")
    L+=[f"  R-Squared  : {_f(rsq,'','.3f')}",
        f"\n  Upside Cap : {_f(uc,'%','.1f')}",
        f"  Downside Cap: {_f(dc,'%','.1f')}"]
    if not np.isnan(uc) and not np.isnan(dc):
        if uc>=85 and dc<60: L+=["    EXCEPTIONAL ASYMMETRY: captures most rally, fraction of fall"]
        elif uc>=85 and dc<85: L+=["    GOOD ASYMMETRY: strong upside + meaningful downside cushion"]
        elif uc<85 and dc>=100: L+=["    WEAK: underperforms in both directions"]

    # E: Drawdown
    L+=["",sep,"  E. DRAWDOWN ANALYSIS",sep]
    mdd=metrics.get('max_drawdown',{})
    L.append(f"  Worst Ever : {_f(mdd.get('max_drawdown_pct',np.nan),'%','.2f')}")
    if mdd.get('peak_date'): L.append(f"    Peak: {mdd['peak_date']} → Trough: {mdd['trough_date']}")
    L+=["",f"  COVID (Feb-Apr 2020)    : {_f(metrics.get('dd_covid',np.nan),'%','.2f')}",
        f"  2022 Correction          : {_f(metrics.get('dd_2022',np.nan),'%','.2f')}",
        f"  IL&FS (Sep-Dec 2018)     : {_f(metrics.get('dd_ilfs',np.nan),'%','.2f')}"]

    # F: Holdings (Phase 3)
    if portfolio and portfolio.get('available'):
        L+=["",sep,"  F. PORTFOLIO HOLDINGS  (AMFI monthly disclosure)",sep,
            f"  Total holdings: {portfolio.get('total_stocks',0)}  |  "
            f"Top 5: {portfolio.get('top5_pct','N/A')}%  |  Top 10: {portfolio.get('top10_pct','N/A')}%"]
        if portfolio.get('cash_pct'): L.append(f"  Cash/CBLO: {portfolio['cash_pct']}%")
        holdings=portfolio.get('holdings',[])
        if holdings:
            L+=["","  TOP 10 HOLDINGS:"]
            for i,h in enumerate(holdings[:10],1):
                L.append(f"    {i:>2}. {h['name'][:40]:<40}  {h['pct_nav']:>5.1f}%"
                         +(f"  [{h['sector']}]" if h.get('sector') else ""))
        sectors=portfolio.get('sector_alloc',{})
        if sectors:
            L+=["","  SECTOR ALLOCATION (top 5):"]
            for sec,pct in list(sectors.items())[:5]:
                L.append(f"    {sec[:35]:<35}  {pct:.1f}%")
    else:
        L+=["",sep,"  F. PORTFOLIO HOLDINGS",sep,
            "  Holdings data unavailable — AMFI disclosure fetch returned no data.",
            "  This may be a timing issue (end of month). Retry tomorrow or check amfiindia.com"]

    # G: Signals
    L+=["",sep,"  G. CONVICTION SIGNALS",sep]
    flags=_flags_equity(metrics)
    if flags['green']:
        L.append("  POSITIVE:")
        for x in flags['green']: L.append(f"    ✓ {x}")
    if flags['amber']:
        L.append("  WATCH:")
        for x in flags['amber']: L.append(f"    ⚠ {x}")
    if flags['red']:
        L.append("  FLAGS:")
        for x in flags['red']: L.append(f"    ✗ {x}")

    # H: AI Narrative
    L+=["",sep,f"  H. AI INTELLIGENCE NARRATIVE  [{ai.get('provider','?').upper()}]",sep]
    for para in ai.get('narrative','').split('\n'):
        if para.strip(): L.append(f"  {para.strip()}")

    L+=["","  NOTE: Intelligence, not advice. All reasoning shown.",
        "  The investor decides. Fintelligence informs.","="*70,""]
    return "\n".join(L)


def _print_brief_debt(fund_meta,mf_meta,debt_profile,metrics,ai,portfolio=None):
    L=[]; sep="-"*70
    L+=["","="*70,"  FINTELLIGENCE — DEBT FUND INTELLIGENCE BRIEF","="*70,
        f"  Fund         : {fund_meta.get('scheme_name','N/A')}",
        f"  Category     : {fund_meta.get('scheme_category','N/A')}",
        f"  AMC          : {fund_meta.get('fund_house','N/A')}",
        f"  As of        : {metrics.get('as_of','N/A')}",
        f"  Rate Sensit. : {debt_profile.get('rate_sensitivity','UNKNOWN')}",
        f"  Primary Risk : {debt_profile.get('primary_risk','UNKNOWN').replace('_',' ').upper()}",
        "="*70]
    conv,reason=_conviction_debt(metrics,debt_profile)
    L+=[f"\n  CONVICTION: {conv}",f"  {reason}\n"]

    # G: Profile
    L+=[sep,"  G. FUND PROFILE",sep]
    aum=mf_meta.get('aum_crore'); exp=mf_meta.get('expense_ratio')
    ytm=metrics.get('ytm_estimate',{})
    L+=[f"  Manager   : {mf_meta.get('fund_manager') or 'Not available'}",
        f"  AUM       : {'Rs{:,.0f}Cr'.format(aum) if aum else 'Not available'}",
        f"  Exp Ratio : {'{:.2f}%'.format(exp) if exp else 'Not available'}",
        f"  YTM Proxy : {'{:.2f}%'.format(ytm.get('ytm_estimate')) if ytm.get('ytm_estimate') else 'N/A'} (6M NAV annualised)",
        f"  Net Yield : {'{:.2f}%'.format(ytm.get('ytm_estimate')-exp) if ytm.get('ytm_estimate') and exp else 'N/A'} (YTM minus ER)"]

    # A: Returns
    L+=["",sep,"  A. RETURN PERFORMANCE",sep,
        f"  Expected: {debt_profile.get('benchmark_return')}% to {debt_profile.get('return_ceiling')}% p.a."]
    cd=metrics.get('cagr',{}); bench=debt_profile.get('benchmark_return',7.0)
    for p in ['1Y','3Y','5Y','Full']:
        v=cd.get(p,np.nan)
        if not np.isnan(v):
            d=v-bench; flag='✓' if d>=0 else '⚠'
            L.append(f"  {p:8}: {v:+.2f}%  {flag} ({d:+.1f}% vs category)")
    L.append(f"\n  SIP XIRR (3Y): {_f(metrics.get('sip_xirr',np.nan),'%')}")

    # B: Rolling (debt calibrated)
    L+=["",sep,"  B. ROLLING CONSISTENCY (debt-calibrated)",sep,
        f"  Thresholds: >RF ({RISK_FREE_RATE*100:.1f}%) and >category ({bench:.1f}%)"]
    for w in ['1Y','3Y']:
        rr=metrics.get(f'rolling_{w}',{})
        if rr.get('available'):
            L+=[f"\n  {w} Rolling ({rr['n_obs']:,} obs):",
                f"    Range: {rr['min']:.2f}% to {rr['max']:.2f}%  |  Avg: {rr['mean']:.2f}%",
                f"    > RF: {rr.get('pct_above_rf','N/A')}%  |  > Category: {rr.get('pct_above_bench','N/A')}%"]

    # C: Risk
    L+=["",sep,"  C. RISK METRICS (debt-appropriate)",sep]
    sd=metrics.get('std_dev',np.nan); sh=metrics.get('sharpe',np.nan)
    nm=metrics.get('negative_months',np.nan); sd_an=metrics.get('sd_anomaly',{})
    exp_ef=metrics.get('expense_efficiency',{})
    L.append(f"  Std Dev (3Y): {_f(sd,'%')}")
    sev=sd_an.get('severity',''); pre={'RED':'  ✗','AMBER':'  ⚠','GREEN':'  ✓'}.get(sev,'   ')
    if sd_an.get('message'): L.append(f"{pre} {sd_an['message']}")
    L+=[f"  Sharpe (3Y) : {_f(sh,'','.3f')}",
        f"  Neg Months  : {_f(nm,'%','.1f')} of months (3Y)"]
    sev2=exp_ef.get('severity',''); pre2={'RED':'  ✗','AMBER':'  ⚠','GREEN':'  ✓'}.get(sev2,'   ')
    if exp_ef.get('message'): L+=["",f"  EXPENSE EFFICIENCY:",f"{pre2} {exp_ef['message']}"]

    # D: Rate sensitivity
    L+=["",sep,"  D. RATE SENSITIVITY — ACTUAL NAV BEHAVIOUR IN KNOWN EVENTS",sep,
        "  (Reveals true duration regardless of stated category)"]
    rs=metrics.get('rate_sensitivity_test',{})
    for key,label in [('rate_hike_2022_23','RBI hike +250bps (May22-Jan23)'),
                      ('rate_cut_2019_20','RBI cut -210bps (Feb19-Mar20)'),
                      ('il_fs_2018','IL&FS (Sep-Dec 2018)'),
                      ('franklin_2020','Franklin closure (Apr-May 2020)'),
                      ('taper_tantrum_2013','Taper tantrum (May-Aug 2013)')]:
        ev=rs.get(key,{}); tr=ev.get('total_return',np.nan); dd=ev.get('drawdown',np.nan)
        if not np.isnan(tr):
            flag='✓' if tr>=0 else '⚠' if tr>-2 else '✗'
            L.append(f"  {flag} {label}: return {tr:+.2f}%  |  drawdown {_f(dd,'%','.2f')}")

    # E: Drawdown
    L+=["",sep,"  E. DRAWDOWN ANALYSIS",sep]
    mdd=metrics.get('max_drawdown',{})
    L.append(f"  Worst Ever: {_f(mdd.get('max_drawdown_pct',np.nan),'%','.2f')}")
    if mdd.get('peak_date'): L.append(f"    Peak: {mdd['peak_date']} → Trough: {mdd['trough_date']}")

    # F: Holdings (Phase 3)
    if portfolio and portfolio.get('available'):
        L+=["",sep,"  F. PORTFOLIO COMPOSITION (AMFI monthly disclosure)",sep,
            f"  Holdings: {portfolio.get('total_stocks',0)}  |  "
            f"Top 5: {portfolio.get('top5_pct','N/A')}%"]
        holdings=portfolio.get('holdings',[])
        if holdings:
            L+=["","  TOP 10 HOLDINGS:"]
            for i,h in enumerate(holdings[:10],1):
                L.append(f"    {i:>2}. {h['name'][:40]:<40}  {h['pct_nav']:>5.1f}%")
    else:
        L+=["",sep,"  F. PORTFOLIO COMPOSITION",sep,
            "  Holdings data unavailable from AMFI. Check amfiindia.com directly."]

    # G: Signals
    L+=["",sep,"  G. DEBT SIGNALS",sep]
    flags=_flags_debt(metrics,debt_profile,mf_meta)
    if flags['green']:
        L.append("  POSITIVE:")
        for x in flags['green']: L.append(f"    ✓ {x}")
    if flags['amber']:
        L.append("  WATCH:")
        for x in flags['amber']: L.append(f"    ⚠ {x}")
    if flags['red']:
        L.append("  FLAGS:")
        for x in flags['red']: L.append(f"    ✗ {x}")

    # H: Use Case
    L+=["",sep,"  H. USE CASE GUIDANCE",sep,
        f"  SUITABLE FOR : {debt_profile.get('suitable_for','')}",
        f"  AVOID IF     : {debt_profile.get('avoid_if','')}"]

    # I: AI Narrative
    L+=["",sep,f"  I. AI INTELLIGENCE NARRATIVE  [{ai.get('provider','?').upper()}]",sep]
    for para in ai.get('narrative','').split('\n'):
        if para.strip(): L.append(f"  {para.strip()}")

    L+=["","  NOTE: Intelligence, not advice. All reasoning shown.",
        "  The investor decides. Fintelligence informs.","="*70,""]
    return "\n".join(L)


def _print_regime_section(regime_ctx,ai_result):
    L=[]; sep="-"*70
    L+=["",sep,f"  MARKET REGIME CONTEXT  ({regime_ctx.get('timestamp','N/A')})",sep]

    vix=regime_ctx.get('india_vix',np.nan); vix_p=regime_ctx.get('vix_percentile',{})
    vix_ok=vix is not None and not (isinstance(vix,float) and np.isnan(vix))
    if vix_ok:
        L+=[f"  India VIX : {vix:.2f}  |  1Y Pct: {vix_p.get('percentile_1y','N/A')}th  |  Regime: {vix_p.get('regime','N/A')}",
            f"  1Y range  : {vix_p.get('1y_min','N/A')} - {vix_p.get('1y_max','N/A')}  |  Mean: {vix_p.get('1y_mean','N/A')}"]

    im=regime_ctx.get('india_macro',{})
    L+=["","  INDIA MACRO:",
        f"    Repo: {im.get('repo_rate','N/A')}%  |  Stance: {im.get('rbi_stance','N/A')}",
        f"    CPI: {'{:.1f}%'.format(im['cpi_latest']) if im.get('cpi_latest') else 'N/A'}  |  Target: {im.get('rbi_cpi_target',4.0)}%  |  vs target: {'{:+.1f}pp'.format(im.get('cpi_vs_target',0)) if im.get('cpi_vs_target') is not None else 'N/A'}",
        f"    GDP: {'{:.1f}%'.format(im['gdp_growth_latest']) if im.get('gdp_growth_latest') else 'N/A'}  |  Momentum: {im.get('growth_momentum','N/A')}",
        f"    Rate cut room: {im.get('rate_cut_room','N/A')}  |  Macro stance: {im.get('macro_stance','N/A')}"]

    fii=regime_ctx.get('fii',{}); cash=fii.get('cash',{}); fut=fii.get('futures',{})
    L+=["",f"  FII  (combined: {fii.get('combined_signal','N/A').replace('_',' ')})"]
    if cash.get('available'):
        cn=cash.get('fii_net_cr',np.nan); fd=cash.get('5d_net_cr',np.nan)
        L.append(f"    Cash: {'Rs{:+,.0f}Cr'.format(cn) if not np.isnan(cn) else 'N/A'}  |  5-day: {'Rs{:+,.0f}Cr'.format(fd) if not np.isnan(fd) else 'N/A'}  |  {cash.get('direction','?')}")
    else:
        L.append("    Cash: N/A (NSE data unavailable)")
    if fut.get('available'):
        fn=fut.get('fii_fut_net',np.nan)
        L.append(f"    Futures: {'{:+,.0f} contracts'.format(fn) if not np.isnan(fn) else 'N/A'}  |  {fut.get('sentiment','?')}  |  {fut.get('conviction','?')} conviction  |  {fut.get('flow_regime','?').replace('_',' ')}")

    m=regime_ctx.get('macro',{})
    if m.get('_meta',{}).get('available'):
        meta=m['_meta']
        L+=["",f"  GLOBAL (tone: {meta.get('global_tone','?')}  |  risk-off: {meta.get('risk_off_count',0)})"]
        for asset,lbl,fmt,pre in [('sp500','S&P 500',',.0f',''),('us_vix','US VIX','.2f',''),
                                   ('us_10y','US 10Y','.2f',''),('dxy','DXY','.2f',''),
                                   ('crude_wti','Crude WTI','.1f','$'),('gold','Gold',',.0f','$'),
                                   ('usd_inr','USD/INR','.2f','')]:
            d=m.get(asset,{}); p=d.get('price',np.nan); c=d.get('change_pct',np.nan)
            if not (isinstance(p,float) and np.isnan(p)) and p is not None:
                cs=f" ({c:+.2f}%)" if isinstance(c,float) and not np.isnan(c) else ""
                L.append(f"    {lbl:<14}: {pre}{p:{fmt}}{cs}")

    news=regime_ctx.get('news',{})
    L.append("")
    if news.get('has_veto'):
        L.append("  NEWS: *** VETO EVENT ***")
        for item in news.get('veto_items',[])[:2]: L.append(f"    !!! {item['title'][:65]}")
    elif news.get('has_high'):
        L.append(f"  NEWS: High-impact ({len(news.get('high_items',[]))} items)  |  {news.get('total_scanned',0)} scanned")
        for item in news.get('high_items',[])[:2]: L.append(f"    >>  {item['title'][:65]}")
    else:
        L.append(f"  NEWS: Clear  |  {news.get('total_scanned',0)} articles scanned")

    interp=regime_ctx.get('interpretation',{})
    L+=["",f"  REGIME : {interp.get('overall','?')}",f"  VERDICT: {interp.get('entry_view','?')}"]

    if interp.get('risk_flags'):
        L+=["","  RISK FLAGS:"]
        for rf in interp.get('risk_flags',[])[:3]: L.append(f"    ! {rf[:68]}")
    if interp.get('opportunities'):
        L+=["","  OPPORTUNITIES:"]
        for op in interp.get('opportunities',[])[:2]: L.append(f"    * {op[:68]}")

    prov={'claude':'Claude','groq':'Groq','rule-based':'Rule-based'}.get(
        ai_result.get('provider','rule-based'),'?')
    L+=["",sep,f"  REGIME NARRATIVE  [{prov}]",sep]
    for para in ai_result.get('narrative','').split('\n'):
        if para.strip(): L.append(f"  {para.strip()}")
    return "\n".join(L)


# ============================================================================
# MAIN ANALYSIS FUNCTIONS
# ============================================================================

def analyse_fund(scheme_code, with_regime=False, with_holdings=True):
    """
    Full equity fund analysis: Phase 1 + 2 + 3 (holdings) + optional Phase 4 (regime).

    scheme_code  : int — from find_fund() search
    with_regime  : bool — add live macro regime context (Phase 4). Adds ~30s.
    with_holdings: bool — fetch AMFI portfolio holdings (Phase 3). May be unavailable.

    Examples:
        analyse_fund(122639)                    # quick analysis
        analyse_fund(122639, with_regime=True)  # include live macro context
    """
    F=MFDataFetcher()
    _log.info(f"\nFetching NAV ({scheme_code})...")
    meta,nav=F.get_nav_history(scheme_code)
    if nav.empty: _log.warning(f"No NAV data for {scheme_code}"); return {}
    _log.info(f"  {meta.get('scheme_name','N/A')}")
    _log.info(f"  {nav['date'].iloc[0].strftime('%d %b %Y')} → {nav['date'].iloc[-1].strftime('%d %b %Y')}  ({len(nav):,} records)")

    category=meta.get('scheme_category','')
    if is_debt_fund(category):
        _log.info(f"  Detected as DEBT fund — routing to analyse_debt_fund()")
        return analyse_debt_fund(scheme_code, with_regime=with_regime)

    bench_code,bench_name=get_benchmark(category)
    bench=pd.DataFrame()
    if bench_code:
        _log.info("Fetching benchmark...")
        _,bench=F.get_nav_history(int(bench_code))

    _log.info("Fetching metadata...")
    mf_meta=F.get_fund_metadata(scheme_code)
    if 'captnemo' in mf_meta.get('meta_source',''):
        aum=mf_meta.get('aum_crore'); exp=mf_meta.get('expense_ratio')
        _log.info(f"  {'Rs{:,.0f}Cr'.format(aum) if aum else 'AUM N/A'}  |  {'{:.2f}%'.format(exp) if exp else 'ER N/A'}")

    portfolio=None
    if with_holdings:
        _log.info("Fetching portfolio holdings (AMFI)...")
        portfolio=F.get_portfolio_holdings(scheme_code)
        if portfolio.get('available'):
            _log.info(f"  {portfolio.get('total_stocks',0)} holdings fetched")
        else:
            _log.info("  Holdings unavailable from AMFI")

    _log.info("Computing metrics...")
    metrics={
        'as_of':nav['date'].iloc[-1].strftime('%d %b %Y'),
        'cagr':     {p:ReturnEngine.cagr(nav,y) for p,y in [('1Y',1),('3Y',3),('5Y',5),('Full',None)]},
        'benchmark_cagr':{p:(ReturnEngine.cagr(bench,y) if not bench.empty else np.nan)
                          for p,y in [('1Y',1),('3Y',3),('5Y',5),('Full',None)]},
        'rolling_1Y':ReturnEngine.rolling_returns(nav,1),
        'rolling_3Y':ReturnEngine.rolling_returns(nav,3),
        'rolling_5Y':ReturnEngine.rolling_returns(nav,5),
        'std_dev':   ReturnEngine.std_dev(nav),
        'sharpe':    RiskEngine.sharpe(nav),
        'sortino':   RiskEngine.sortino(nav),
        'max_drawdown':ReturnEngine.max_drawdown(nav),
        'sip_xirr':  ReturnEngine.sip_xirr(nav),
        'dd_covid':  ReturnEngine.drawdown_in_period(nav,'2020-02-01','2020-04-15'),
        'dd_2022':   ReturnEngine.drawdown_in_period(nav,'2022-01-01','2022-06-30'),
        'dd_ilfs':   ReturnEngine.drawdown_in_period(nav,'2018-09-01','2018-12-31'),
    }
    if not bench.empty:
        metrics['beta_alpha']       =RiskEngine.beta_alpha(nav,bench)
        metrics['information_ratio']=RiskEngine.information_ratio(nav,bench)
        metrics['capture_ratios']   =RiskEngine.capture_ratios(nav,bench)
    else:
        metrics['beta_alpha']       ={'beta':np.nan,'alpha':np.nan,'r_squared':np.nan}
        metrics['information_ratio']=np.nan
        metrics['capture_ratios']   ={'upside_capture':np.nan,'downside_capture':np.nan}

    _log.info("AI synthesis...")
    ai=EquityAISynthesis.synthesise(meta,mf_meta,metrics)
    _log.info(f"  Provider: {ai['provider']}")

    _log.info(_print_brief_equity(meta,mf_meta,metrics,ai,bench_name,portfolio))

    if with_regime:
        _log.info("\nFetching live regime context...")
        regime_ctx=RegimeContextEngine.build(category,'equity')
        regime_ai=RegimeAISynthesis.synthesise(
            regime_ctx,meta.get('scheme_name',''),category,'equity')
        _log.info(_print_regime_section(regime_ctx,regime_ai))

    return metrics


def analyse_debt_fund(scheme_code, with_regime=False, with_holdings=True):
    """
    Full debt fund analysis: Phase 1 + 5 + 3 (holdings) + optional Phase 4 (regime).

    scheme_code  : int — from find_debt_fund() search
    with_regime  : bool — add live macro regime context (adds ~30s)

    Example:
        find_debt_fund("HDFC short term debt direct growth")
        analyse_debt_fund(119016)
    """
    F=MFDataFetcher()
    _log.info(f"\nFetching NAV ({scheme_code})...")
    meta,nav=F.get_nav_history(scheme_code)
    if nav.empty: _log.warning(f"No NAV data for {scheme_code}"); return {}
    category=meta.get('scheme_category','')
    if not is_debt_fund(category):
        _log.info(f"  WARNING: '{category}' may not be a debt fund. Use analyse_fund() for equity.")
    _log.info(f"  {meta.get('scheme_name','N/A')}  |  Category: {category}")
    _log.info(f"  {nav['date'].iloc[0].strftime('%d %b %Y')} → {nav['date'].iloc[-1].strftime('%d %b %Y')}  ({len(nav):,} records)")

    debt_profile=get_debt_profile(category)
    _log.info(f"  Profile: {debt_profile['rate_sensitivity']} sensitivity  |  {debt_profile['primary_risk'].replace('_',' ')}")

    _log.info("Fetching metadata...")
    mf_meta=F.get_fund_metadata(scheme_code)
    if 'captnemo' in mf_meta.get('meta_source',''):
        aum=mf_meta.get('aum_crore'); exp=mf_meta.get('expense_ratio')
        _log.info(f"  {'Rs{:,.0f}Cr'.format(aum) if aum else 'AUM N/A'}  |  {'{:.2f}%'.format(exp) if exp else 'ER N/A'}")

    portfolio=None
    if with_holdings:
        _log.info("Fetching portfolio holdings (AMFI)...")
        portfolio=F.get_portfolio_holdings(scheme_code)
        if portfolio.get('available'):
            _log.info(f"  {portfolio.get('total_stocks',0)} holdings fetched")
        else:
            _log.info("  Holdings unavailable from AMFI")

    _log.info("Computing debt metrics...")
    bench_ret=debt_profile.get('benchmark_return',7.0)
    ytm_data=DebtReturnEngine.ytm_estimate(nav)
    sd=DebtReturnEngine.std_dev(nav)
    cagr3=DebtReturnEngine.cagr(nav,3)
    metrics={
        'as_of':      nav['date'].iloc[-1].strftime('%d %b %Y'),
        'cagr':       {p:DebtReturnEngine.cagr(nav,y) for p,y in [('1Y',1),('3Y',3),('5Y',5),('Full',None)]},
        'rolling_1Y': DebtReturnEngine.rolling_returns(nav,1,bench_ret),
        'rolling_3Y': DebtReturnEngine.rolling_returns(nav,3,bench_ret),
        'std_dev':    sd,
        'sharpe':     DebtReturnEngine.sharpe(nav),
        'max_drawdown':DebtReturnEngine.max_drawdown(nav),
        'sip_xirr':   DebtReturnEngine.sip_xirr(nav),
        'negative_months':DebtReturnEngine.negative_months(nav),
        'ytm_estimate':ytm_data,
        'sd_anomaly':  DebtAnomalyDetector.check_sd(sd,debt_profile.get('rate_sensitivity','MODERATE')),
        'expense_efficiency':DebtAnomalyDetector.check_expense_efficiency(
            cagr3,mf_meta.get('expense_ratio'),bench_ret),
        'rate_sensitivity_test':DebtReturnEngine.rate_sensitivity_test(nav),
    }

    _log.info("AI synthesis (debt-specific)...")
    ai=DebtAISynthesis.synthesise(meta,mf_meta,debt_profile,metrics)
    _log.info(f"  Provider: {ai['provider']}")

    _log.info(_print_brief_debt(meta,mf_meta,debt_profile,metrics,ai,portfolio))

    if with_regime:
        _log.info("\nFetching live regime context...")
        regime_ctx=RegimeContextEngine.build(category,'debt')
        regime_ai=RegimeAISynthesis.synthesise(
            regime_ctx,meta.get('scheme_name',''),category,'debt')
        _log.info(_print_regime_section(regime_ctx,regime_ai))

    return metrics


def analyse_portfolio(scheme_codes, names=None):
    """
    Phase 3: Portfolio overlap analysis for multiple funds.
    Best used for 2-4 funds you hold together.

    scheme_codes: list of int — from find_fund() searches
    names: optional list of short names for display

    Example:
        analyse_portfolio([122639, 120503], names=["PP Flexi", "HDFC Flexi"])
    """
    if len(scheme_codes) < 2:
        _log.info("Need at least 2 fund codes for overlap analysis")
        return

    F=MFDataFetcher()
    _log.info(f"\nFetching holdings for {len(scheme_codes)} funds...")
    fund_data=[]
    for i,code in enumerate(scheme_codes):
        name=names[i] if names and i<len(names) else f"Fund {code}"
        meta,_=F.get_nav_history(code)
        full_name=meta.get('scheme_name',name)
        _log.info(f"  Fetching holdings: {full_name[:50]}...")
        portfolio=F.get_portfolio_holdings(code)
        fund_data.append({'code':code,'name':full_name,'portfolio':portfolio})

    # Pairwise overlap
    _log.info("\nComputing pairwise overlap...")
    for i in range(len(fund_data)):
        for j in range(i+1,len(fund_data)):
            fa,fb=fund_data[i],fund_data[j]
            ha=fa['portfolio'].get('holdings',[]) if fa['portfolio'] else []
            hb=fb['portfolio'].get('holdings',[]) if fb['portfolio'] else []
            overlap=PortfolioOverlapEngine.calculate_overlap(ha,hb,fa['name'],fb['name'])
            PortfolioOverlapEngine.print_overlap(overlap)


def get_regime_context(fund_name, fund_category, fund_type='equity'):
    """
    Standalone live market regime context for any fund.

    fund_type: 'equity' or 'debt'

    Example:
        get_regime_context(
            "Parag Parikh Flexi Cap Fund",
            "Equity Scheme - Flexi Cap Fund",
            fund_type="equity"
        )
    """
    _log.info(f"\nFetching regime context: {fund_name}")
    regime_ctx=RegimeContextEngine.build(fund_category,fund_type)
    ai=RegimeAISynthesis.synthesise(regime_ctx,fund_name,fund_category,fund_type)
    _log.info(f"  Provider: {ai['provider']}")
    _log.info("\n"+"="*70)
    _log.info(f"  FINTELLIGENCE — MARKET REGIME CONTEXT")
    _log.info("="*70)
    _log.info(f"  Fund    : {fund_name}")
    _log.info(f"  Category: {fund_category}")
    _log.info("="*70)
    _log.info(_print_regime_section(regime_ctx,ai))
    _log.info("="*70)
    return {'regime_ctx':regime_ctx,'ai_result':ai}


# ============================================================================
# HELPERS
# ============================================================================

def find_fund(query, top=10):
    """Search for any equity fund by name. Returns scheme codes."""
    _log.info(f"\nSearching: '{query}'")
    r=MFDataFetcher.search(query,top)
    if r.empty: _log.info("No results."); return
    _log.info(f"\n{'Code':<10} Fund Name")
    _log.info("-"*80)
    for _,row in r.iterrows():
        _log.info(f"{row['scheme_code']:<10} {row['scheme_name'][:70]}")
    _log.info("\nUsage: analyse_fund(code)")


def find_debt_fund(query, top=10):
    """Search for any debt fund by name. Returns scheme codes."""
    _log.info(f"\nSearching debt fund: '{query}'")
    r=MFDataFetcher.search(query,top)
    if r.empty: _log.info("No results."); return
    _log.info(f"\n{'Code':<10} Fund Name")
    _log.info("-"*80)
    for _,row in r.iterrows():
        _log.info(f"{row['scheme_code']:<10} {row['scheme_name'][:70]}")
    _log.info("\nUsage: analyse_debt_fund(code)")


def compare_funds(code1, code2):
    """Side-by-side equity fund comparison. Both equity funds."""
    _log.info(f"\nComparing {code1} vs {code2}...")
    F=MFDataFetcher()
    m1,n1=F.get_nav_history(code1); m2,n2=F.get_nav_history(code2)
    if n1.empty or n2.empty: _log.info("Could not fetch one or both funds"); return
    bc1,_=get_benchmark(m1.get('scheme_category',''))
    bc2,_=get_benchmark(m2.get('scheme_category',''))
    _,b1=F.get_nav_history(int(bc1)) if bc1 else (None,pd.DataFrame())
    _,b2=F.get_nav_history(int(bc2)) if bc2 else (None,pd.DataFrame())
    def qm(nav,bench):
        ba=RiskEngine.beta_alpha(nav,bench) if not bench.empty else {}
        cr=RiskEngine.capture_ratios(nav,bench) if not bench.empty else {}
        return {'cagr3':ReturnEngine.cagr(nav,3),'cagr5':ReturnEngine.cagr(nav,5),
                'sd':ReturnEngine.std_dev(nav),'sharpe':RiskEngine.sharpe(nav),
                'sortino':RiskEngine.sortino(nav),'alpha':ba.get('alpha',np.nan),
                'beta':ba.get('beta',np.nan),
                'ir':RiskEngine.information_ratio(nav,bench) if not bench.empty else np.nan,
                'uc':cr.get('upside_capture',np.nan),'dc':cr.get('downside_capture',np.nan),
                'mdd':ReturnEngine.max_drawdown(nav).get('max_drawdown_pct',np.nan),
                'sip':ReturnEngine.sip_xirr(nav)}
    q1,q2=qm(n1,b1),qm(n2,b2)
    f1=m1.get('scheme_name',f'Fund {code1}')[:38]; f2=m2.get('scheme_name',f'Fund {code2}')[:38]
    _log.info(f"\n{'Metric':<22} {f1:<40} {f2}")
    _log.info("-"*103)
    def row(lbl,key,fmt='.1f',s='%',better='higher'):
        v1,v2=q1.get(key,np.nan),q2.get(key,np.nan)
        s1=f"{v1:{fmt}}{s}" if not np.isnan(v1) else "N/A"
        s2=f"{v2:{fmt}}{s}" if not np.isnan(v2) else "N/A"
        if not np.isnan(v1) and not np.isnan(v2):
            w1='<' if (v1>v2 if better=='higher' else v1<v2) else '  '
            w2='>' if (v2>v1 if better=='higher' else v2<v1) else '  '
            s1,s2=f"{s1} {w1}",f"{w2} {s2}"
        _log.info(f"  {lbl:<20} {s1:<42} {s2}")
    row("CAGR 3Y",'cagr3'); row("CAGR 5Y",'cagr5')
    row("Std Dev (3Y)",'sd',better='lower'); row("Sharpe (3Y)",'sharpe',fmt='.3f',s='')
    row("Sortino (3Y)",'sortino',fmt='.3f',s=''); row("Alpha (3Y)",'alpha')
    row("Beta (3Y)",'beta',fmt='.3f',s='',better='lower'); row("Info Ratio",'ir',fmt='.3f',s='')
    row("Upside Capture",'uc'); row("Downside Capture",'dc',better='lower')
    row("Max Drawdown",'mdd',better='lower'); row("SIP XIRR (3Y)",'sip')
    _log.info("\n  < > = better on that metric")


# ============================================================================
# API KEY + RUN
# ============================================================================

if _LLM_PROVIDER == "none":
    pass  # No API key configured — set GROQ_API_KEY or ANTHROPIC_API_KEY in .env


# ============================================================================
# HOW TO USE
# ============================================================================
#
# EQUITY FUND ANALYSIS:
#   find_fund("parag parikh flexi cap direct growth")
#   analyse_fund(122639)
#   analyse_fund(122639, with_regime=True)   # adds live macro context
#
# DEBT FUND ANALYSIS:
#   find_debt_fund("HDFC short term debt direct growth")
#   analyse_debt_fund(119016)
#   analyse_debt_fund(119016, with_regime=True)
#
# COMPARE TWO EQUITY FUNDS:
#   compare_funds(122639, 120503)
#
# PORTFOLIO OVERLAP:
#   find_fund("HDFC flexi cap direct")
#   find_fund("Axis bluechip direct growth")
#   analyse_portfolio([122639, XXXXX], names=["PP Flexi", "HDFC Flexi"])
#
# STANDALONE REGIME CONTEXT:
#   get_regime_context(
#       "Parag Parikh Flexi Cap",
#       "Equity Scheme - Flexi Cap Fund",
#       fund_type="equity"
#   )
# ============================================================================

if __name__ == "__main__":
    # Default run — search first, then analyse
    # Step 1: uncomment a find_fund line to get the scheme code
    # Step 2: uncomment analyse_fund with that code

    find_fund("parag parikh flexi cap direct growth")

    # analyse_fund(122639)
    # analyse_fund(122639, with_regime=True)

    # find_debt_fund("HDFC short term debt direct growth")
    # analyse_debt_fund(119016)
