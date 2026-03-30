"""
Fintelligence Tax — FastAPI Backend
Module 4: Tax Intelligence

Flow:
  - /api/tax/brief  → Returns full tax brief (mock or real)
  - /api/tax/upload → Accepts Zerodha P&L + CAMS statement
  - /api/tax/query  → Answers Finance Act queries (Gemini reads PDF)
  - /api/health     → Status
"""

import os, json, logging, hashlib
from datetime import date, datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from auth_utils import decode_token
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from fastapi import Depends as SQLDepends
from db_utils import make_engine, make_redis, get_db_dependency

load_dotenv()

# ── Database (PostgreSQL via db_utils) ────────────────────────────────────────
_engine  = make_engine(schema_prefix="tax")
_Base    = declarative_base()
_Session = sessionmaker(bind=_engine, expire_on_commit=False)
get_db   = get_db_dependency(_Session)

# ── Redis cache (DB index 3 = tax) ───────────────────────────────────────────
redis_client = make_redis(db=3)

class TaxPortfolio(_Base):
    """Stores the last uploaded portfolio per user so real brief survives restarts."""
    __tablename__ = "tax_portfolios"
    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, unique=True, index=True, nullable=False)
    portfolio_json = Column(Text, nullable=False)
    zerodha_file = Column(String(255), nullable=True)
    cams_file    = Column(String(255), nullable=True)
    uploaded_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("fintelligence_tax")

# ── Import modules ────────────────────────────────────────────────────────────
from tax_rules import (
    classify_instrument, compute_capital_gain_tax, compute_slab_tax,
    compute_fo_deductible_expenses, compute_advance_tax_schedule,
    compute_ltcg_harvest_opportunity, regime_comparison,
    InstrumentType, LTCG_EXEMPTION_ANNUAL,
)
from mock_portfolio import MOCK_PORTFOLIO
from file_parser   import parse_zerodha_tax_pnl, parse_cams_statement, build_portfolio_from_uploads
from narrative_writer import write_narrative, write_flag_narrative, write_query_answer
from gemini_reader import extract_rule_from_finance_act, answer_tax_query


# ── Date serialiser ───────────────────────────────────────────────────────────
class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)): return obj.isoformat()
        return super().default(obj)

def jsonify(obj): return json.loads(json.dumps(obj, cls=DateEncoder))


# ── Brief generator ───────────────────────────────────────────────────────────

def generate_tax_brief(portfolio: dict) -> dict:
    """
    Core function: takes portfolio data → returns full tax brief.
    Python computes everything. Gemini extracts rules. Claude/Groq writes narrative.
    """
    fo        = portfolio.get("fo", {})
    mf        = portfolio.get("mf_holdings", [])
    equity    = portfolio.get("equity_holdings", [])
    gsecs     = portfolio.get("gsec_holdings", [])
    sgbs      = portfolio.get("sgb_holdings", [])
    other_inc = portfolio.get("other_income", {})
    summary   = portfolio.get("summary", {})
    flags     = portfolio.get("flags", [])

    # ── 1. F&O computation ────────────────────────────────────────────────────
    expenses_detail = compute_fo_deductible_expenses(fo.get("expenses", {}))
    net_fo          = fo.get("net_taxable_fo", fo.get("net_pnl", 0))

    # ── 2. LTCG harvest opportunities ────────────────────────────────────────
    ltcg_used = summary.get("ltcg_realised_this_fy",
                portfolio.get("ltcg_realised_this_fy", 0))

    all_ltcg_holdings = [
        h for h in (equity + mf)
        if h.get("qualifies_ltcg") and h.get("unrealised_gain", 0) > 0
    ]
    harvest_opps = compute_ltcg_harvest_opportunity(all_ltcg_holdings, ltcg_used)

    # ── 3. Regime comparison ──────────────────────────────────────────────────
    total_slab = portfolio.get("total_slab_income",
                 net_fo + other_inc.get("total", 0))
    old_deductions = portfolio.get("old_regime_deductions", 150_000)
    stcg_realised  = portfolio.get("stcg_realised_this_fy", 0)
    ltcg_above_ex  = max(0, ltcg_used - LTCG_EXEMPTION_ANNUAL)

    regime = regime_comparison(
        total_slab_income=total_slab,
        stcg=stcg_realised,
        ltcg=ltcg_used,
        ltcg_exemption_used=0,
        old_regime_deductions=old_deductions,
    )

    # ── 4. Advance tax schedule ───────────────────────────────────────────────
    estimated_tax = min(
        regime["new_regime"]["total_tax"],
        regime["old_regime"]["total_tax"]
    )
    advance_sched = compute_advance_tax_schedule(
        estimated_annual_tax=estimated_tax,
        tax_paid_so_far=fo.get("advance_tax_paid", 0),
    )

    # ── 5. MF tax breakdown ───────────────────────────────────────────────────
    mf_breakdown = []
    for fund in mf:
        if fund.get("unrealised_gain", 0) <= 0:
            continue
        fund_type = fund.get("type", "equity_mf")
        inst_map  = {
            "equity_mf":            InstrumentType.EQUITY_MF,
            "debt_mf_pre_apr2023":  InstrumentType.DEBT_MF_PRE_APR2023,
            "debt_mf_post_apr2023": InstrumentType.DEBT_MF_POST_APR2023,
        }
        inst = inst_map.get(fund_type, InstrumentType.EQUITY_MF)

        p_date = fund.get("purchase_date", date.today())
        if isinstance(p_date, str):
            p_date = date.fromisoformat(p_date)

        rule  = classify_instrument(inst, p_date, date.today())
        tax   = compute_capital_gain_tax(
            gain=fund.get("unrealised_gain", 0),
            rule=rule,
            ltcg_exemption_used=ltcg_used,
        )

        mf_breakdown.append({
            "name":        fund.get("name", ""),
            "type":        fund_type,
            "gain":        fund.get("unrealised_gain", 0),
            "treatment":   rule.treatment,
            "act_section": rule.act_section,
            "act_year":    rule.act_year,
            "tax_if_sold_today": tax.get("tax", 0),
            "note":        rule.note,
        })

    # ── 6. Add narratives to flags (Claude/Groq) ─────────────────────────────
    flags_with_narrative = []
    for flag in flags:
        narrative = write_flag_narrative(flag)
        flags_with_narrative.append({**flag, "narrative": narrative})

    # ── 7. Income breakdown table ─────────────────────────────────────────────
    income_breakdown = []

    if net_fo:
        income_breakdown.append({
            "head":        "F&O Business Income",
            "amount":      net_fo,
            "treatment":   "Non-speculative business income — added to total income",
            "tax_at_slab": round(net_fo * 0.30 * 1.04, 0),
            "act_ref":     "Section 43(5), Income Tax Act",
        })

    if stcg_realised:
        income_breakdown.append({
            "head":        "Equity STCG (realised)",
            "amount":      stcg_realised,
            "treatment":   "STCG at 20% flat",
            "tax_at_slab": round(stcg_realised * 0.20 * 1.04, 0),
            "act_ref":     "Section 111A, Finance Act 2024 (No. 2 of 2024)",
        })

    if ltcg_used:
        taxable_ltcg = max(0, ltcg_used - LTCG_EXEMPTION_ANNUAL)
        income_breakdown.append({
            "head":        "Equity LTCG (realised)",
            "amount":      ltcg_used,
            "exemption":   min(ltcg_used, LTCG_EXEMPTION_ANNUAL),
            "taxable":     taxable_ltcg,
            "treatment":   f"LTCG at 12.5% above ₹{LTCG_EXEMPTION_ANNUAL:,} exemption",
            "tax_at_slab": round(taxable_ltcg * 0.125 * 1.04, 0),
            "act_ref":     "Section 112A, Finance Act 2024",
        })

    if other_inc.get("gsec_interest"):
        income_breakdown.append({
            "head":        "G-Sec Interest",
            "amount":      other_inc["gsec_interest"],
            "treatment":   "Income from Other Sources — slab rate",
            "tax_at_slab": round(other_inc["gsec_interest"] * 0.30 * 1.04, 0),
            "act_ref":     "Section 56, Income Tax Act",
        })

    if other_inc.get("sgb_interest"):
        income_breakdown.append({
            "head":        "SGB Interest (2.5% p.a.)",
            "amount":      other_inc["sgb_interest"],
            "treatment":   "Income from Other Sources — slab rate",
            "tax_at_slab": round(other_inc["sgb_interest"] * 0.30 * 1.04, 0),
            "act_ref":     "Section 56, Income Tax Act",
        })

    # ── Assemble brief ────────────────────────────────────────────────────────
    brief = {
        "generated_at":   datetime.utcnow().isoformat(),
        "financial_year": "2025-26",
        "assessment_year":"2026-27",

        # Summary card
        "summary": {
            "estimated_tax_new_regime":  regime["new_regime"]["total_tax"],
            "estimated_tax_old_regime":  regime["old_regime"]["total_tax"],
            "better_regime":             regime["better_regime"],
            "regime_saving":             regime["saving"],
            "ltcg_exemption_used":       ltcg_used,
            "ltcg_exemption_remaining":  max(0, LTCG_EXEMPTION_ANNUAL - ltcg_used),
            "total_harvest_opportunity": sum(h["harvestable"] for h in harvest_opps),
            "total_deductible_expenses": expenses_detail["total"],
            "act_ref_regime":            regime["act_ref"],
        },

        # Income breakdown
        "income_breakdown": income_breakdown,

        # Regime comparison
        "regime_comparison": regime,

        # Flags
        "flags": flags_with_narrative,

        # Harvest opportunities
        "harvest_opportunities": harvest_opps,

        # F&O detail
        "fo_detail": {
            "gross_profit":    fo.get("gross_profit", 0),
            "gross_loss":      fo.get("gross_loss", 0),
            "net_pnl":         fo.get("net_pnl", 0),
            "expenses":        expenses_detail,
            "net_taxable":     net_fo,
            "act_ref":         "Section 43(5), Section 37(1) — Income Tax Act",
        },

        # MF breakdown
        "mf_breakdown": mf_breakdown,

        # Advance tax
        "advance_tax": {
            "estimated_annual_tax": estimated_tax,
            "paid_so_far":          fo.get("advance_tax_paid", 0),
            "schedule":             advance_sched,
            "act_ref":              "Section 211, Section 234C — Income Tax Act",
        },
    }

    return jsonify(brief)


# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Check for Finance Act PDFs
    from pathlib import Path
    tax_docs = Path("tax_docs")
    pdfs = list(tax_docs.glob("*.pdf")) if tax_docs.exists() else []
    log.info(f"Finance Act PDFs found: {len(pdfs)}")
    if not pdfs:
        log.warning("No Finance Act PDFs in tax_docs/. "
                    "Download from incometaxindia.gov.in for full functionality.")

    gemini_ok = bool(os.getenv("GEMINI_API_KEY"))
    claude_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
    groq_ok   = bool(os.getenv("GROQ_API_KEY"))
    log.info(f"Gemini: {'OK' if gemini_ok else 'NOT SET'} | "
             f"Claude: {'OK' if claude_ok else 'NOT SET'} | "
             f"Groq: {'OK' if groq_ok else 'NOT SET'}")
    if not gemini_ok:
        log.warning("GEMINI_API_KEY not set — Finance Act rule extraction unavailable. "
                    "Tax computations will run from Python rules engine only.")
    if not claude_ok and not groq_ok:
        log.warning("No LLM keys — using rule-based narrative fallback.")
    yield
    log.info("Shutting down Fintelligence Tax")


app = FastAPI(
    title="Fintelligence Tax API",
    description="Tax Intelligence — Module 4 | Source of truth: Finance Acts",
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


# ── Request models ────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    from pathlib import Path
    pdfs = list(Path("tax_docs").glob("*.pdf")) if Path("tax_docs").exists() else []
    return {
        "status":   "ok",
        "module":   "tax",
        "gemini":   "ok" if os.getenv("GEMINI_API_KEY") else "not_configured",
        "claude":   "ok" if os.getenv("ANTHROPIC_API_KEY") else "not_configured",
        "groq":     "ok" if os.getenv("GROQ_API_KEY") else "not_configured",
        "finance_act_pdfs": [p.name for p in pdfs],
        "pdf_count":len(pdfs),
        "timestamp":datetime.utcnow().isoformat(),
    }


@app.get("/api/tax/brief/demo")
async def get_demo_brief():
    """
    Returns the full tax brief using the mock portfolio.
    This is what the user sees on first load before uploading their data.
    Numbers are realistic (not random) — simulates an actual options seller.
    """
    brief = generate_tax_brief(MOCK_PORTFOLIO)
    brief["is_demo"] = True
    brief["demo_note"] = (
        "Demo mode — simulated portfolio of a Nifty options seller with "
        "equity MFs, direct equity, G-Secs, and SGBs. "
        "Upload your Zerodha Tax P&L and CAMS statement to see your actual picture."
    )
    return brief


@app.get("/api/tax/brief/real")
async def get_real_brief(
    user_id: int = Depends(require_user),
    db: Session = SQLDepends(get_db),
):
    """Returns the full tax brief from last uploaded portfolio data for this user."""
    row = db.query(TaxPortfolio).filter(TaxPortfolio.user_id == user_id).first()
    if not row:
        raise HTTPException(404, "No uploaded data found. Upload your Zerodha P&L and/or CAMS statement first.")
    portfolio = json.loads(row.portfolio_json)
    brief = generate_tax_brief(portfolio)
    brief["is_demo"] = False
    brief["data_sources"] = {
        "zerodha":    row.zerodha_file,
        "cams":       row.cams_file,
        "uploaded_at":row.uploaded_at.isoformat() if row.uploaded_at else None,
    }
    return brief


@app.post("/api/tax/upload")
async def upload_statements(
    zerodha_file: Optional[UploadFile] = File(None),
    cams_file:    Optional[UploadFile] = File(None),
    user_id: int = Depends(require_user),
):
    """
    Accept Zerodha Tax P&L (Excel/CSV) and/or CAMS statement (Excel/CSV).
    Returns the full tax brief generated from uploaded data.
    """
    if not zerodha_file and not cams_file:
        raise HTTPException(400, "Upload at least one file: Zerodha Tax P&L or CAMS statement")

    zerodha_data = None
    cams_data    = None

    MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB — matches nginx client_max_body_size

    if zerodha_file:
        content = await zerodha_file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Zerodha file too large ({len(content)//1024}KB). Maximum is 15MB.")
        zerodha_data = parse_zerodha_tax_pnl(content, zerodha_file.filename)
        if zerodha_data.get("error"):
            log.warning(f"Zerodha parse warning: {zerodha_data['error']}")

    if cams_file:
        content = await cams_file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"CAMS file too large ({len(content)//1024}KB). Maximum is 15MB.")
        cams_data = parse_cams_statement(content, cams_file.filename)
        if cams_data.get("error"):
            log.warning(f"CAMS parse warning: {cams_data['error']}")

    portfolio = build_portfolio_from_uploads(zerodha_data, cams_data)
    brief     = generate_tax_brief(portfolio)
    brief["is_demo"] = False
    brief["data_sources"] = {
        "zerodha":    zerodha_file.filename if zerodha_file else None,
        "cams":       cams_file.filename if cams_file else None,
        "uploaded_at":datetime.utcnow().isoformat(),
    }

    # Persist portfolio so /brief/real works after container restarts
    db = next(get_db())
    try:
        row = db.query(TaxPortfolio).filter(TaxPortfolio.user_id == user_id).first()
        if row:
            row.portfolio_json = json.dumps(portfolio, default=str)
            row.zerodha_file   = zerodha_file.filename if zerodha_file else None
            row.cams_file      = cams_file.filename if cams_file else None
            row.uploaded_at    = datetime.utcnow()
        else:
            db.add(TaxPortfolio(
                user_id        = user_id,
                portfolio_json = json.dumps(portfolio, default=str),
                zerodha_file   = zerodha_file.filename if zerodha_file else None,
                cams_file      = cams_file.filename if cams_file else None,
            ))
        db.commit()
        log.info(f"Tax portfolio saved for user_id={user_id}")
    except Exception:
        log.warning("Failed to persist tax portfolio to DB (non-fatal)", exc_info=True)
        db.rollback()
    finally:
        db.close()

    return brief


@app.post("/api/tax/query")
async def tax_query(req: QueryRequest, user_id: int = Depends(require_user)):
    """
    Answer a tax question. Only answers:
    1. What does a Finance Act section say?
    2. How does a rule apply to the user's holdings?

    Refuses investment advice, stock tips, and anything non-tax.
    Source of truth: Finance Act PDFs read by Gemini.
    """
    if len(req.query.strip()) < 5:
        raise HTTPException(400, "Query too short")

    # Build portfolio context for portfolio-specific queries
    portfolio_context = {
        "fo_profit_ytd":   MOCK_PORTFOLIO["fo"]["net_pnl"],
        "equity_holdings": MOCK_PORTFOLIO["equity_holdings"],
        "mf_holdings":     MOCK_PORTFOLIO["mf_holdings"],
        "ltcg_used_ytd":   MOCK_PORTFOLIO["summary"]["ltcg_realised_this_fy"],
    }

    # Gemini reads Finance Act PDF
    query_result = answer_tax_query(req.query, portfolio_context)

    # Compute portfolio-specific numbers if applicable
    portfolio_computation = {}
    if query_result.get("applies_to_portfolio"):
        portfolio_computation = {"raw_context": portfolio_context}

    # Claude/Groq writes the answer
    narrative = write_query_answer(query_result, portfolio_computation)

    return {
        "query":     req.query,
        "answer":    narrative,
        "section":   query_result.get("primary_section"),
        "act":       query_result.get("act_name"),
        "effective": query_result.get("effective_from"),
        "answerable":query_result.get("is_answerable_from_document", False),
        "redirect":  query_result.get("redirect_module"),
        "caveat":    "Verify with a CA before filing.",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/tax/finance-acts")
async def list_finance_acts():
    """List available Finance Act PDFs and download instructions."""
    from pathlib import Path
    tax_docs = Path("tax_docs")
    pdfs     = list(tax_docs.glob("*.pdf")) if tax_docs.exists() else []

    return {
        "available_pdfs": [p.name for p in pdfs],
        "missing_pdfs": [
            f for f in [
                "finance_act_2023.pdf",
                "finance_act_2024_no2.pdf",
                "income_tax_act_2025.pdf",
            ] if f not in [p.name for p in pdfs]
        ],
        "download_sources": {
            "income_tax_act_consolidated": "https://incometaxindia.gov.in/pages/acts/income-tax-act.aspx",
            "finance_acts": "https://indiacode.nic.in/handle/123456789/1362",
            "note": "Government documents — public domain in India. Free to download.",
        },
        "instructions": (
            "Download PDFs and place in backend/tax_docs/ directory. "
            "Gemini will read these for all rule extractions. "
            "Without PDFs, the module computes numbers from the Python rules engine "
            "but cannot provide verbatim Finance Act references."
        ),
    }


@app.get("/")
async def root():
    return {
        "service":     "Fintelligence Tax API",
        "version":     "1.0.0",
        "module":      "Module 4 — Tax Intelligence",
        "philosophy":  "Source of truth: Finance Acts. Numbers first. Awareness always.",
        "docs":        "/docs",
    }
