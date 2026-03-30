"""
Fintelligence Equity — FastAPI Backend
Module 2: Equity Intelligence

Fixes applied (March 2026):
  - BUG FIX: _run_analysis now owns its own DB session (was using the
    request-scoped session which FastAPI closes before the background
    task finishes, silently dropping all analysis results).
  - BUG FIX: /api/equity/analyse now requires authentication
    (was Optional — unauthenticated callers could trigger expensive
    Gemini PDF-read jobs and drain quota).
  - BUG FIX: DELETE /api/equity/cache now requires auth
    (was fully unauthenticated — anyone could wipe the cache).
  - BUG FIX: GET endpoints now use Depends(get_db) so sessions are
    always released, even on exceptions.
"""

import os, json, time, asyncio, logging, hashlib
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
from db_utils import make_engine, make_redis, get_db_dependency

load_dotenv()


# ── Subscription tier helper ──────────────────────────────────────────────────
def _user_is_pro(user_id: int, db: Session) -> bool:
    """
    Returns True if user has an active pro/team subscription or is admin.
    Non-blocking: returns False on any DB error.
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
        return False  # fail open

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fintelligence_equity")

# ── Database (PostgreSQL via db_utils) ────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "not-set")
engine_db    = make_engine(schema_prefix="equity")
SessionLocal = sessionmaker(bind=engine_db, autocommit=False, autoflush=False)
Base         = declarative_base()
get_db       = get_db_dependency(SessionLocal)

# ── Redis cache (DB index 2 = equity) ────────────────────────────────────────
redis_client = make_redis(db=2)
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))


class AnalysisCache(Base):
    __tablename__ = "equity_analysis_cache"
    id           = Column(Integer, primary_key=True)
    cache_key    = Column(String(64), unique=True, index=True)
    bse_code     = Column(String(20), index=True)
    nse_symbol   = Column(String(20), index=True)
    company_name = Column(String(200))
    sector       = Column(String(50))
    result_json  = Column(Text)
    status       = Column(String(20), default="pending")
    error_msg    = Column(String(500), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    expires_at   = Column(DateTime)


class SearchCache(Base):
    __tablename__ = "equity_search_cache"
    id          = Column(Integer, primary_key=True)
    query_hash  = Column(String(64), unique=True, index=True)
    result_json = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime)


class AnalysisHistory(Base):
    __tablename__ = "equity_analysis_history"
    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, nullable=True, index=True)
    bse_code     = Column(String(20), index=True)
    company_name = Column(String(200))
    sector       = Column(String(50))
    conviction   = Column(String(50), nullable=True)
    analysed_at  = Column(DateTime, default=datetime.utcnow)


# get_db provided by db_utils — see engine setup above

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
log.info("Loading equity analysis engine...")
ENGINE_OK = False
eq_engine = None

try:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    import engine as eq_engine
    eq_engine.initialize()
    if eq_engine._GEM:
        log.info("Gemini client initialised")
    else:
        log.warning("GEMINI_API_KEY not set — PDF analysis unavailable")
    if eq_engine._GROQ:
        log.info("Groq client initialised")
    else:
        log.warning("GROQ_API_KEY not set — synthesis unavailable")
    ENGINE_OK = True
    log.info("Equity engine loaded successfully")
except Exception as e:
    log.error(f"Engine load failed: {e}", exc_info=True)


# ── JSON serialiser ───────────────────────────────────────────────────────────
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):  return int(obj)
        if isinstance(obj, (np.floating,)): return None if np.isnan(obj) else float(obj)
        if isinstance(obj, np.ndarray):     return obj.tolist()
        if isinstance(obj, datetime):       return obj.isoformat()
        return super().default(obj)

def safe_json(obj) -> str: return json.dumps(obj, cls=NumpyEncoder)

def clean(obj):
    if isinstance(obj, dict):  return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [clean(v) for v in obj]
    if isinstance(obj, float): return None if (np.isnan(obj) or np.isinf(obj)) else obj
    return obj


# ── Core analysis runner ──────────────────────────────────────────────────────
# FIX: No longer accepts a db parameter. Creates and owns its own session so
# write-backs succeed even after FastAPI has closed the request session.
async def _run_analysis(bse_code: str, nse_symbol: str, company_name: str,
                         sector: str, fy_year: int,
                         sector_params: dict, cache_key: str,
                         user_id: Optional[int] = None):
    log.info(f"Starting analysis: {company_name} ({bse_code}) FY{fy_year}")
    start = time.time()
    db = SessionLocal()
    try:
        loop = asyncio.get_event_loop()

        def _analyse():
            e = eq_engine
            profile = e.SECTOR_PROFILES.get(sector, e.SECTOR_PROFILES["diversified"])

            log.info(f"Fetching annual report PDF for BSE {bse_code} FY{fy_year}")
            pdf_bytes = e.fetch_pdf(bse_code, fy_year)
            if not pdf_bytes:
                raise ValueError(f"Could not fetch annual report for BSE {bse_code}")
            if not e._GEM:
                raise ValueError("GEMINI_API_KEY not configured")
            log.info(f"Gemini reading annual report for {company_name}")
            fin_raw, qual = e.gemini_read(pdf_bytes, company_name, fy_year, profile)
            log.info(f"Gemini read complete for {company_name}")

            log.info(f"Fetching Screener data for NSE:{nse_symbol}")
            log.info(f"Fetching Screener data for NSE:{nse_symbol}")
            sc = e.Screener.fetch(nse_symbol)
            sc_ok = sc.get('available', False)
            log.info(f"Screener data available: {sc_ok}")
            if not sc_ok:
                log.warning(f"Screener returned no data for NSE:{nse_symbol} — "
                            f"DCF and pattern recognition will use Gemini data only.")
            if sc["available"]:
                m = e.build_metrics(sc)
                for key, fkey in [("cwip","cwip"),("fixed_assets","fixed_assets")]:
                    if m.get(key) is None:
                        arr = fin_raw.get(fkey, [])
                        if isinstance(arr, list) and arr: m[key] = arr[0]
            else:
                m = {}
                for key, fkey in [
                    ("revenue","revenue"),("ebitda","ebitda"),("pat","pat"),
                    ("interest","interest"),("cfo","cfo"),("capex","capex"),
                    ("borrowings","borrowings"),("cash","cash"),
                    ("equity_cap","equity_capital"),("reserves","reserves")
                ]:
                    arr = fin_raw.get(fkey, [])
                    if isinstance(arr, list) and arr and arr[0] is not None:
                        m[key] = arr[0]
                eq  = (m.get("equity_cap") or 0) + (m.get("reserves") or 0)
                m["total_equity"] = eq if eq > 0 else None
                m["net_debt"]     = (m.get("borrowings") or 0) - (m.get("cash") or 0)
                m["_net_cash"]    = m["net_debt"] < 0
                if m.get("ebitda") and m.get("revenue") and m["revenue"] > 0:
                    m["ebitda_margin"] = round(m["ebitda"]/m["revenue"]*100, 1)
                if m.get("pat") and m.get("revenue") and m["revenue"] > 0:
                    m["pat_margin"] = round(m["pat"]/m["revenue"]*100, 1)
                if m.get("cfo") and m.get("pat") and m["pat"] != 0:
                    m["cfo_to_pat"] = round(m["cfo"]/m["pat"], 2)
                if m.get("ebitda") and m.get("interest") and m["interest"] > 0:
                    m["interest_cov"] = round(m["ebitda"]/m["interest"], 1)
                for key, fkey in [
                    ("rev_arr","revenue"),("pat_arr","pat"),("ebit_arr","ebitda"),
                    ("cfo_arr","cfo"),("roce_arr","roce_pct")
                ]:
                    arr = fin_raw.get(fkey, [])
                    if isinstance(arr, list): m[key] = [x for x in arr if x is not None]
                def _cagr(arr, yrs):
                    v = [x for x in arr if x is not None and x > 0]
                    if len(v) > yrs: return round(((v[0]/v[yrs])**(1/yrs)-1)*100, 1)
                ra = m.get("rev_arr",[]); pa = m.get("pat_arr",[])
                m["rev_cagr_3y"] = _cagr(ra,3); m["rev_cagr_5y"] = _cagr(ra,5)
                m["pat_cagr_3y"] = _cagr(pa,3); m["pat_cagr_5y"] = _cagr(pa,5)
                m["roce_arr"]    = fin_raw.get("roce_pct",[]) or []
                m["roce"]        = next((x for x in m["roce_arr"] if x is not None), None)

            peers = {}
            for sym, name in zip(profile["peers"], profile["peer_names"]):
                try:
                    ps = e.Screener.fetch(sym)
                    if ps["available"]:
                        pm = e.build_metrics(ps)
                        peers[name] = {k: pm.get(k) for k in [
                            "roce","ebitda_margin","pat_margin",
                            "nwc_days","cfo_to_pat","rev_cagr_5y","pe"]}
                    time.sleep(2)
                except Exception as pe:
                    log.warning(f"Peer {name} failed: {pe}")

            macro      = e.fetch_macro()
            macro_sigs = e.macro_sector_signal(macro, sector)
            sec_d      = e.compute_section_D(m)
            dcf        = e.compute_dcf(m, sector_params)
            spreads    = e.compute_peer_spreads(m, peers, profile)
            implied_g  = e.compute_implied_growth(m, sector_params)
            patterns   = e.run_pattern_recognition(m, profile)
            early_w    = e.run_early_warnings(m, profile)
            scenarios  = e.compute_probability_scenarios(m, sector_params, profile)
            conviction, cv_reason = e.compute_conviction(m, qual, sec_d, spreads)

            sec_i = {}
            if e._GROQ:
                try:
                    sec_i = e.groq_synthesis(
                        m, qual, sec_d, dcf, peers, spreads, implied_g,
                        patterns, scenarios, early_w, profile,
                        company_name, sector, fy_year, macro_sigs)
                except Exception as ge:
                    log.warning(f"Groq synthesis failed: {ge}")

            return {
                "bse_code": bse_code, "nse_symbol": nse_symbol,
                "company_name": company_name, "sector": sector, "fy_year": fy_year,
                "fin_raw": fin_raw, "metrics": m, "qualitative": qual,
                "sec_d": sec_d, "dcf": dcf, "peers": peers, "spreads": spreads,
                "implied_growth": implied_g, "patterns": patterns,
                "early_warnings": early_w, "scenarios": scenarios,
                "macro_signals": macro_sigs, "intelligence": sec_i,
                "conviction": conviction, "conviction_reason": cv_reason,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        result = await loop.run_in_executor(None, _analyse)
        result = clean(result)

        db.query(AnalysisCache).filter(AnalysisCache.cache_key == cache_key).update({
            "result_json":  safe_json(result),
            "status":       "ready",
            "company_name": result["company_name"],
            "expires_at":   datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS),
        })

        existing = db.query(AnalysisHistory).filter(
            AnalysisHistory.bse_code == bse_code,
            AnalysisHistory.user_id == user_id,
        ).first()
        if existing:
            existing.analysed_at = datetime.now(timezone.utc)
            existing.conviction  = result.get("conviction")
        else:
            db.add(AnalysisHistory(
                user_id=user_id, bse_code=bse_code, company_name=company_name,
                sector=sector, conviction=result.get("conviction")))

        db.commit()
        log.info(f"Analysis done: {company_name} in {time.time()-start:.1f}s ({result.get('conviction')})")

    except Exception as err:
        log.error(f"Analysis failed {bse_code}: {err}", exc_info=True)
        try:
            db.query(AnalysisCache).filter(AnalysisCache.cache_key == cache_key).update({
                "status":    "error",
                "error_msg": str(err)[:500],
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
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
    for _tbl, _col in [("equity_analysis_history", "user_id INTEGER"), ("equity_analysis_cache", "user_id INTEGER")]:
        try:
            with engine_db.begin() as _conn:
                _conn.execute(_text(f"ALTER TABLE {_tbl} ADD COLUMN {_col}"))
        except Exception as _e:
            _es = str(_e).lower()
            if "duplicate column" in _es or "already exists" in _es:
                pass  # expected on restart — column already present
            else:
                log.warning("Suppressed exception", exc_info=True)
    log.info(f"Database: {DATABASE_URL}")
    log.info(f"Engine: {'OK' if ENGINE_OK else 'FAILED'}")
    log.info(f"Gemini: {'OK' if (eq_engine and eq_engine._GEM) else 'NOT CONFIGURED'}")
    log.info(f"Groq:   {'OK' if (eq_engine and eq_engine._GROQ) else 'NOT CONFIGURED'}")
    yield
    log.info("Shutting down Fintelligence Equity")


app = FastAPI(
    title="Fintelligence Equity API",
    description="Equity Intelligence — Module 2",
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


# ── Models ────────────────────────────────────────────────────────────────────
class AnalyseRequest(BaseModel):
    bse_code:     str
    nse_symbol:   str
    company_name: str
    sector:       str  = "diversified"
    fy_year:      int  = 2024
    sector_params: dict = {
        "beta": 1.0, "risk_free_rate": 7.0, "equity_risk_premium": 6.5,
        "terminal_growth": 6.5, "cost_of_debt_pretax": 8.0, "tax_rate": 25.0,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _cache_key(bse_code: str, fy_year: int) -> str:
    return hashlib.sha256(f"{bse_code}:{fy_year}".encode()).hexdigest()[:16]

def _fresh(db: Session, key: str) -> Optional[AnalysisCache]:
    return db.query(AnalysisCache).filter(
        AnalysisCache.cache_key == key,
        AnalysisCache.expires_at > datetime.now(timezone.utc),
    ).first()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status":    "ok",
        "module":    "equity",
        "engine":    "ok" if ENGINE_OK else "failed",
        "gemini":    "ok" if (eq_engine and eq_engine._GEM) else "not_configured",
        "groq":      "ok" if (eq_engine and eq_engine._GROQ) else "not_configured",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/equity/search")
async def search_companies(
    q: str = Query(..., min_length=2),
    _uid: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Search BSE-listed companies via Screener.in. Results cached 1 hour."""
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")

    q_hash = hashlib.sha256(q.strip().lower().encode()).hexdigest()[:16]
    cached = db.query(SearchCache).filter(
        SearchCache.query_hash == q_hash,
        SearchCache.expires_at > datetime.now(timezone.utc),
    ).first()
    if cached:
        return json.loads(cached.result_json)

    results = []
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: eq_engine.Screener.fetch_search(q))
    except Exception:

        log.warning("Suppressed exception", exc_info=True)

    if not results:
        try:
            import requests as req_lib
            r = req_lib.get(
                f"https://www.screener.in/api/company/search/?q={q}&v=3&fts=1",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                raw_items = data if isinstance(data, list) else data.get("results", [])
                for item in raw_items[:12]:
                    if not item.get("name"):
                        continue
                    # Screener API returns "id" as BSE code
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
                log.info(f"Equity search fallback: {len(results)} results for '{q}'" )
        except Exception as se:
            log.warning(f"Search failed: {se}")

    payload = {"query": q, "results": results, "count": len(results)}
    db.query(SearchCache).filter(SearchCache.query_hash == q_hash).delete()
    db.add(SearchCache(
        query_hash=q_hash, result_json=json.dumps(payload),
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    ))
    db.commit()
    return payload


@app.post("/api/equity/analyse")
async def trigger_analysis(
    req: AnalyseRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Trigger equity analysis. Returns immediately with status.
    Analysis takes 30–120 seconds (Gemini PDF read + Screener + computation).
    Poll /api/equity/brief/{bse_code} every 5 s until status == 'ready'.
    Pro/Team: triggers full Gemini analysis.
    Free: can read cached results but cannot trigger new analysis.
    """
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")
    if not eq_engine._GEM:
        raise HTTPException(503, "GEMINI_API_KEY not configured")

    key = _cache_key(req.bse_code, req.fy_year)

    # Always serve cached results to any authenticated user
    cached = _fresh(db, key)
    if cached and cached.status == "ready":
        return {"bse_code": req.bse_code, "status": "ready",
                "message": "Result available immediately from cache"}

    # ── Subscription gate — Pro/Team only for triggering fresh analysis ───────
    if not _user_is_pro(user_id, db):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_REQUIRED",
                "message": "Equity analysis (annual report + sector DCF) requires a Pro subscription.",
                "upgrade_url": "/subscription",
            },
        )
    # ─────────────────────────────────────────────────────────────────────────

    pending = db.query(AnalysisCache).filter(
        AnalysisCache.cache_key == key, AnalysisCache.status == "pending").first()
    if pending:
        return {"bse_code": req.bse_code, "status": "processing",
                "message": "Analysis already in progress"}

    db.query(AnalysisCache).filter(AnalysisCache.cache_key == key).delete()
    db.add(AnalysisCache(
        cache_key=key, bse_code=req.bse_code, nse_symbol=req.nse_symbol,
        company_name=req.company_name, sector=req.sector,
        status="pending", created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS),
    ))
    db.commit()

    # db is NOT passed — _run_analysis creates its own session.
    # Passing the request session caused silent failures: FastAPI closes it
    # the moment this response is sent, before the background task finishes.
    background_tasks.add_task(
        _run_analysis, req.bse_code, req.nse_symbol, req.company_name,
        req.sector, req.fy_year, req.sector_params, key, user_id
    )

    return {"bse_code": req.bse_code, "status": "processing",
            "message": "Analysis started — poll /api/equity/brief/{bse_code} every 5s"}


@app.get("/api/equity/brief/{bse_code}")
async def get_brief(
    bse_code: str,
    fy_year: int = 2024,
    db: Session = Depends(get_db),   # FIX: was next(get_db()) without cleanup
):
    """Poll until status == 'ready'. Returns full analysis result."""
    key = _cache_key(bse_code, fy_year)
    row = db.query(AnalysisCache).filter(
        AnalysisCache.cache_key == key
    ).order_by(AnalysisCache.created_at.desc()).first()

    if not row:
        return {"bse_code": bse_code, "status": "not_found",
                "message": "No analysis found. POST to /api/equity/analyse first."}
    if row.status == "pending":
        return {"bse_code": bse_code, "status": "processing",
                "message": "Analysis in progress — Gemini reading annual report PDF..."}
    if row.status == "error":
        return {"bse_code": bse_code, "status": "error", "error": row.error_msg}
    if row.expires_at < datetime.now(timezone.utc):
        return {"bse_code": bse_code, "status": "expired",
                "message": "Analysis expired. POST to /api/equity/analyse to refresh."}

    result = json.loads(row.result_json)
    result["status"]     = "ready"
    result["cached_at"]  = row.created_at.isoformat()
    result["expires_at"] = row.expires_at.isoformat()
    return result


@app.get("/api/equity/sectors")
async def get_sectors():
    """Return available sector profiles."""
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")
    return {
        "sectors": [
            {
                "key":          k,
                "peers":        v.get("peer_names", []),
                "value_driver": v.get("value_driver","")[:120],
                "normal_roce":  v.get("normal_roce"),
                "normal_margin":v.get("normal_margin"),
            }
            for k, v in eq_engine.SECTOR_PROFILES.items()
        ]
    }


@app.get("/api/equity/sector/{sector}/peers")
async def get_peer_data(sector: str):
    """Fetch current peer metrics for a sector from Screener."""
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")
    profile = eq_engine.SECTOR_PROFILES.get(sector)
    if not profile:
        raise HTTPException(404, f"Unknown sector: {sector}")

    loop  = asyncio.get_event_loop()
    peers = {}

    async def _fetch_peer(sym, name):
        try:
            ps = await loop.run_in_executor(None, lambda: eq_engine.Screener.fetch(sym))
            if ps["available"]:
                pm = eq_engine.build_metrics(ps)
                peers[name] = {k: pm.get(k) for k in [
                    "revenue","roce","ebitda_margin","pat_margin",
                    "nwc_days","cfo_to_pat","rev_cagr_5y","pe","market_cap_cr"]}
            await asyncio.sleep(2)
        except Exception as e:
            log.warning(f"Peer {name} failed: {e}")

    await asyncio.gather(*[
        _fetch_peer(sym, name)
        for sym, name in zip(profile["peers"], profile["peer_names"])
    ])
    return {
        "sector": sector,
        "peers":  peers,
        "profile": {
            "normal_roce":   profile.get("normal_roce"),
            "normal_margin": profile.get("normal_margin"),
            "value_driver":  profile.get("value_driver",""),
            "break_point":   profile.get("break_point",""),
            "hidden_alpha":  profile.get("hidden_alpha",""),
        },
    }


@app.get("/api/equity/history")
async def get_history(
    limit: int = 10,
    user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = db.query(AnalysisHistory).filter(
        (AnalysisHistory.user_id == user_id) | (AnalysisHistory.user_id == None)
    ).order_by(AnalysisHistory.analysed_at.desc()).limit(limit).all()
    return {"history": [
        {"bse_code": r.bse_code, "company_name": r.company_name,
         "sector": r.sector, "conviction": r.conviction,
         "analysed_at": r.analysed_at.isoformat()}
        for r in rows
    ]}


@app.delete("/api/equity/cache/{bse_code}")
async def invalidate_cache(
    bse_code: str,
    fy_year: int = 2024,
    # FIX: was completely unauthenticated — anyone could wipe the cache.
    user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Clear cached analysis for a stock. Requires authentication."""
    key = _cache_key(bse_code, fy_year)
    db.query(AnalysisCache).filter(AnalysisCache.cache_key == key).delete()
    db.commit()
    return {"message": f"Cache cleared for BSE {bse_code}"}


@app.get("/api/equity/macro/{sector}")
async def get_macro_signals(sector: str, _uid: int = Depends(require_user)):
    """Fetch real-time macro signals for a sector."""
    if not ENGINE_OK:
        raise HTTPException(503, "Engine not available")
    loop  = asyncio.get_event_loop()
    macro = await loop.run_in_executor(None, eq_engine.fetch_macro)
    sigs  = eq_engine.macro_sector_signal(macro, sector)
    return {"sector": sector, "signals": sigs, "raw": clean(macro)}


@app.get("/")
async def root():
    return {"service": "Fintelligence Equity API", "version": "1.0.0", "docs": "/docs"}
