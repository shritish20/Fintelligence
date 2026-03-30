"""
Mock Portfolio — Realistic Simulated Indian Investor
======================================================
This is the persona from "Why I Built This":
- Options seller on Nifty (primary income)
- G-Secs pledged as margin
- SIPs in equity MFs (3-4 years running)
- Direct equity portfolio (10 stocks, ₹12L)
- Some debt MF purchased before April 2023 (transitional case)
- Mix of RBI-issue and secondary market SGBs

Numbers are realistic — not random, not fantasy.
A real investor looking at this should think: "that looks like my situation."
"""

from datetime import date

MOCK_PORTFOLIO = {

    # ── Persona ───────────────────────────────────────────────────────────────
    "persona": {
        "name":           "Demo Portfolio",
        "description":    "Nifty options seller with equity MFs, direct equity, G-Secs, and SGBs",
        "financial_year": "2025-26",
        "tax_regime_current": "new",
        "slab_rate_pct":  30,
    },

    # ── F&O Business Income ───────────────────────────────────────────────────
    "fo": {
        "gross_profit":     820_000,     # ₹8.2L — realistic for 2-3 lots Nifty options
        "gross_loss":        95_000,     # Some bad months
        "net_pnl":          725_000,     # ₹7.25L net
        "months_traded":    10,
        "expenses": {
            "stt":              18_400,  # 0.1% on options sell side
            "brokerage":        14_200,  # ₹20/order × ~710 orders
            "exchange_charges":  6_800,
            "sebi_charges":      1_200,
            "dp_charges":        2_400,
            "zerodha_subscription": 2_400,  # ₹200/month
            "advisory_fees":    12_000,  # Volguard subscription (hypothetical)
            "internet_bill":     8_400,  # ₹700/month × 12, trading portion
            "electricity":       3_600,  # Proportionate
            "total":            69_400,
        },
        "net_taxable_fo":   655_600,     # 7,25,000 - 69,400
        "advance_tax_paid":  0,          # Hasn't paid any — flag this
        "act_ref": "Section 43(5), Section 28, Section 37(1) — Income Tax Act",
    },

    # ── Other Income ──────────────────────────────────────────────────────────
    "other_income": {
        "gsec_interest":    14_500,      # 7.26% on ₹2L face value G-Secs
        "sgb_interest":      6_250,      # 2.5% on ₹2.5L gold value SGBs
        "savings_interest":  8_200,      # Bank savings account
        "total":            28_950,
        "act_ref": "Section 56 — Income from Other Sources",
    },

    # ── Total Slab Income ─────────────────────────────────────────────────────
    "total_slab_income":    684_550,     # FO net taxable + other income
    "old_regime_deductions": 180_000,   # 80C: ₹1.5L ELSS + 80D: ₹25K health + NPS ₹5K

    # ── Equity Holdings ───────────────────────────────────────────────────────
    "equity_holdings": [
        {
            "name":           "Asian Paints Ltd",
            "exchange":       "NSE",
            "quantity":       25,
            "purchase_date":  date(2023, 4, 15),
            "purchase_price": 2_850,
            "current_price":  2_990,
            "cost_basis":     71_250,
            "current_value":  74_750,
            "unrealised_gain": 3_500,
            "holding_months": 23,
            "qualifies_ltcg": True,
            "sector":         "Paints",
        },
        {
            "name":           "TCS Ltd",
            "exchange":       "NSE",
            "quantity":       15,
            "purchase_date":  date(2022, 8, 10),
            "purchase_price": 3_200,
            "current_price":  3_820,
            "cost_basis":     48_000,
            "current_value":  57_300,
            "unrealised_gain": 9_300,
            "holding_months": 43,
            "qualifies_ltcg": True,
            "sector":         "IT Services",
        },
        {
            "name":           "HDFC Bank Ltd",
            "exchange":       "NSE",
            "quantity":       40,
            "purchase_date":  date(2022, 3, 20),
            "purchase_price": 1_420,
            "current_price":  1_650,
            "cost_basis":     56_800,
            "current_value":  66_000,
            "unrealised_gain": 9_200,
            "holding_months": 48,
            "qualifies_ltcg": True,
            "sector":         "Private Banks",
        },
        {
            "name":           "Maruti Suzuki India",
            "exchange":       "NSE",
            "quantity":       8,
            "purchase_date":  date(2021, 11, 5),
            "purchase_price": 7_200,
            "current_price":  10_400,
            "cost_basis":     57_600,
            "current_value":  83_200,
            "unrealised_gain": 25_600,
            "holding_months": 52,
            "qualifies_ltcg": True,
            "sector":         "Auto OEM",
        },
        {
            "name":           "Sun Pharmaceutical",
            "exchange":       "NSE",
            "quantity":       30,
            "purchase_date":  date(2023, 9, 12),
            "purchase_price": 1_180,
            "current_price":  1_320,
            "cost_basis":     35_400,
            "current_value":  39_600,
            "unrealised_gain": 4_200,
            "holding_months": 18,
            "qualifies_ltcg": True,
            "sector":         "Pharma",
        },
        {
            "name":           "Zomato Ltd",
            "exchange":       "NSE",
            "quantity":       200,
            "purchase_date":  date(2024, 8, 20),
            "purchase_price": 245,
            "current_price":  210,
            "cost_basis":     49_000,
            "current_value":  42_000,
            "unrealised_gain": -7_000,   # Unrealised LOSS — harvest opportunity
            "holding_months": 7,
            "qualifies_ltcg": False,
            "sector":         "Consumer Tech",
        },
        {
            "name":           "Bajaj Finance Ltd",
            "exchange":       "NSE",
            "quantity":       12,
            "purchase_date":  date(2024, 2, 14),
            "purchase_price": 6_800,
            "current_price":  7_450,
            "cost_basis":     81_600,
            "current_value":  89_400,
            "unrealised_gain": 7_800,
            "holding_months": 13,
            "qualifies_ltcg": True,
            "sector":         "NBFC",
        },
        {
            "name":           "UltraTech Cement",
            "exchange":       "NSE",
            "quantity":       6,
            "purchase_date":  date(2022, 6, 8),
            "purchase_price": 6_500,
            "current_price":  9_200,
            "cost_basis":     39_000,
            "current_value":  55_200,
            "unrealised_gain": 16_200,
            "holding_months": 45,
            "qualifies_ltcg": True,
            "sector":         "Cement",
        },
        {
            "name":           "Infosys Ltd",
            "exchange":       "NSE",
            "quantity":       20,
            "purchase_date":  date(2024, 11, 3),
            "purchase_price": 1_840,
            "current_price":  1_920,
            "cost_basis":     36_800,
            "current_value":  38_400,
            "unrealised_gain": 1_600,
            "holding_months": 4,
            "qualifies_ltcg": False,
            "sector":         "IT Services",
        },
        {
            "name":           "Tata Motors Ltd",
            "exchange":       "NSE",
            "quantity":       60,
            "purchase_date":  date(2024, 6, 22),
            "purchase_price": 940,
            "current_price":  790,
            "cost_basis":     56_400,
            "current_value":  47_400,
            "unrealised_gain": -9_000,   # Unrealised LOSS — harvest opportunity
            "holding_months": 9,
            "qualifies_ltcg": False,
            "sector":         "Auto OEM",
        },
    ],

    # Realised equity transactions this FY
    "equity_realised": [
        {
            "name":        "Wipro Ltd",
            "sale_date":   date(2025, 7, 10),
            "gain":        8_400,
            "type":        "LTCG",
            "tax_paid":    0,
        },
        {
            "name":        "ICICI Bank",
            "sale_date":   date(2025, 9, 5),
            "gain":        6_200,
            "type":        "LTCG",
            "tax_paid":    0,
        },
    ],
    "ltcg_realised_this_fy":   14_600,   # Already booked this FY
    "stcg_realised_this_fy":    0,

    # ── Mutual Fund Holdings ──────────────────────────────────────────────────
    "mf_holdings": [
        {
            "name":           "Parag Parikh Flexi Cap Fund — Direct Growth",
            "type":           "equity_mf",
            "amc":            "PPFAS",
            "purchase_date":  date(2021, 4, 1),
            "units":          842.145,
            "avg_nav":        42.80,
            "current_nav":    82.40,
            "cost_basis":     36_044,
            "current_value":  69_393,
            "unrealised_gain": 33_349,
            "holding_months": 48,
            "qualifies_ltcg": True,
            "sip_amount":     10_000,
            "monthly_sip":    True,
            "note":           "Equity MF — 65%+ domestic equity. Section 112A applies.",
        },
        {
            "name":           "Mirae Asset Large Cap Fund — Direct Growth",
            "type":           "equity_mf",
            "amc":            "Mirae Asset",
            "purchase_date":  date(2022, 1, 15),
            "units":          1_205.62,
            "avg_nav":        74.50,
            "current_nav":    98.20,
            "cost_basis":     89_819,
            "current_value":  118_392,
            "unrealised_gain": 28_573,
            "holding_months": 38,
            "qualifies_ltcg": True,
            "sip_amount":     5_000,
            "monthly_sip":    True,
            "note":           "Equity MF — LTCG at 12.5% above ₹1.25L annual exemption.",
        },
        {
            "name":           "HDFC Short Term Debt Fund — Direct Growth",
            "type":           "debt_mf_pre_apr2023",   # KEY: purchased before 1 Apr 2023
            "amc":            "HDFC",
            "purchase_date":  date(2023, 2, 20),       # Feb 2023 — before April 2023 cutoff
            "units":          2_841.30,
            "avg_nav":        52.80,
            "current_nav":    61.20,
            "cost_basis":     150_020,
            "current_value":  173_888,
            "unrealised_gain": 23_868,
            "holding_months": 25,
            "qualifies_ltcg": True,    # 24+ months met
            "note":           "CRITICAL: Purchased BEFORE 1 April 2023. "
                              "Qualifies for LTCG at 12.5% (pre-FA2023 treatment). "
                              "New purchases after Apr 2023 lose this benefit permanently.",
        },
        {
            "name":           "SBI Liquid Fund — Direct Growth",
            "type":           "debt_mf_post_apr2023",  # After April 2023 — Section 50AA
            "amc":            "SBI",
            "purchase_date":  date(2024, 9, 10),
            "units":          482.15,
            "avg_nav":        3_920.50,
            "current_nav":    4_082.30,
            "cost_basis":     1_890_000,
            "current_value":  1_968_278,
            "unrealised_gain": 78_278,
            "holding_months": 6,
            "qualifies_ltcg": False,
            "note":           "Purchased after 1 April 2023. Section 50AA applies. "
                              "All gains taxed at slab rate regardless of holding period.",
        },
    ],

    # ── G-Secs ────────────────────────────────────────────────────────────────
    "gsec_holdings": [
        {
            "name":           "7.26% GOI 2033",
            "face_value":     200_000,
            "purchase_price": 98.50,     # per ₹100 face value
            "current_price":  99.20,
            "coupon_rate":    7.26,
            "purchase_date":  date(2023, 6, 15),
            "maturity_date":  date(2033, 8, 22),
            "annual_interest":14_520,
            "holding_months": 21,
            "is_pledged":     True,      # pledged as F&O margin
            "pledge_value":   180_000,   # 90% haircut margin value
            "unrealised_gain": 1_400,
            "note":           "G-Sec pledged as margin for F&O. "
                              "Interest taxed under 'Income from Other Sources' at slab. "
                              "Capital gain on sale: LTCG at 12.5% after 12 months.",
        },
    ],

    # ── SGBs ──────────────────────────────────────────────────────────────────
    "sgb_holdings": [
        {
            "name":           "SGB 2022-23 Series III",
            "source":         "rbi_issue",          # SUBSCRIBED from RBI — EXEMPT on maturity
            "units":          10,                   # 10 grams
            "issue_price":    5_200,                # per gram
            "current_price":  7_850,                # per gram (approx gold price)
            "cost_basis":     52_000,
            "current_value":  78_500,
            "unrealised_gain": 26_500,
            "purchase_date":  date(2022, 12, 20),
            "maturity_date":  date(2030, 12, 20),
            "annual_interest": 2_500,               # 2.5% of ₹1L value at issue
            "holding_months": 27,
            "note":           "RBI direct subscription. Exempt from capital gains on "
                              "maturity under Section 47(viic). "
                              "Annual interest of ₹2,500 taxed at slab rate.",
        },
        {
            "name":           "SGB 2023-24 Series II (secondary)",
            "source":         "secondary_market",   # Bought from NSE — NO maturity exemption
            "units":          5,
            "purchase_price": 6_240,               # per gram (bought higher than issue)
            "current_price":  7_850,
            "cost_basis":     31_200,
            "current_value":  39_250,
            "unrealised_gain": 8_050,
            "purchase_date":  date(2023, 8, 14),
            "maturity_date":  date(2031, 4, 30),
            "annual_interest": 1_250,
            "holding_months": 19,
            "note":           "CRITICAL: Bought from secondary market. "
                              "Budget 2024 removed Section 47(viic) exemption for "
                              "secondary market buyers. Gain taxed as LTCG at 12.5% "
                              "after 12 months (not exempt on maturity).",
        },
    ],

    # ── Computed summary (derived from above) ─────────────────────────────────
    "summary": {
        "total_equity_value":         515_050,
        "total_mf_value":           2_330_071,
        "total_gsec_value":           198_400,
        "total_sgb_value":            117_750,
        "total_portfolio_value":    3_161_271,

        "total_unrealised_gain_equity":  61_400,
        "total_unrealised_loss_equity":  16_000,
        "ltcg_qualified_gains_equity":   77_000,   # Only gains on LTCG-eligible holdings

        "ltcg_used_this_fy":        14_600,   # Already realised
        "ltcg_remaining_exemption": 110_400,  # 1,25,000 - 14,600
        "harvest_opportunity":       77_000,  # Can harvest within exemption: ₹77K of the ₹1.1L

        "total_fo_income":          655_600,  # Net of expenses
        "total_other_income":        28_950,
        "total_slab_income":        684_550,

        "estimated_tax_new_regime":  98_200,
        "estimated_tax_old_regime": 142_800,
        "regime_saving":             44_600,  # New regime saves ₹44,600

        "advance_tax_paid":              0,
        "advance_tax_due_15_sep":    14_730,  # 15% of estimated annual tax

        "days_to_31_mar":            11,      # As of mock date — urgency for harvest
    },

    # ── Flags (pre-computed, narrative added by Claude/Groq) ──────────────────
    "flags": [
        {
            "priority":    "URGENT",
            "type":        "ADVANCE_TAX",
            "title":       "Advance tax overdue — 15 September deadline",
            "number":      14_730,
            "description": "No advance tax paid. Estimated annual tax ₹98,200. "
                           "15% due by 15 September = ₹14,730. "
                           "Penalty: 1% per month on overdue amount.",
            "act_ref":     "Section 234C, Section 211 — Income Tax Act",
            "effective":   "Every FY — instalments due Jun/Sep/Dec/Mar",
            "action_date": "15 September 2025",
        },
        {
            "priority":    "URGENT",
            "type":        "LTCG_HARVEST",
            "title":       "₹1,10,400 LTCG exemption remaining — expires 31 March",
            "number":      110_400,
            "description": "₹14,600 of LTCG already realised this FY. "
                           "Remaining exemption: ₹1,10,400. "
                           "LTCG-eligible unrealised gains: ₹77,000 across 7 holdings. "
                           "Selling and rebuying these before 31 March = ₹0 tax. "
                           "Same gain would cost ₹9,625 if realised next FY above exemption.",
            "act_ref":     "Section 112A, Finance Act 2024 (No. 2 of 2024)",
            "effective":   "w.e.f 23 July 2024",
            "saving":      9_625,
        },
        {
            "priority":    "URGENT",
            "type":        "STCG_LOSS_HARVEST",
            "title":       "₹16,000 unrealised STCG loss — harvest before 31 March",
            "number":      16_000,
            "description": "Zomato and Tata Motors show unrealised loss of ₹16,000 "
                           "(STCG category — held less than 12 months). "
                           "Booking this loss before 31 March allows set-off against "
                           "any STCG in the same FY. Tax saving at 20%: ₹3,200.",
            "act_ref":     "Section 74 — Capital Gains losses, Income Tax Act",
            "effective":   "Same FY set-off and carry forward 8 years",
            "saving":      3_200,
        },
        {
            "priority":    "WATCH",
            "type":        "SGB_SECONDARY",
            "title":       "SGB secondary market purchase — maturity exemption lost",
            "number":      8_050,
            "description": "SGB 2023-24 Series II purchased from NSE secondary market. "
                           "Budget 2024 restricted Section 47(viic) exemption to RBI subscribers only. "
                           "Unrealised gain ₹8,050 will be taxed as LTCG at 12.5% on sale. "
                           "RBI-issue SGB (2022-23) retains full exemption on maturity.",
            "act_ref":     "Section 47(viic), Finance Act 2024 (No. 2 of 2024)",
            "effective":   "w.e.f 23 July 2024",
        },
        {
            "priority":    "WATCH",
            "type":        "DEBT_MF_PRETRANSITION",
            "title":       "HDFC Short Term Debt — pre-April 2023 treatment preserved",
            "number":      23_868,
            "description": "HDFC Short Term Debt Fund purchased 20 Feb 2023 — "
                           "before the 1 April 2023 Finance Act 2023 cutoff. "
                           "Held 25 months — qualifies for LTCG at 12.5% (not slab rate). "
                           "Gain ₹23,868: tax at 12.5% = ₹2,984. "
                           "If purchased after 1 April 2023: same gain taxed at 30% = ₹7,160.",
            "act_ref":     "Section 50AA, Finance Act 2023 (No. 8 of 2023)",
            "effective":   "1 April 2024 (AY 2024-25 onwards)",
            "saving_vs_new": 4_176,
        },
        {
            "priority":    "GREEN",
            "type":        "FO_EXPENSES",
            "title":       "₹69,400 in F&O expenses — fully deductible",
            "number":      69_400,
            "description": "STT ₹18,400 + Brokerage ₹14,200 + Exchange/SEBI ₹8,000 + "
                           "Advisory ₹12,000 + Internet ₹8,400 + Subscription ₹4,800 + "
                           "Others ₹3,600 = ₹69,400 total. "
                           "All deductible under Section 37(1) as business expenses. "
                           "Tax saving at 30% slab: ₹20,820. "
                           "Note: STT is NOT deductible for capital gains — only for business income.",
            "act_ref":     "Section 37(1), Section 28 — Income Tax Act",
            "effective":   "Ongoing — business income rules",
            "saving":      20_820,
        },
        {
            "priority":    "GREEN",
            "type":        "REGIME",
            "title":       "New tax regime saves ₹44,600 this year",
            "number":      44_600,
            "description": "Total slab income ₹6,84,550. "
                           "Old regime (with ₹1,80,000 deductions): tax ₹1,42,800. "
                           "New regime (Section 87A rebate up to ₹12L): tax ₹98,200. "
                           "New regime is better by ₹44,600 — primary income is F&O, "
                           "deductions are limited.",
            "act_ref":     "Section 115BAC, Finance Act 2020 as amended — FY 2025-26 slabs",
            "effective":   "New regime is default from FY 2024-25",
            "saving":      44_600,
        },
    ],
}
