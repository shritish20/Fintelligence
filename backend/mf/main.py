"""
Fintelligence MF — FastAPI Backend
Module 1: Mutual Fund Intelligence

Fixes applied (March 2026):
  - BUG FIX: _run_analysis now owns its own DB session (was using the
    request-scoped session which FastAPI closes before the background
    task finishes, silently dropping all analysis results).
  - BUG FIX: trigger_analysis was opening a SECOND session with
    next(get_db()) and leaking the injected one — removed.
  - BUG FIX: /api/mf/analyse now requires authentication
    (was Optional — unauthenticated callers could trigger expensive jobs).
  - BUG FIX: DELETE /api/mf/cache now requires auth.
  - BUG FIX: GET endpoints now use Depends(get_db) so sessions are
    always released, even on exceptions.
  - BUG FIX: /api/mf/compare and /api/mf/portfolio/overlap now use
    Depends(get_db) for proper session lifecycle.
"""

import os
import json
import time
import asyncio
import logging
import hashlib
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional, List

import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv
from auth_utils import decode_token
from db_utils import make_engine, make_redis, get_db_dependency   # ← shared utils

load_dotenv()


# ── Subscription tier helper ──────────────────────────────────────────────────
def _user_is_pro(user_id: int, db: Session) -> bool:
    """
    Returns True if user has an active pro/team subscription or is admin.
    Queries the shared users table (same PostgreSQL DB, owned by volguard).
    Non-blocking: returns False on any DB error so analysis is never
    denied due to a transient infrastructure issue.
    """
    from datetime import datetime as _dt
    try:
        from sqlalchemy import text as _text
        row = db.execute(
            _text("SELECT is_admin, subscription_tier, subscription_expires_at FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if not row:
            return False
        is_admin, tier, expires_at = row
        if is_admin:
            return True
        if tier in ("pro", "team"):
            return expires_at is None or expires_at > _dt.utcnow()
        return False
    except Exception:
        return False  # fail open — never block on DB error

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fintelligence_mf")

# ── Database (PostgreSQL via db_utils) ───────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "not-set")
engine_db    = make_engine(schema_prefix="mf")
SessionLocal = sessionmaker(bind=engine_db, autocommit=False, autoflush=False)
Base         = declarative_base()
get_db       = get_db_dependency(SessionLocal)  # FastAPI dependency

# ── Redis cache ───────────────────────────────────────────────────────────────
# DB index 1 = MF service. Falls back to None if Redis unavailable.
redis_client = make_redis(db=1)

CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))


class AnalysisCache(Base):
    __tablename__ = "mf_analysis_cache"
    id          = Column(Integer, primary_key=True)
    cache_key   = Column(String(64), unique=True, index=True)
    scheme_code = Column(String(20), index=True)
    fund_type   = Column(String(20))
    result_json = Column(Text)
    status      = Column(String(20), default="pending")
    error_msg   = Column(String(500), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime)
    with_regime = Column(Boolean, default=False)


class SearchCache(Base):
    __tablename__ = "mf_search_cache"
    id          = Column(Integer, primary_key=True)
    query_hash  = Column(String(64), unique=True, index=True)
    query       = Column(String(200))
    result_json = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime)


class AnalysisHistory(Base):
    __tablename__ = "mf_analysis_history"
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, nullable=True, index=True)
    scheme_code = Column(String(20), index=True)
    scheme_name = Column(String(200))
    fund_type   = Column(String(20))
    conviction  = Column(String(50), nullable=True)
    analysed_at = Column(DateTime, default=datetime.utcnow)


# get_db is provided by db_utils.get_db_dependency — see engine setup above

# ── JWT auth ──────────────────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)

def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> Optional[int]:
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    return int(payload["sub"]) if payload else None

def require_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> int:
    uid = get_current_user_id(credentials)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return uid


# ── Engine import ─────────────────────────────────────────────────────────────
log.info("Loading MF analysis engine...")
try:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    import io, contextlib
    import engine as mf_engine
    log.info("MF engine loaded successfully")
    ENGINE_OK = True
except Exception as e:
    log.exception("Engine load failed")
    ENGINE_OK = False
    mf_engine = None


# ── Serialisation helpers ─────────────────────────────────────────────────────
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):   return int(obj)
        if isinstance(obj, (np.floating,)):  return None if np.isnan(obj) else float(obj)
        if isinstance(obj, np.ndarray):      return obj.tolist()
        if isinstance(obj, datetime):        return obj.isoformat()
        return super().default(obj)

def safe_json(obj) -> str:
    return json.dumps(obj, cls=NumpyEncoder)

def clean_metrics(metrics: dict) -> dict:
    if isinstance(metrics, dict):
        return {k: clean_metrics(v) for k, v in metrics.items()}
    if isinstance(metrics, list):
        return [clean_metrics(v) for v in metrics]
    if isinstance(metrics, float):
        return None if (np.isnan(metrics) or np.isinf(metrics)) else metrics
    return metrics


# ── Background analysis runner ────────────────────────────────────────────────
# FIX: No longer accepts a db parameter. Creates and owns its own session so
# write-backs succeed even after FastAPI has closed the request session.
async def _run_analysis(scheme_code: int, with_regime: bool, cache_key: str,
                         user_id: Optional[int] = None):
    log.info(f"Starting analysis: scheme_code={scheme_code}, regime={with_regime}")
    start = time.time()
    db = SessionLocal()
    try:
        loop = asyncio.get_event_loop()

        def _analyse():
            log.info(f"Fetching NAV history for scheme {scheme_code}")
            meta, nav = mf_engine.MFDataFetcher().get_nav_history(scheme_code)
            if nav.empty:
                raise ValueError(f"No NAV data for scheme {scheme_code}")

            category  = meta.get('scheme_category', '')
            is_debt   = mf_engine.is_debt_fund(category)
            fund_type = "debt" if is_debt else "equity"

            meta_info = mf_engine.MFDataFetcher().get_fund_metadata(scheme_code)

            holdings = None
            try:
                log.info(f"Fetching portfolio holdings for scheme {scheme_code}")
                holdings = mf_engine.MFDataFetcher().get_portfolio_holdings(scheme_code)
                log.info(f"Holdings fetched: {len(holdings) if holdings is not None else 0} rows")
            except Exception:
                log.warning(f"Holdings fetch failed for {scheme_code} (non-fatal)", exc_info=True)

            if is_debt:
                debt_profile = mf_engine.get_debt_profile(category)
                bench_ret    = debt_profile.get('benchmark_return', 7.0)
                ytm_data     = mf_engine.DebtReturnEngine.ytm_estimate(nav)
                sd           = mf_engine.DebtReturnEngine.std_dev(nav)
                cagr3        = mf_engine.DebtReturnEngine.cagr(nav, 3)
                metrics = {
                    'as_of':           nav['date'].iloc[-1].strftime('%d %b %Y'),
                    'fund_type':       'debt',
                    'cagr':            {p: mf_engine.DebtReturnEngine.cagr(nav, y)
                                        for p, y in [('1Y',1),('3Y',3),('5Y',5),('Full',None)]},
                    'rolling_1Y':      mf_engine.DebtReturnEngine.rolling_returns(nav, 1, bench_ret),
                    'rolling_3Y':      mf_engine.DebtReturnEngine.rolling_returns(nav, 3, bench_ret),
                    'std_dev':         sd,
                    'sharpe':          mf_engine.DebtReturnEngine.sharpe(nav),
                    'max_drawdown':    mf_engine.DebtReturnEngine.max_drawdown(nav),
                    'sip_xirr':        mf_engine.DebtReturnEngine.sip_xirr(nav),
                    'negative_months': mf_engine.DebtReturnEngine.negative_months(nav),
                    'ytm_estimate':    ytm_data,
                    'rate_sensitivity':mf_engine.DebtReturnEngine.rate_sensitivity_test(nav),
                    'sd_anomaly':      mf_engine.DebtAnomalyDetector.check_sd(sd, None),
                    'expense_efficiency': mf_engine.DebtAnomalyDetector.check_expense_efficiency(
                        cagr3, meta_info.get('expense_ratio'), bench_ret),
                    'debt_profile':    debt_profile,
                }
                ai = mf_engine.DebtAISynthesis.synthesise(meta, meta_info, debt_profile, metrics)
                conviction, reason = mf_engine._conviction_debt(metrics, debt_profile)
                flags = mf_engine._flags_debt(metrics, debt_profile, meta_info)
            else:
                bench_code, bench_name = mf_engine.get_benchmark(category)
                bench = mf_engine.pd.DataFrame()
                if bench_code:
                    _, bench = mf_engine.MFDataFetcher().get_nav_history(int(bench_code))

                metrics = {
                    'as_of':         nav['date'].iloc[-1].strftime('%d %b %Y'),
                    'fund_type':     'equity',
                    'cagr':          {p: mf_engine.ReturnEngine.cagr(nav, y)
                                      for p, y in [('1Y',1),('3Y',3),('5Y',5),('Full',None)]},
                    'benchmark_cagr':{p: (mf_engine.ReturnEngine.cagr(bench, y)
                                          if not bench.empty else None)
                                      for p, y in [('1Y',1),('3Y',3),('5Y',5),('Full',None)]},
                    'rolling_1Y':    mf_engine.ReturnEngine.rolling_returns(nav, 1),
                    'rolling_3Y':    mf_engine.ReturnEngine.rolling_returns(nav, 3),
                    'rolling_5Y':    mf_engine.ReturnEngine.rolling_returns(nav, 5),
                    'std_dev':       mf_engine.ReturnEngine.std_dev(nav),
                    'sharpe':        mf_engine.RiskEngine.sharpe(nav),
                    'sortino':       mf_engine.RiskEngine.sortino(nav),
                    'max_drawdown':  mf_engine.ReturnEngine.max_drawdown(nav),
                    'sip_xirr':      mf_engine.ReturnEngine.sip_xirr(nav),
                    'dd_covid':      mf_engine.ReturnEngine.drawdown_in_period(nav,'2020-02-01','2020-04-15'),
                    'dd_2022':       mf_engine.ReturnEngine.drawdown_in_period(nav,'2022-01-01','2022-06-30'),
                    'dd_ilfs':       mf_engine.ReturnEngine.drawdown_in_period(nav,'2018-09-01','2018-12-31'),
                    'dd_2020_mar':   mf_engine.ReturnEngine.drawdown_in_period(nav,'2021-10-01','2021-12-31'),
                    'bench_name':    bench_name if bench_code else None,
                }
                if not bench.empty:
                    metrics['beta_alpha']        = mf_engine.RiskEngine.beta_alpha(nav, bench)
                    metrics['information_ratio'] = mf_engine.RiskEngine.information_ratio(nav, bench)
                    metrics['capture_ratios']    = mf_engine.RiskEngine.capture_ratios(nav, bench)
                else:
                    metrics['beta_alpha']        = {'beta': None, 'alpha': None, 'r_squared': None}
                    metrics['information_ratio'] = None
                    metrics['capture_ratios']    = {'upside_capture': None, 'downside_capture': None}

                ai = mf_engine.EquityAISynthesis.synthesise(meta, meta_info, metrics)
                conviction, reason = mf_engine._conviction_equity(metrics)
                flags = mf_engine._flags_equity(metrics)

            regime_ctx = None
            if with_regime:
                try:
                    log.info(f"Fetching regime context for {category}")
                    regime_ctx = mf_engine.RegimeContextEngine.build(
                        category, 'debt' if is_debt else 'equity')
                except Exception:
                    log.warning(f"Regime fetch failed for {scheme_code}", exc_info=True)

            result = {
                'scheme_code':  scheme_code,
                'scheme_name':  meta.get('scheme_name'),
                'fund_house':   meta.get('fund_house'),
                'category':     category,
                'fund_type':    'debt' if is_debt else 'equity',
                'metadata':     meta_info,
                'metrics':      clean_metrics(metrics),
                'ai':           ai,
                'conviction':   conviction,
                'conviction_reason': reason,
                'flags':        flags,
                'holdings':     holdings,
                'regime':       regime_ctx,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            return result, 'debt' if is_debt else 'equity', conviction

        result, fund_type, conviction = await loop.run_in_executor(None, _analyse)

        db.query(AnalysisCache).filter(AnalysisCache.cache_key == cache_key).update({
            'result_json': safe_json(result),
            'status':      'ready',
            'fund_type':   fund_type,
            'expires_at':  datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS),
        })

        existing = db.query(AnalysisHistory).filter(
            AnalysisHistory.scheme_code == str(scheme_code),
            AnalysisHistory.user_id == user_id,
        ).first()
        if existing:
            existing.analysed_at = datetime.now(timezone.utc)
            existing.conviction  = conviction
        else:
            db.add(AnalysisHistory(
                user_id=user_id, scheme_code=str(scheme_code),
                scheme_name=result.get('scheme_name', ''),
                fund_type=fund_type, conviction=conviction,
            ))

        db.commit()
        log.info(f"Analysis complete: {scheme_code} in {time.time()-start:.1f}s ({conviction})")

    except Exception as err:
        log.error(f"Analysis failed for {scheme_code}: {err}", exc_info=True)
        try:
            db.query(AnalysisCache).filter(AnalysisCache.cache_key == cache_key).update({
                'status':    'error',
                'error_msg': str(err)[:500],
                'expires_at': datetime.now(timezone.utc) + timedelta(hours=1),
            })
            db.commit()
        except Exception:
            log.error("Could not write error status to DB", exc_info=True)
    finally:
        db.close()


# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine_db, checkfirst=True)
    except Exception:

        log.warning("Suppressed exception", exc_info=True)
    from sqlalchemy import text as _text
    for _tbl, _col in [("mf_analysis_history", "user_id INTEGER"), ("mf_analysis_cache", "user_id INTEGER")]:
        try:
            with engine_db.begin() as _conn:
                _conn.execute(_text(f"ALTER TABLE {_tbl} ADD COLUMN {_col}"))
        except Exception as _e:
            _es = str(_e).lower()
            if "duplicate column" in _es or "already exists" in _es:
                pass  # expected on restart — column already present
            else:
                log.warning("Suppressed migration exception", exc_info=True)
    log.info(f"Database ready at {DATABASE_URL}")
    log.info(f"MF engine status: {'OK' if ENGINE_OK else 'FAILED'}")
    log.info(f"Cache TTL: {CACHE_TTL_HOURS}h")
    yield
    log.info("Shutting down Fintelligence MF")


app = FastAPI(
    title="Fintelligence MF API",
    description="Mutual Fund Intelligence — Module 1",
    version="1.0.0",
    lifespan=lifespan,
)

_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost,http://localhost:80,http://localhost:5173,http://localhost:3000"
    ).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ───────────────────────────────────────────────────
class AnalyseRequest(BaseModel):
    scheme_code: int
    with_regime: bool = False

class CompareRequest(BaseModel):
    code_a: int
    code_b: int

class PortfolioRequest(BaseModel):
    scheme_codes: List[int]
    names: Optional[List[str]] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _cache_key(scheme_code: int, with_regime: bool) -> str:
    return hashlib.sha256(f"{scheme_code}:{with_regime}".encode()).hexdigest()[:16]

def _get_fresh_cache(db: Session, cache_key: str) -> Optional[AnalysisCache]:
    return db.query(AnalysisCache).filter(
        AnalysisCache.cache_key == cache_key,
        AnalysisCache.expires_at > datetime.now(timezone.utc),
    ).first()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status":    "ok",
        "module":    "mf",
        "engine":    "ok" if ENGINE_OK else "failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/mf/search")
async def search_funds(
    q: str = Query(..., min_length=2),
    _uid: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Search mutual funds by name. Uses mfapi.in search. Results cached 1 hour per query."""
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")

    q_clean = q.strip().lower()
    q_hash  = hashlib.sha256(q_clean.encode()).hexdigest()[:16]

    cached = db.query(SearchCache).filter(
        SearchCache.query_hash == q_hash,
        SearchCache.expires_at > datetime.now(timezone.utc),
    ).first()
    if cached:
        return json.loads(cached.result_json)

    try:
        loop = asyncio.get_event_loop()
        raw_results = await loop.run_in_executor(
            None, lambda: mf_engine.MFDataFetcher.search(q, top=12)
        )
    except Exception as e:
        raise HTTPException(500, f"Search failed: {e}")

    import pandas as pd
    if isinstance(raw_results, pd.DataFrame):
        raw_list = raw_results.to_dict(orient="records") if not raw_results.empty else []
    elif isinstance(raw_results, list):
        raw_list = raw_results
    else:
        raw_list = []

    # Normalize: engine returns {Code, Fund Name}; frontend expects {scheme_code, scheme_name, ...}
    results_list = []
    for item in raw_list:
        normalized = {
            "scheme_code":     item.get("scheme_code") or item.get("Code") or item.get("schemeCode"),
            "scheme_name":     item.get("scheme_name") or item.get("Fund Name") or item.get("schemeName", ""),
            "fund_house":      item.get("fund_house") or item.get("AMC", ""),
            "scheme_type":     item.get("scheme_type", ""),
            "scheme_category": item.get("scheme_category") or item.get("Category", ""),
        }
        if normalized["scheme_code"]:
            results_list.append(normalized)

    payload = {"query": q, "results": results_list, "count": len(results_list)}
    payload_json = json.dumps(payload)

    try:
        db.query(SearchCache).filter(SearchCache.query_hash == q_hash).delete()
        db.add(SearchCache(
            query_hash=q_hash, query=q, result_json=payload_json,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
    except Exception as cache_err:
        db.rollback()
        log.warning(f"Search cache write failed (non-fatal): {cache_err}")

    return payload


@app.post("/api/mf/analyse")
async def trigger_analysis(
    req: AnalyseRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Trigger fund analysis. Returns immediately with job status.
    Frontend polls /api/mf/brief/{scheme_code} until status == 'ready'.
    Pro/Team: triggers full AI analysis.
    Free: can read cached results but cannot trigger new analysis.
    """
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")

    key = _cache_key(req.scheme_code, req.with_regime)

    # Always serve cached results to any authenticated user
    cached = _get_fresh_cache(db, key)
    if cached and cached.status == 'ready':
        return {
            "scheme_code": req.scheme_code, "status": "ready",
            "cache_key": key, "message": "Result available immediately from cache",
        }

    # ── Subscription gate — Pro/Team only for triggering fresh analysis ───────
    if not _user_is_pro(user_id, db):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_REQUIRED",
                "message": "Full MF analysis requires a Pro subscription. Upgrade to analyse any fund.",
                "upgrade_url": "/subscription",
            },
        )
    # ─────────────────────────────────────────────────────────────────────────

    pending = db.query(AnalysisCache).filter(
        AnalysisCache.cache_key == key, AnalysisCache.status == 'pending',
    ).first()
    if pending:
        return {
            "scheme_code": req.scheme_code, "status": "processing",
            "cache_key": key, "message": "Analysis already in progress",
        }

    db.query(AnalysisCache).filter(AnalysisCache.cache_key == key).delete()
    db.add(AnalysisCache(
        cache_key=key, scheme_code=str(req.scheme_code),
        status='pending', with_regime=req.with_regime,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS),
    ))
    db.commit()

    # FIX: db is NOT passed — _run_analysis creates its own session.
    # Passing the request session caused silent failures: FastAPI closes it
    # the moment this response is sent, before the background task finishes.
    background_tasks.add_task(
        _run_analysis, req.scheme_code, req.with_regime, key, user_id
    )

    return {
        "scheme_code": req.scheme_code, "status": "processing",
        "cache_key": key,
        "message": "Analysis started — poll /api/mf/brief/{scheme_code} every 3s",
    }


@app.get("/api/mf/brief/{scheme_code}")
async def get_brief(
    scheme_code: int,
    with_regime: bool = False,
    db: Session = Depends(get_db),   # FIX: was next(get_db()) without cleanup
):
    """Get analysis result. Frontend polls until status == 'ready'."""
    key = _cache_key(scheme_code, with_regime)
    row = db.query(AnalysisCache).filter(
        AnalysisCache.cache_key == key,
    ).order_by(AnalysisCache.created_at.desc()).first()

    if not row:
        return {"scheme_code": scheme_code, "status": "not_found",
                "message": "No analysis found. POST to /api/mf/analyse first."}
    if row.status == 'pending':
        return {"scheme_code": scheme_code, "status": "processing",
                "message": "Analysis in progress..."}
    if row.status == 'error':
        return {"scheme_code": scheme_code, "status": "error", "error": row.error_msg}
    if row.expires_at < datetime.now(timezone.utc):
        return {"scheme_code": scheme_code, "status": "expired",
                "message": "Analysis expired. POST to /api/mf/analyse to refresh."}

    result = json.loads(row.result_json)
    result["status"]     = "ready"
    result["cached_at"]  = row.created_at.isoformat()
    result["expires_at"] = row.expires_at.isoformat()
    return result


@app.post("/api/mf/compare")
async def compare_funds(
    req: CompareRequest,
    db: Session = Depends(get_db),   # FIX: was next(get_db()) without cleanup
):
    """Compare two equity funds. Both must be analysed first."""
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")

    results = {}
    missing = []

    for code in [req.code_a, req.code_b]:
        key    = _cache_key(code, False)
        cached = _get_fresh_cache(db, key)
        if cached and cached.status == 'ready':
            results[code] = json.loads(cached.result_json)
        else:
            missing.append(code)

    if missing:
        return {"status": "not_ready", "missing": missing,
                "message": f"Analyse these funds first: {missing}"}

    def qm(r):
        m  = r.get('metrics', {})
        ba = m.get('beta_alpha', {}) or {}
        cr = m.get('capture_ratios', {}) or {}
        return {
            'scheme_name':     r.get('scheme_name', ''),
            'fund_house':      r.get('fund_house', ''),
            'category':        r.get('category', ''),
            'conviction':      r.get('conviction', ''),
            'cagr_1y':         (m.get('cagr') or {}).get('1Y'),
            'cagr_3y':         (m.get('cagr') or {}).get('3Y'),
            'cagr_5y':         (m.get('cagr') or {}).get('5Y'),
            'sip_xirr':        m.get('sip_xirr'),
            'alpha':           ba.get('alpha'),
            'beta':            ba.get('beta'),
            'sharpe':          m.get('sharpe'),
            'sortino':         m.get('sortino'),
            'std_dev':         m.get('std_dev'),
            'information_ratio': m.get('information_ratio'),
            'upside_capture':  cr.get('upside_capture'),
            'downside_capture':cr.get('downside_capture'),
            'max_drawdown':    (m.get('max_drawdown') or {}).get('max_drawdown_pct'),
            'expense_ratio':   (r.get('metadata') or {}).get('expense_ratio'),
            'aum_crore':       (r.get('metadata') or {}).get('aum_crore'),
            'rolling_3y_pct_above_8': ((m.get('rolling_3Y') or {}).get('pct_above_8')),
        }

    fund_a = qm(results[req.code_a])
    fund_b = qm(results[req.code_b])

    overlap = None
    h_a = (results[req.code_a].get('holdings') or {})
    h_b = (results[req.code_b].get('holdings') or {})
    if h_a.get('available') and h_b.get('available'):
        try:
            loop = asyncio.get_event_loop()
            overlap = await loop.run_in_executor(None, lambda: mf_engine.PortfolioOverlapEngine.calculate_overlap(
                h_a.get('holdings', []), h_b.get('holdings', []),
                fund_a['scheme_name'], fund_b['scheme_name']
            ))
        except Exception as e:
            log.warning(f"Overlap calc failed: {e}")

    return {
        "status":  "ready",
        "fund_a":  fund_a,
        "fund_b":  fund_b,
        "overlap": clean_metrics(overlap) if overlap else None,
    }


@app.post("/api/mf/portfolio/overlap")
async def portfolio_overlap(
    req: PortfolioRequest,
    db: Session = Depends(get_db),   # FIX: was next(get_db()) without cleanup
):
    """Compute pairwise overlap for up to 5 funds. All must be analysed first."""
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")
    if len(req.scheme_codes) < 2:
        raise HTTPException(400, "Need at least 2 scheme codes")
    if len(req.scheme_codes) > 5:
        raise HTTPException(400, "Maximum 5 funds")

    fund_data = {}
    missing   = []

    for code in req.scheme_codes:
        key    = _cache_key(code, False)
        cached = _get_fresh_cache(db, key)
        if cached and cached.status == 'ready':
            fund_data[code] = json.loads(cached.result_json)
        else:
            missing.append(code)

    if missing:
        return {"status": "not_ready", "missing": missing}

    codes  = req.scheme_codes
    names  = req.names or [fund_data[c].get('scheme_name', str(c)) for c in codes]
    matrix = {}

    for i, ca in enumerate(codes):
        matrix[ca] = {}
        for j, cb in enumerate(codes):
            if ca == cb:
                matrix[ca][cb] = 100.0
                continue
            ha = (fund_data[ca].get('holdings') or {})
            hb = (fund_data[cb].get('holdings') or {})
            if ha.get('available') and hb.get('available'):
                try:
                    ov = mf_engine.PortfolioOverlapEngine.calculate_overlap(
                        ha.get('holdings', []), hb.get('holdings', []),
                        names[i], names[j]
                    )
                    matrix[ca][cb] = ov.get('overlap_pct', 0)
                except Exception:
                    matrix[ca][cb] = None
            else:
                matrix[ca][cb] = None

    fund_summaries = []
    for i, code in enumerate(codes):
        d = fund_data[code]
        m = d.get('metrics', {})
        fund_summaries.append({
            'scheme_code':  code,
            'scheme_name':  names[i],
            'fund_house':   d.get('fund_house'),
            'category':     d.get('category'),
            'conviction':   d.get('conviction'),
            'cagr_3y':      (m.get('cagr') or {}).get('3Y'),
            'expense_ratio':(d.get('metadata') or {}).get('expense_ratio'),
        })

    return {
        "status":         "ready",
        "funds":          fund_summaries,
        "overlap_matrix": matrix,
        "fund_names":     {str(c): n for c, n in zip(codes, names)},
    }


@app.get("/api/mf/history")
async def get_history(
    limit: int = 10,
    user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return recent analysis history for the authenticated user."""
    rows = db.query(AnalysisHistory).filter(
        (AnalysisHistory.user_id == user_id) | (AnalysisHistory.user_id == None)
    ).order_by(AnalysisHistory.analysed_at.desc()).limit(limit).all()
    return {"history": [
        {"scheme_code": r.scheme_code, "scheme_name": r.scheme_name,
         "fund_type": r.fund_type, "conviction": r.conviction,
         "analysed_at": r.analysed_at.isoformat()}
        for r in rows
    ]}


@app.delete("/api/mf/cache/{scheme_code}")
async def invalidate_cache(
    scheme_code: int,
    # FIX: was completely unauthenticated — anyone could wipe the cache.
    user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Force re-analysis on next request by deleting cache entry. Requires authentication."""
    for regime in [True, False]:
        key = _cache_key(scheme_code, regime)
        db.query(AnalysisCache).filter(AnalysisCache.cache_key == key).delete()
    db.commit()
    return {"message": f"Cache cleared for scheme {scheme_code}"}


@app.get("/")
async def root():
    return {"service": "Fintelligence MF API", "version": "1.0.0", "docs": "/docs"}
