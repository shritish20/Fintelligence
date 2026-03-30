"""
Tax Rules Engine — Fintelligence Module 4
==========================================
Pure Python. No LLM. No external APIs.
Every rule has its Finance Act reference in the docstring.
When rules change, update the function. Everything downstream updates.

IMPORTANT: These are the computation rules only.
The human-readable explanation of each rule comes from Gemini
reading the actual Finance Act PDF — not from this file.
"""

from datetime import date, datetime
from dataclasses import dataclass
from typing import Optional
from enum import Enum


# ── Tax year context ──────────────────────────────────────────────────────────
CURRENT_FY     = "2025-26"
CURRENT_AY     = "2026-27"
FINANCE_ACT_EFFECTIVE = {
    "ltcg_rate_change":  date(2024, 7, 23),  # Budget 2024 No.2 — 12.5% from this date
    "stcg_rate_change":  date(2024, 7, 23),  # 20% from this date
    "debt_mf_50aa":      date(2023, 4, 1),   # Finance Act 2023 — Section 50AA
    "sgb_secondary_market_change": date(2024, 7, 23),  # Budget 2024 No.2
    "new_regime_default": date(2024, 4, 1),  # FY 2024-25 onwards
}

# ── New Tax Regime Slabs FY 2025-26 ──────────────────────────────────────────
# Finance Act 2025, Section 115BAC
# Effective: 1 April 2025
NEW_REGIME_SLABS_FY2526 = [
    (0,         400_000,  0.00),
    (400_001,   800_000,  0.05),
    (800_001,  1_200_000, 0.10),
    (1_200_001, 1_600_000, 0.15),
    (1_600_001, 2_000_000, 0.20),
    (2_000_001, 2_400_000, 0.25),
    (2_400_001, float("inf"), 0.30),
]
NEW_REGIME_REBATE_87A = 60_000   # Section 87A — rebate if total income ≤ 12L
NEW_REGIME_REBATE_THRESHOLD = 1_200_000

# ── Old Tax Regime Slabs FY 2025-26 ──────────────────────────────────────────
# Income Tax Act, Part III of First Schedule
OLD_REGIME_SLABS_FY2526 = [
    (0,         250_000,  0.00),
    (250_001,   500_000,  0.05),
    (500_001,  1_000_000, 0.20),
    (1_000_001, float("inf"), 0.30),
]
OLD_REGIME_REBATE_87A = 12_500   # Section 87A — rebate if total income ≤ 5L
OLD_REGIME_REBATE_THRESHOLD = 500_000

# Surcharge and cess
HEALTH_EDUCATION_CESS = 0.04     # Section 2(11C) — 4% on tax + surcharge

# ── LTCG / STCG constants ─────────────────────────────────────────────────────
LTCG_EXEMPTION_ANNUAL = 125_000  # Section 112A — ₹1.25L per FY (Budget 2024)
LTCG_RATE             = 0.125    # Section 112A — 12.5% w.e.f 23 Jul 2024
STCG_RATE_EQUITY      = 0.20     # Section 111A — 20% w.e.f 23 Jul 2024

# Pre-Budget 2024 rates (for transactions before 23 Jul 2024)
LTCG_RATE_PRE_BUDGET2024 = 0.10  # Section 112A old
LTCG_EXEMPTION_PRE_BUDGET2024 = 100_000
STCG_RATE_PRE_BUDGET2024 = 0.15  # Section 111A old

# ── Holding period thresholds ─────────────────────────────────────────────────
EQUITY_LTCG_MONTHS    = 12       # Section 2(42A) — listed equity
DEBT_MF_LTCG_MONTHS   = 24       # Pre-FA2023 debt MF — 24 months for LTCG


class InstrumentType(Enum):
    EQUITY_LISTED         = "equity_listed"
    EQUITY_MF             = "equity_mf"
    DEBT_MF_PRE_APR2023   = "debt_mf_pre_apr2023"
    DEBT_MF_POST_APR2023  = "debt_mf_post_apr2023"
    SGB_RBI_ISSUE         = "sgb_rbi_issue"
    SGB_SECONDARY         = "sgb_secondary"
    LISTED_NCD            = "listed_ncd"
    UNLISTED_NCD          = "unlisted_ncd"
    GSEC                  = "gsec"
    LISTED_BOND           = "listed_bond"
    FO_NIFTY              = "fo_nifty"
    INTRADAY_EQUITY       = "intraday_equity"


@dataclass
class TaxRule:
    treatment:     str          # LTCG / STCG / BUSINESS_INCOME / EXEMPT / SLAB
    rate:          Optional[float]  # None if slab rate
    holding_months:Optional[int]    # minimum months for this treatment
    act_section:   str
    act_year:      str
    effective_from:date
    note:          str


@dataclass
class TaxComputation:
    instrument:      str
    gain:            float
    holding_days:    int
    holding_months:  float
    treatment:       str
    taxable_gain:    float
    tax_amount:      float
    rule:            TaxRule
    flags:           list[str]
    finance_act_ref: str


# ── Core computation functions ────────────────────────────────────────────────

def holding_months(purchase_date: date, sale_date: date) -> float:
    """Compute exact months held."""
    delta = sale_date - purchase_date
    return delta.days / 30.44


def compute_slab_tax(income: float, regime: str = "new") -> dict:
    """
    Compute income tax on slab-rate income.
    
    Section 115BAC (New Regime) — Finance Act 2020 as amended 2023 and 2025
    Part III First Schedule (Old Regime) — Income Tax Act
    FY 2025-26 slabs.
    """
    slabs = NEW_REGIME_SLABS_FY2526 if regime == "new" else OLD_REGIME_SLABS_FY2526
    
    tax = 0.0
    for lower, upper, rate in slabs:
        if income <= lower:
            break
        taxable_in_slab = min(income, upper if upper != float("inf") else income) - lower
        tax += taxable_in_slab * rate

    # Section 87A rebate
    if regime == "new":
        if income <= NEW_REGIME_REBATE_THRESHOLD:
            tax = max(0, tax - NEW_REGIME_REBATE_87A)
    else:
        if income <= OLD_REGIME_REBATE_THRESHOLD:
            tax = max(0, tax - OLD_REGIME_REBATE_87A)

    # Health and Education Cess — Section 2(11C)
    cess = tax * HEALTH_EDUCATION_CESS
    total = tax + cess

    return {
        "tax_before_cess":     round(tax, 2),
        "cess":                round(cess, 2),
        "total_tax":           round(total, 2),
        "effective_rate":      round((total / income * 100) if income > 0 else 0, 2),
        "regime":              regime,
        "act_ref":             "Section 115BAC" if regime == "new" else "Part III First Schedule",
        "act_year":            "Finance Act 2025 (FY 2025-26 slabs)",
    }


def classify_instrument(
    instrument_type: InstrumentType,
    purchase_date: date,
    sale_date: date,
    is_rbi_issue: bool = True,  # for SGB only
) -> TaxRule:
    """
    Classify instrument and return applicable tax rule.
    Every rule traced to specific Finance Act section and year.
    """
    months = holding_months(purchase_date, sale_date)

    if instrument_type == InstrumentType.EQUITY_LISTED:
        """
        Section 111A (STCG) — Income Tax Act
        Section 112A (LTCG) — Income Tax Act, amended by Finance Act 2024 No.2
        w.e.f 23 July 2024: STCG 20%, LTCG 12.5% above ₹1.25L
        """
        if months >= 12:
            return TaxRule(
                treatment="LTCG",
                rate=LTCG_RATE,
                holding_months=12,
                act_section="Section 112A",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note=f"LTCG at 12.5% above ₹{LTCG_EXEMPTION_ANNUAL:,} annual exemption. "
                     f"Rate changed from 10% to 12.5% w.e.f 23 July 2024."
            )
        else:
            return TaxRule(
                treatment="STCG",
                rate=STCG_RATE_EQUITY,
                holding_months=None,
                act_section="Section 111A",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="STCG at 20% flat. Rate changed from 15% to 20% w.e.f 23 July 2024."
            )

    elif instrument_type == InstrumentType.EQUITY_MF:
        """
        Same as listed equity — equity MF = 65%+ in domestic equity.
        Section 112A (LTCG), Section 111A (STCG)
        Finance Act 2024 No.2
        """
        if months >= 12:
            return TaxRule(
                treatment="LTCG", rate=LTCG_RATE, holding_months=12,
                act_section="Section 112A",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="Equity-oriented MF (65%+ domestic equity). LTCG at 12.5% above ₹1.25L."
            )
        else:
            return TaxRule(
                treatment="STCG", rate=STCG_RATE_EQUITY, holding_months=None,
                act_section="Section 111A",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="Equity-oriented MF held less than 12 months. STCG at 20%."
            )

    elif instrument_type == InstrumentType.DEBT_MF_POST_APR2023:
        """
        Section 50AA — Finance Act 2023 (No. 8 of 2023)
        Effective: 1 April 2024 (AY 2024-25 onwards)
        Units acquired ON OR AFTER 1 April 2023:
        ALL gains treated as STCG regardless of holding period.
        Taxed at slab rate. No LTCG benefit. No indexation.
        """
        return TaxRule(
            treatment="SLAB",
            rate=None,
            holding_months=None,
            act_section="Section 50AA",
            act_year="Finance Act 2023 (No. 8 of 2023)",
            effective_from=date(2023, 4, 1),
            note="Debt MF purchased on/after 1 April 2023. All gains are STCG "
                 "regardless of holding period. Taxed at individual slab rate. "
                 "No LTCG treatment. No indexation. This applies to any fund "
                 "where equity allocation is less than 65%."
        )

    elif instrument_type == InstrumentType.DEBT_MF_PRE_APR2023:
        """
        Units acquired BEFORE 1 April 2023 — grandfathered under old rules.
        LTCG at 12.5% if held 24+ months (Budget 2024 removed indexation).
        STCG at slab rate if held less than 24 months.
        Finance Act 2024 No.2 removed indexation benefit w.e.f 23 July 2024.
        """
        if months >= 24:
            return TaxRule(
                treatment="LTCG", rate=0.125, holding_months=24,
                act_section="Section 112 read with Section 50AA proviso",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="Debt MF purchased before 1 April 2023. Held 24+ months: "
                     "LTCG at 12.5% without indexation (indexation removed w.e.f "
                     "23 July 2024 by Finance Act 2024 No.2). This is a transitional "
                     "benefit — new purchases after 1 April 2023 do not get this."
            )
        else:
            return TaxRule(
                treatment="SLAB", rate=None, holding_months=None,
                act_section="Section 50AA proviso, Finance Act 2023",
                act_year="Finance Act 2023 (No. 8 of 2023)",
                effective_from=date(2023, 4, 1),
                note="Debt MF purchased before 1 April 2023 but held less than "
                     "24 months. Treated as STCG — taxed at slab rate. "
                     "Wait for 24-month mark to qualify for 12.5% LTCG treatment."
            )

    elif instrument_type == InstrumentType.SGB_RBI_ISSUE:
        """
        Sovereign Gold Bond — directly subscribed from RBI issuance.
        On maturity (8 years): EXEMPT — Section 47(viic)
        Premature redemption after 5 years via RBI window: EXEMPT
        Secondary market sale before maturity:
          LTCG at 12.5% if held 12+ months (Budget 2024)
        Budget 2024 (Finance Act 2024 No.2): exemption retained for 
        original subscribers holding to maturity.
        """
        if months >= 12:
            return TaxRule(
                treatment="LTCG_OR_EXEMPT",
                rate=LTCG_RATE,
                holding_months=12,
                act_section="Section 47(viic) / Section 112",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="SGB subscribed from RBI. If held to maturity (8 years) or "
                     "redeemed via RBI premature window after 5 years: EXEMPT under "
                     "Section 47(viic). If sold on secondary market before maturity: "
                     "LTCG at 12.5% after 12 months."
            )
        else:
            return TaxRule(
                treatment="SLAB", rate=None, holding_months=None,
                act_section="Section 112",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="SGB held less than 12 months. Gain taxed at slab rate as STCG."
            )

    elif instrument_type == InstrumentType.SGB_SECONDARY:
        """
        SGB purchased from secondary market (NSE/BSE).
        Budget 2024 (Finance Act 2024 No.2), w.e.f 23 July 2024:
        Capital gains exemption under Section 47(viic) NOT available
        to investors who purchased from secondary market.
        Only investors who originally subscribed from RBI get the exemption.
        LTCG at 12.5% if held 12+ months.
        STCG at slab rate if held less than 12 months.
        """
        if months >= 12:
            return TaxRule(
                treatment="LTCG", rate=LTCG_RATE, holding_months=12,
                act_section="Section 112, Section 47(viic) — not applicable",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="SGB purchased from secondary market. The capital gains "
                     "exemption under Section 47(viic) is NOT available — Budget 2024 "
                     "restricted it to original RBI subscribers. Gain taxed as LTCG "
                     "at 12.5% after 12 months. For future gold allocation, subscribe "
                     "directly from RBI to preserve the exemption."
            )
        else:
            return TaxRule(
                treatment="SLAB", rate=None, holding_months=None,
                act_section="Section 112 — secondary market purchase",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="SGB purchased from secondary market, held less than 12 months. "
                     "Gain taxed at slab rate. Exemption under 47(viic) not available."
            )

    elif instrument_type in (InstrumentType.GSEC, InstrumentType.LISTED_BOND):
        """
        Government Securities / Listed Bonds.
        Section 112 — LTCG at 12.5% if held 12+ months (Budget 2024).
        Slab rate if held less than 12 months.
        Interest income: "Income from Other Sources" — slab rate always.
        """
        if months >= 12:
            return TaxRule(
                treatment="LTCG", rate=0.125, holding_months=12,
                act_section="Section 112",
                act_year="Finance Act 2024 (No. 2 of 2024)",
                effective_from=date(2024, 7, 23),
                note="Listed government security / bond. Capital gain on sale after "
                     "12 months taxed as LTCG at 12.5% (without indexation). "
                     "Interest income taxed separately at slab rate under "
                     "'Income from Other Sources' — Section 56."
            )
        else:
            return TaxRule(
                treatment="SLAB", rate=None, holding_months=None,
                act_section="Section 111 / Section 56",
                act_year="Income Tax Act",
                effective_from=date(2001, 4, 1),
                note="Listed security held less than 12 months. Gain at slab rate. "
                     "Interest income also at slab rate."
            )

    elif instrument_type == InstrumentType.UNLISTED_NCD:
        """
        Unlisted NCDs / Debentures.
        Section 50AA (Finance Act 2023) — ALL gains treated as STCG
        regardless of holding period. Taxed at slab rate.
        Same treatment as post-April 2023 debt MF.
        """
        return TaxRule(
            treatment="SLAB", rate=None, holding_months=None,
            act_section="Section 50AA",
            act_year="Finance Act 2023 (No. 8 of 2023)",
            effective_from=date(2023, 4, 1),
            note="Unlisted NCD/debenture. Section 50AA (Finance Act 2023) treats "
                 "all gains as STCG regardless of holding period. "
                 "Taxed at individual slab rate."
        )

    elif instrument_type == InstrumentType.FO_NIFTY:
        """
        F&O trading — Non-Speculative Business Income.
        Section 43(5) of Income Tax Act.
        Added to total income. Taxed at slab rate.
        All trading-related expenses deductible under Section 37(1).
        Losses can be carried forward 8 years (non-speculative only).
        """
        return TaxRule(
            treatment="BUSINESS_INCOME", rate=None, holding_months=None,
            act_section="Section 43(5) / Section 28 / Section 37(1)",
            act_year="Income Tax Act (as amended)",
            effective_from=date(2001, 4, 1),
            note="F&O income — non-speculative business income under Section 43(5). "
                 "Added to total income, taxed at applicable slab rate. "
                 "All trading expenses deductible under Section 37(1). "
                 "Net loss can be set off against any non-salary income in same year "
                 "and carried forward for 8 years against non-speculative gains."
        )

    elif instrument_type == InstrumentType.INTRADAY_EQUITY:
        """
        Intraday equity — Speculative Business Income.
        Section 43(5) of Income Tax Act.
        Losses can ONLY be set off against speculative gains.
        Carry forward: 4 years (speculative only).
        """
        return TaxRule(
            treatment="SPECULATIVE_BUSINESS", rate=None, holding_months=None,
            act_section="Section 43(5) proviso",
            act_year="Income Tax Act (as amended)",
            effective_from=date(2001, 4, 1),
            note="Intraday equity — speculative business income under Section 43(5). "
                 "Losses can ONLY be set off against speculative income — NOT against "
                 "F&O or any other income. Carry forward: 4 years."
        )

    # Default
    return TaxRule(
        treatment="UNKNOWN", rate=None, holding_months=None,
        act_section="Verify with CA",
        act_year="N/A",
        effective_from=date.today(),
        note="Treatment unclear. Verify with a Chartered Accountant."
    )


def compute_capital_gain_tax(
    gain: float,
    rule: TaxRule,
    ltcg_exemption_used: float = 0.0,
    slab_rate: float = 0.30,
) -> dict:
    """
    Compute exact tax on a capital gain given the applicable rule.
    """
    if gain <= 0:
        return {"taxable_gain": 0, "tax": 0, "treatment": rule.treatment,
                "exemption_used": 0, "note": "No gain — no tax."}

    if rule.treatment == "LTCG":
        # ₹1.25L annual exemption under Section 112A
        remaining_exemption = max(0, LTCG_EXEMPTION_ANNUAL - ltcg_exemption_used)
        exemption_applied   = min(gain, remaining_exemption)
        taxable_gain        = max(0, gain - exemption_applied)
        tax                 = round(taxable_gain * LTCG_RATE * (1 + HEALTH_EDUCATION_CESS), 2)
        return {
            "taxable_gain":       taxable_gain,
            "tax":                tax,
            "treatment":          "LTCG",
            "rate":               f"{LTCG_RATE*100:.1f}%",
            "exemption_applied":  exemption_applied,
            "exemption_used_now": ltcg_exemption_used + exemption_applied,
            "act_ref":            f"{rule.act_section}, {rule.act_year}",
        }

    elif rule.treatment == "STCG":
        tax = round(gain * STCG_RATE_EQUITY * (1 + HEALTH_EDUCATION_CESS), 2)
        return {
            "taxable_gain": gain,
            "tax":          tax,
            "treatment":    "STCG",
            "rate":         "20%",
            "act_ref":      f"{rule.act_section}, {rule.act_year}",
        }

    elif rule.treatment in ("SLAB", "SPECULATIVE_BUSINESS", "BUSINESS_INCOME"):
        tax = round(gain * slab_rate * (1 + HEALTH_EDUCATION_CESS), 2)
        return {
            "taxable_gain": gain,
            "tax":          tax,
            "treatment":    "Slab rate",
            "rate":         f"{slab_rate*100:.0f}%",
            "act_ref":      f"{rule.act_section}, {rule.act_year}",
            "note":         "Slab rate varies by total income. Shown at your marginal rate."
        }

    return {"taxable_gain": gain, "tax": 0, "treatment": "UNKNOWN",
            "act_ref": "Verify with CA"}


def compute_fo_deductible_expenses(expenses: dict) -> dict:
    """
    Compute total deductible F&O business expenses.
    Section 37(1) — Income Tax Act — expenses wholly and exclusively
    for business purposes are deductible.
    Section 43(5) — F&O is non-speculative business income.
    STT: deductible under business income (unlike capital gains where it is NOT).
    """
    deductible = {
        "stt":            expenses.get("stt", 0),           # Sec 37(1) — fully deductible
        "brokerage":      expenses.get("brokerage", 0),     # Sec 37(1) — fully deductible
        "exchange_charges":expenses.get("exchange_charges",0),# Sec 37(1)
        "sebi_charges":   expenses.get("sebi_charges", 0),  # Sec 37(1)
        "dp_charges":     expenses.get("dp_charges", 0),    # Sec 37(1)
        "advisory_fees":  expenses.get("advisory_fees", 0), # Sec 37(1) — if for trading
        "subscriptions":  expenses.get("subscriptions", 0), # Sec 37(1) — trading subscriptions
        "internet_bill":  expenses.get("internet_bill", 0), # Sec 37(1) — proportionate portion
        "depreciation":   expenses.get("depreciation", 0),  # Sec 32 — on trading equipment
        "salary_to_staff":expenses.get("salary_to_staff",0),# Sec 37(1) — if any
    }
    total = sum(deductible.values())
    return {
        "breakdown":  deductible,
        "total":      total,
        "act_ref":    "Section 37(1), Income Tax Act — expenses wholly and exclusively for business",
        "note":       "STT is deductible for F&O (business income) but NOT for capital gains. "
                      "Internet and phone: only the portion proportionate to trading use.",
    }


def compute_advance_tax_schedule(
    estimated_annual_tax: float,
    tax_paid_so_far: float = 0.0,
    current_date: date = None,
) -> list[dict]:
    """
    Advance tax installment schedule.
    Section 211 — Income Tax Act.
    Penalty for non-payment: Section 234C — 1% per month (simple interest).
    """
    if current_date is None:
        current_date = date.today()

    fy_year = current_date.year if current_date.month >= 4 else current_date.year - 1
    
    installments = [
        {"due_date": date(fy_year, 6, 15),  "cumulative_pct": 0.15, "label": "15 June"},
        {"due_date": date(fy_year, 9, 15),  "cumulative_pct": 0.45, "label": "15 September"},
        {"due_date": date(fy_year, 12, 15), "cumulative_pct": 0.75, "label": "15 December"},
        {"due_date": date(fy_year + 1, 3, 15), "cumulative_pct": 1.00, "label": "15 March"},
    ]

    schedule = []
    for inst in installments:
        required_cumulative = estimated_annual_tax * inst["cumulative_pct"]
        installment_amount  = max(0, required_cumulative - tax_paid_so_far)
        is_past             = inst["due_date"] < current_date
        months_delayed      = max(0, (current_date - inst["due_date"]).days // 30) if is_past else 0
        penalty             = round(installment_amount * 0.01 * months_delayed, 0) if is_past and installment_amount > 0 else 0

        schedule.append({
            "due_date":        inst["due_date"].strftime("%d %b %Y"),
            "label":           inst["label"],
            "cumulative_pct":  f"{inst['cumulative_pct']*100:.0f}%",
            "amount_due":      round(installment_amount, 0),
            "is_past":         is_past,
            "status":          "OVERDUE" if is_past and installment_amount > 0 else
                               "PAID" if tax_paid_so_far >= required_cumulative else "UPCOMING",
            "penalty_if_late": penalty,
            "act_ref":         "Section 211 / Section 234C, Income Tax Act",
        })

    return schedule


def compute_ltcg_harvest_opportunity(
    holdings: list[dict],
    ltcg_used_this_fy: float = 0.0,
) -> list[dict]:
    """
    Identify holdings where unrealised LTCG can be harvested
    within the ₹1.25L annual exemption — at ₹0 tax.
    Section 112A — Finance Act 2024, ₹1.25L exemption per FY.
    
    Strategy: Sell before 31 March, immediately rebuy.
    Effect: Crystallise gain tax-free. Reset cost basis higher.
    Future tax saving: (harvested gain × 12.5%) = permanent saving.
    """
    remaining_exemption = max(0, LTCG_EXEMPTION_ANNUAL - ltcg_used_this_fy)
    opportunities       = []
    cumulative_harvested = 0.0

    for h in holdings:
        if h.get("holding_months", 0) < 12:
            continue  # Must be LTCG qualified
        if h.get("unrealised_gain", 0) <= 0:
            continue

        gain      = h["unrealised_gain"]
        harvestable = min(gain, remaining_exemption - cumulative_harvested)

        if harvestable <= 0:
            continue

        tax_if_harvest_now  = 0.0  # Within exemption
        tax_if_wait_to_sell = round(gain * LTCG_RATE * (1 + HEALTH_EDUCATION_CESS), 2)
        tax_saving          = round(harvestable * LTCG_RATE * (1 + HEALTH_EDUCATION_CESS), 2)

        opportunities.append({
            "instrument":         h.get("name"),
            "unrealised_gain":    gain,
            "harvestable":        harvestable,
            "tax_if_harvest_now": tax_if_harvest_now,
            "tax_saving":         tax_saving,
            "strategy":           "Sell before 31 March, immediately rebuy at current price. "
                                  "New cost basis resets higher. Future LTCG reduced by ₹"
                                  + f"{harvestable:,.0f}.",
            "act_ref":            "Section 112A, Finance Act 2024 (₹1.25L annual exemption)",
        })
        cumulative_harvested += harvestable

    return opportunities


def regime_comparison(
    total_slab_income: float,
    stcg:              float = 0.0,
    ltcg:              float = 0.0,
    ltcg_exemption_used: float = 0.0,
    old_regime_deductions: float = 0.0,  # 80C + 80D + HRA etc.
) -> dict:
    """
    Compare old vs new tax regime for the user's specific income mix.
    Finance Act 2020 Section 115BAC (new regime).
    FY 2025-26 slabs.
    """
    # Old regime
    old_taxable = max(0, total_slab_income - old_regime_deductions)
    old_tax     = compute_slab_tax(old_taxable, "old")

    # New regime — no deductions allowed
    new_tax     = compute_slab_tax(total_slab_income, "new")

    # LTCG and STCG tax — same under both regimes
    ltcg_above_exemption = max(0, ltcg - max(0, LTCG_EXEMPTION_ANNUAL - ltcg_exemption_used))
    ltcg_tax = round(ltcg_above_exemption * LTCG_RATE * (1 + HEALTH_EDUCATION_CESS), 2)
    stcg_tax = round(stcg * STCG_RATE_EQUITY * (1 + HEALTH_EDUCATION_CESS), 2)

    old_total = old_tax["total_tax"] + ltcg_tax + stcg_tax
    new_total = new_tax["total_tax"] + ltcg_tax + stcg_tax
    saving    = old_total - new_total

    return {
        "old_regime": {
            "slab_income_after_deductions": round(old_taxable, 0),
            "deductions_claimed":           round(old_regime_deductions, 0),
            "slab_tax":                     old_tax["total_tax"],
            "ltcg_tax":                     ltcg_tax,
            "stcg_tax":                     stcg_tax,
            "total_tax":                    round(old_total, 0),
        },
        "new_regime": {
            "slab_income":  round(total_slab_income, 0),
            "no_deductions":"New regime — no deductions except NPS Sec 80CCD(2)",
            "slab_tax":     new_tax["total_tax"],
            "ltcg_tax":     ltcg_tax,
            "stcg_tax":     stcg_tax,
            "total_tax":    round(new_total, 0),
        },
        "better_regime":   "new" if new_total <= old_total else "old",
        "saving":          round(abs(saving), 0),
        "saving_regime":   "new" if new_total <= old_total else "old",
        "act_ref":         "Section 115BAC (new regime), Finance Act 2020 as amended FY 2025-26",
        "note":            "New regime is default from FY 2024-25. "
                           "Must opt for old regime explicitly at time of ITR filing."
    }
