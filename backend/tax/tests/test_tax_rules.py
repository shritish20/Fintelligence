"""
Tests for tax_rules.py — Fintelligence Tax Engine

Run with:
    pip install pytest
    cd backend/tax
    pytest tests/ -v

Every test is named for the Finance Act section it covers so failures
point directly to the relevant law. Test values are derived from the
Finance Act 2024 and 2025 slabs — not from the implementation — to
give independent verification.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import date
from tax_rules import (
    InstrumentType,
    TaxRule,
    TaxComputation,
    holding_months,
    compute_slab_tax,
    classify_instrument,
    compute_capital_gain_tax,
    compute_fo_deductible_expenses,
    compute_advance_tax_schedule,
    compute_ltcg_harvest_opportunity,
    regime_comparison,
    LTCG_EXEMPTION_ANNUAL,
    LTCG_RATE,
    STCG_RATE_EQUITY,
    NEW_REGIME_REBATE_THRESHOLD,
    NEW_REGIME_REBATE_87A,
    HEALTH_EDUCATION_CESS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def approx(val, rel=0.01):
    """pytest.approx wrapper — 1% relative tolerance for tax rounding."""
    return pytest.approx(val, rel=rel)


# ─────────────────────────────────────────────────────────────────────────────
# holding_months
# ─────────────────────────────────────────────────────────────────────────────

class TestHoldingMonths:
    def test_exactly_12_months(self):
        """365 days / 30.44 ≈ 11.99 months — just under the 12-month threshold."""
        result = holding_months(date(2023, 1, 1), date(2024, 1, 1))
        assert result == approx(12.0, rel=0.02)

    def test_less_than_12_months(self):
        result = holding_months(date(2024, 1, 1), date(2024, 6, 30))
        assert result < 12

    def test_more_than_24_months(self):
        result = holding_months(date(2022, 1, 1), date(2024, 6, 1))
        assert result > 24

    def test_one_day(self):
        result = holding_months(date(2024, 1, 1), date(2024, 1, 2))
        assert result == approx(1 / 30.44, rel=0.01)

    def test_same_day(self):
        result = holding_months(date(2024, 6, 1), date(2024, 6, 1))
        assert result == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# compute_slab_tax — New Regime (Section 115BAC, FY 2025-26)
# ─────────────────────────────────────────────────────────────────────────────

class TestSlabTaxNewRegime:
    """Finance Act 2025, Section 115BAC — new regime slabs FY 2025-26."""

    def test_zero_income(self):
        r = compute_slab_tax(0, "new")
        assert r["total_tax"] == 0
        assert r["effective_rate"] == 0

    def test_income_below_4_lakh_zero_tax(self):
        """₹0–4L: 0% slab. New regime FY 2025-26."""
        r = compute_slab_tax(400_000, "new")
        assert r["tax_before_cess"] == 0
        assert r["total_tax"] == 0

    def test_income_below_12_lakh_rebate_87a(self):
        """
        Income ≤ ₹12L — Section 87A rebate of ₹60,000 applies.
        Net tax should be zero for income at exactly ₹12L.
        Slab tax before rebate: 5%*(8L-4L) + 10%*(12L-8L) = 20,000 + 40,000 = 60,000
        After ₹60,000 rebate: 0. After cess: 0.
        """
        r = compute_slab_tax(1_200_000, "new")
        assert r["total_tax"] == 0

    def test_income_just_above_12_lakh_full_tax(self):
        """
        Income > ₹12L — 87A rebate does NOT apply.
        At ₹12,00,001: slab tax ≈ ₹60,000 + ₹0.15 (15% slab on ₹1)
        Cess: 4% on that. This should be >0.
        """
        r = compute_slab_tax(1_200_001, "new")
        assert r["total_tax"] > 0

    def test_income_15_lakh_computation(self):
        """
        ₹15L under new regime:
        0-4L: 0
        4L-8L: 5% of 4L = 20,000
        8L-12L: 10% of 4L = 40,000
        12L-15L: 15% of 3L = 45,000
        Total: 1,05,000. No 87A (>12L). Cess: 4% of 1,05,000 = 4,200.
        Grand total: 1,09,200.
        """
        r = compute_slab_tax(1_500_000, "new")
        assert r["tax_before_cess"] == approx(105_000, rel=0.001)
        assert r["cess"] == approx(4_200, rel=0.001)
        assert r["total_tax"] == approx(109_200, rel=0.001)

    def test_income_30_lakh_new_regime(self):
        """
        ₹30L under new regime:
        0-4L: 0
        4L-8L: 5% of 4L = 20,000
        8L-12L: 10% of 4L = 40,000
        12L-16L: 15% of 4L = 60,000
        16L-20L: 20% of 4L = 80,000
        20L-24L: 25% of 4L = 1,00,000
        24L-30L: 30% of 6L = 1,80,000
        Total slab tax: 4,80,000. Cess: 19,200. Grand total: 4,99,200.
        """
        r = compute_slab_tax(3_000_000, "new")
        assert r["tax_before_cess"] == approx(480_000, rel=0.001)
        assert r["total_tax"] == approx(499_200, rel=0.001)

    def test_regime_key_returned(self):
        r = compute_slab_tax(1_000_000, "new")
        assert r["regime"] == "new"
        assert "115BAC" in r["act_ref"]


# ─────────────────────────────────────────────────────────────────────────────
# compute_slab_tax — Old Regime (Part III First Schedule)
# ─────────────────────────────────────────────────────────────────────────────

class TestSlabTaxOldRegime:
    def test_income_below_2_5_lakh_zero(self):
        r = compute_slab_tax(250_000, "old")
        assert r["total_tax"] == 0

    def test_income_5_lakh_with_rebate(self):
        """
        Old regime at ₹5L: 5% of (5L-2.5L) = 12,500.
        87A rebate: 12,500 (income ≤ 5L). Tax after rebate = 0. Cess = 0.
        """
        r = compute_slab_tax(500_000, "old")
        assert r["total_tax"] == 0

    def test_income_10_lakh_old_regime(self):
        """
        ₹10L old regime:
        0-2.5L: 0
        2.5L-5L: 5% of 2.5L = 12,500
        5L-10L: 20% of 5L = 1,00,000
        Total: 1,12,500. No 87A (>5L). Cess: 4% = 4,500. Grand: 1,17,000.
        """
        r = compute_slab_tax(1_000_000, "old")
        assert r["tax_before_cess"] == approx(112_500, rel=0.001)
        assert r["total_tax"] == approx(117_000, rel=0.001)

    def test_regime_key_returned(self):
        r = compute_slab_tax(1_000_000, "old")
        assert r["regime"] == "old"


# ─────────────────────────────────────────────────────────────────────────────
# classify_instrument — equity listed (Section 111A / 112A)
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyInstrumentEquity:
    """Finance Act 2024 No.2 — STCG 20% / LTCG 12.5% w.e.f 23 Jul 2024."""

    def test_equity_stcg_short_holding(self):
        """Held 6 months → STCG at 20%."""
        rule = classify_instrument(
            InstrumentType.EQUITY_LISTED,
            date(2024, 1, 1),
            date(2024, 7, 1),
        )
        assert rule.treatment == "STCG"
        assert rule.rate == approx(0.20)
        assert "111A" in rule.act_section

    def test_equity_ltcg_long_holding(self):
        """Held 13 months → LTCG at 12.5%."""
        rule = classify_instrument(
            InstrumentType.EQUITY_LISTED,
            date(2023, 1, 1),
            date(2024, 2, 1),
        )
        assert rule.treatment == "LTCG"
        assert rule.rate == approx(0.125)
        assert "112A" in rule.act_section

    def test_equity_mf_same_as_equity(self):
        """Equity MF held 15 months → same LTCG 12.5% as listed equity."""
        rule = classify_instrument(
            InstrumentType.EQUITY_MF,
            date(2023, 1, 1),
            date(2024, 4, 1),
        )
        assert rule.treatment == "LTCG"
        assert rule.rate == approx(0.125)


# ─────────────────────────────────────────────────────────────────────────────
# classify_instrument — debt MF (Section 50AA, Finance Act 2023)
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyInstrumentDebtMF:
    def test_debt_mf_post_apr2023_always_slab(self):
        """
        Units bought after 1 Apr 2023 → Section 50AA → SLAB regardless of holding.
        Even if held 3 years, no LTCG benefit.
        """
        rule = classify_instrument(
            InstrumentType.DEBT_MF_POST_APR2023,
            date(2023, 6, 1),
            date(2026, 6, 1),
        )
        assert rule.treatment == "SLAB"
        assert rule.rate is None
        assert "50AA" in rule.act_section

    def test_debt_mf_pre_apr2023_held_24m_ltcg(self):
        """
        Units bought before 1 Apr 2023, held 24+ months → LTCG at 12.5%.
        Grandfathered. Indexation removed by Finance Act 2024 No.2.
        """
        rule = classify_instrument(
            InstrumentType.DEBT_MF_PRE_APR2023,
            date(2022, 1, 1),
            date(2024, 6, 1),
        )
        assert rule.treatment == "LTCG"
        assert rule.rate == approx(0.125)

    def test_debt_mf_pre_apr2023_held_under_24m_slab(self):
        """
        Units bought before 1 Apr 2023, held < 24 months → slab rate.
        """
        rule = classify_instrument(
            InstrumentType.DEBT_MF_PRE_APR2023,
            date(2023, 1, 1),
            date(2024, 1, 15),
        )
        assert rule.treatment == "SLAB"


# ─────────────────────────────────────────────────────────────────────────────
# compute_capital_gain_tax — integration through classify + tax
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeCapitalGainTax:
    """
    compute_capital_gain_tax(gain, rule, ltcg_exemption_used, slab_rate) -> dict
    The caller first calls classify_instrument() to get the TaxRule,
    then passes it here along with the gain.
    """

    def test_stcg_equity_tax_amount(self):
        """
        Gain of ₹1,00,000 on equity held 6 months → STCG at 20%.
        Tax = 1,00,000 × 20% × 1.04 = 20,800.
        """
        rule = classify_instrument(
            InstrumentType.EQUITY_LISTED,
            date(2024, 1, 1),
            date(2024, 7, 1),
        )
        result = compute_capital_gain_tax(gain=100_000, rule=rule)
        assert result["treatment"] == "STCG"
        assert result["tax"] == approx(20_800, rel=0.01)

    def test_ltcg_equity_with_exemption(self):
        """
        LTCG of ₹2,00,000. Exemption ₹1,25,000. Taxable ₹75,000.
        Tax = 75,000 × 12.5% × 1.04 = 9,750.
        """
        rule = classify_instrument(
            InstrumentType.EQUITY_LISTED,
            date(2023, 1, 1),
            date(2024, 2, 1),
        )
        result = compute_capital_gain_tax(gain=200_000, rule=rule, ltcg_exemption_used=0)
        assert result["treatment"] == "LTCG"
        taxable = 200_000 - LTCG_EXEMPTION_ANNUAL
        expected_tax = taxable * LTCG_RATE * (1 + HEALTH_EDUCATION_CESS)
        assert result["tax"] == approx(expected_tax, rel=0.02)

    def test_ltcg_equity_below_exemption_zero_tax(self):
        """
        LTCG of ₹1,00,000 < ₹1,25,000 exemption → zero tax.
        """
        rule = classify_instrument(
            InstrumentType.EQUITY_LISTED,
            date(2023, 1, 1),
            date(2024, 2, 1),
        )
        result = compute_capital_gain_tax(gain=100_000, rule=rule, ltcg_exemption_used=0)
        assert result["tax"] == 0

    def test_ltcg_exemption_partially_used(self):
        """
        ₹75,000 exemption already used. Gain ₹1,00,000.
        Remaining exemption = 1,25,000 - 75,000 = 50,000.
        Taxable = 1,00,000 - 50,000 = 50,000.
        Tax = 50,000 × 12.5% × 1.04 = 6,500.
        """
        rule = classify_instrument(
            InstrumentType.EQUITY_LISTED,
            date(2023, 1, 1),
            date(2024, 2, 1),
        )
        result = compute_capital_gain_tax(gain=100_000, rule=rule, ltcg_exemption_used=75_000)
        assert result["taxable_gain"] == approx(50_000, rel=0.001)
        assert result["tax"] == approx(50_000 * LTCG_RATE * (1 + HEALTH_EDUCATION_CESS), rel=0.01)

    def test_debt_mf_post_2023_slab_rate_applied(self):
        """
        Debt MF post Apr 2023 → SLAB. At 30% rate: ₹50,000 × 30% × 1.04 = 15,600.
        """
        rule = classify_instrument(
            InstrumentType.DEBT_MF_POST_APR2023,
            date(2023, 6, 1),
            date(2024, 6, 1),
        )
        result = compute_capital_gain_tax(gain=50_000, rule=rule, slab_rate=0.30)
        assert result["treatment"] == "Slab rate"
        expected = 50_000 * 0.30 * (1 + HEALTH_EDUCATION_CESS)
        assert result["tax"] == approx(expected, rel=0.02)

    def test_negative_gain_no_tax(self):
        """Loss (negative gain) → no tax liability."""
        rule = classify_instrument(
            InstrumentType.EQUITY_LISTED,
            date(2024, 1, 1),
            date(2024, 7, 1),
        )
        result = compute_capital_gain_tax(gain=-50_000, rule=rule)
        assert result["tax"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# compute_fo_deductible_expenses
# ─────────────────────────────────────────────────────────────────────────────

class TestFODeductibleExpenses:
    """
    compute_fo_deductible_expenses(expenses) -> dict with "total" and "breakdown".
    Section 37(1) — expenses wholly and exclusively for F&O business.
    """

    def test_standard_expenses_deductible(self):
        result = compute_fo_deductible_expenses({
            "brokerage": 10_000,
            "stt": 5_000,
            "exchange_charges": 2_000,
        })
        assert result["total"] == approx(17_000, rel=0.001)

    def test_empty_expenses_zero(self):
        result = compute_fo_deductible_expenses({})
        assert result["total"] == 0

    def test_returns_breakdown_and_total(self):
        result = compute_fo_deductible_expenses({"brokerage": 1_000, "stt": 500})
        assert "total" in result
        assert "breakdown" in result
        assert isinstance(result["breakdown"], dict)

    def test_all_expense_types_summed(self):
        expenses = {
            "stt": 1_000, "brokerage": 2_000, "exchange_charges": 300,
            "sebi_charges": 50, "advisory_fees": 5_000,
        }
        result = compute_fo_deductible_expenses(expenses)
        assert result["total"] == approx(8_350, rel=0.001)


class TestAdvanceTaxSchedule:
    """
    compute_advance_tax_schedule(estimated_annual_tax, tax_paid_so_far, current_date)
    Section 211 — four instalments: 15%, 45%, 75%, 100% cumulative.
    """

    def test_four_instalments_returned(self):
        result = compute_advance_tax_schedule(estimated_annual_tax=100_000)
        assert len(result) == 4

    def test_amount_due_sums_to_full_tax(self):
        """
        Amount due in each instalment is the cumulative liability at that point.
        The final (4th) instalment covers 100% of the total — when nothing has
        been paid yet, amount_due for instalment 4 = full tax.
        """
        result = compute_advance_tax_schedule(estimated_annual_tax=100_000)
        # Last instalment should be 100% of total tax (cumulative)
        assert result[3]["amount_due"] == approx(100_000, rel=0.001)

    def test_first_instalment_is_15_percent(self):
        result = compute_advance_tax_schedule(estimated_annual_tax=100_000)
        assert result[0]["amount_due"] == approx(15_000, rel=0.001)

    def test_zero_tax_all_instalments_zero(self):
        result = compute_advance_tax_schedule(estimated_annual_tax=0)
        assert all(r["amount_due"] == 0 for r in result)

    def test_instalment_has_required_keys(self):
        result = compute_advance_tax_schedule(estimated_annual_tax=50_000)
        first = result[0]
        assert "due_date" in first
        assert "amount_due" in first
        assert "status" in first


class TestLTCGHarvest:
    """
    compute_ltcg_harvest_opportunity(holdings, ltcg_used_this_fy) -> list[dict]
    Holdings is a list of dicts with keys: name, unrealised_gain, holding_months.
    Section 112A — harvest within ₹1.25L annual exemption.
    """

    def _make_holding(self, name, gain, months=15):
        return {"name": name, "unrealised_gain": gain, "holding_months": months}

    def test_harvest_below_exemption_full_amount(self):
        """₹80,000 unrealised LTCG, no prior usage → full amount harvestable at zero tax."""
        holdings = [self._make_holding("RELIANCE", 80_000)]
        result = compute_ltcg_harvest_opportunity(holdings, ltcg_used_this_fy=0)
        assert len(result) == 1
        assert result[0]["harvestable"] == approx(80_000, rel=0.001)
        assert result[0]["tax_if_harvest_now"] == 0

    def test_harvest_limited_by_remaining_exemption(self):
        """₹75,000 already used. Gain ₹2,00,000. Only ₹50,000 is harvestable at zero tax."""
        holdings = [self._make_holding("INFY", 200_000)]
        result = compute_ltcg_harvest_opportunity(holdings, ltcg_used_this_fy=75_000)
        assert len(result) == 1
        assert result[0]["harvestable"] == approx(50_000, rel=0.001)

    def test_no_harvest_when_exemption_exhausted(self):
        """₹1,25,000 already used → no holdings qualify for zero-tax harvest."""
        holdings = [self._make_holding("TCS", 1_00_000)]
        result = compute_ltcg_harvest_opportunity(holdings, ltcg_used_this_fy=1_25_000)
        assert len(result) == 0

    def test_short_term_holding_excluded(self):
        """Holdings held < 12 months are not LTCG — not eligible for harvest."""
        holdings = [self._make_holding("HDFC", 50_000, months=6)]
        result = compute_ltcg_harvest_opportunity(holdings, ltcg_used_this_fy=0)
        assert len(result) == 0

    def test_negative_gain_excluded(self):
        """Loss positions are not harvest opportunities."""
        holdings = [self._make_holding("WIPRO", -30_000)]
        result = compute_ltcg_harvest_opportunity(holdings, ltcg_used_this_fy=0)
        assert len(result) == 0


class TestRegimeComparison:
    """
    regime_comparison(total_slab_income, stcg, ltcg, ltcg_exemption_used, old_regime_deductions)
    Returns dict with "old_regime", "new_regime", "recommended", "saving".
    """

    def test_returns_both_regimes(self):
        result = regime_comparison(total_slab_income=1_500_000, old_regime_deductions=150_000)
        assert "old_regime" in result
        assert "new_regime" in result

    def test_recommends_a_regime(self):
        result = regime_comparison(total_slab_income=1_500_000, old_regime_deductions=150_000)
        # Key is 'better_regime' (not 'recommended')
        assert "better_regime" in result
        assert result["better_regime"] in ("new", "old")

    def test_high_deductions_reduce_old_regime_tax(self):
        """Old regime tax with ₹5.5L deductions must be lower than with ₹0 deductions."""
        r_high_ded = regime_comparison(total_slab_income=1_500_000, old_regime_deductions=550_000)
        r_low_ded  = regime_comparison(total_slab_income=1_500_000, old_regime_deductions=0)
        assert r_high_ded["old_regime"]["total_tax"] < r_low_ded["old_regime"]["total_tax"]

    def test_zero_income_zero_tax(self):
        result = regime_comparison(total_slab_income=0, old_regime_deductions=0)
        assert result["old_regime"]["total_tax"] == 0
        assert result["new_regime"]["total_tax"] == 0

    def test_saving_matches_difference(self):
        """saving = old_total - new_total (positive = new regime is cheaper)."""
        result = regime_comparison(total_slab_income=1_000_000, old_regime_deductions=200_000)
        old_tax = result["old_regime"]["total_tax"]
        new_tax = result["new_regime"]["total_tax"]
        saving  = result["saving"]
        assert saving == approx(old_tax - new_tax, rel=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases and invariants
# ─────────────────────────────────────────────────────────────────────────────

class TestInvariants:
    def test_cess_is_always_4_percent(self):
        """HEALTH_EDUCATION_CESS must be 0.04 (Section 2(11C))."""
        assert HEALTH_EDUCATION_CESS == 0.04

    def test_ltcg_exemption_is_1_25_lakh(self):
        """Section 112A exemption raised to ₹1.25L by Budget 2024."""
        assert LTCG_EXEMPTION_ANNUAL == 125_000

    def test_ltcg_rate_is_12_5_percent(self):
        """Section 112A rate is 12.5% w.e.f 23 Jul 2024."""
        assert LTCG_RATE == pytest.approx(0.125)

    def test_stcg_rate_is_20_percent(self):
        """Section 111A rate is 20% w.e.f 23 Jul 2024."""
        assert STCG_RATE_EQUITY == pytest.approx(0.20)

    def test_new_regime_rebate_threshold_is_12_lakh(self):
        """Section 87A rebate threshold is ₹12L under new regime (FA 2025)."""
        assert NEW_REGIME_REBATE_THRESHOLD == 1_200_000

    def test_new_regime_rebate_is_60_000(self):
        """Section 87A rebate under new regime is ₹60,000 (FA 2025)."""
        assert NEW_REGIME_REBATE_87A == 60_000

    def test_tax_monotone_with_income(self):
        """Higher income must never produce less total tax (no regression zones)."""
        incomes = [0, 400_000, 800_000, 1_200_000, 1_500_000, 2_000_000, 3_000_000]
        taxes_new = [compute_slab_tax(i, "new")["total_tax"] for i in incomes]
        taxes_old = [compute_slab_tax(i, "old")["total_tax"] for i in incomes]
        for i in range(1, len(taxes_new)):
            assert taxes_new[i] >= taxes_new[i - 1], \
                f"New regime tax decreased from {incomes[i-1]} to {incomes[i]}"
        for i in range(1, len(taxes_old)):
            assert taxes_old[i] >= taxes_old[i - 1], \
                f"Old regime tax decreased from {incomes[i-1]} to {incomes[i]}"

    def test_effective_rate_below_30_for_all_tested_incomes(self):
        """
        No income tested should have effective rate above 30%
        (max marginal rate). Surcharge not included at these levels.
        """
        for income in [500_000, 1_000_000, 2_000_000, 5_000_000]:
            r = compute_slab_tax(income, "new")
            assert r["effective_rate"] <= 30, \
                f"Effective rate {r['effective_rate']}% exceeds 30% at ₹{income:,}"
