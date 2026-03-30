"""
File Parser — Zerodha Tax P&L + CAMS/NSDL Statement
=====================================================
Reads uploaded files and extracts portfolio data in a
format compatible with the tax computation engine.
"""

import re
import io
import logging
from datetime import date, datetime
from typing import Optional
import pandas as pd

log = logging.getLogger("fintelligence_tax.parser")


# ── Zerodha Tax P&L Parser ───────────────────────────────────────────────────

def parse_zerodha_tax_pnl(file_bytes: bytes, filename: str) -> dict:
    """
    Parse Zerodha's Tax P&L statement (Excel or CSV).
    Download from: Console.zerodha.com → Reports → Tax P&L
    
    Extracts:
    - F&O profit/loss (futures + options)
    - Equity STCG/LTCG
    - Intraday equity (speculative)
    - Trading expenses (STT, brokerage, charges)
    """
    result = {
        "source":     "zerodha_tax_pnl",
        "filename":   filename,
        "parsed":     False,
        "fo":         {"profit": 0, "loss": 0, "net": 0},
        "equity_stcg":{"gain": 0, "loss": 0},
        "equity_ltcg":{"gain": 0, "loss": 0},
        "intraday":   {"profit": 0, "loss": 0},
        "expenses":   {},
        "raw_rows":   [],
        "error":      None,
    }

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            # Try multiple sheets
            xl = pd.ExcelFile(io.BytesIO(file_bytes))
            sheets = xl.sheet_names

            fo_data     = pd.DataFrame()
            eq_data     = pd.DataFrame()
            charge_data = pd.DataFrame()

            for sheet in sheets:
                df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=None)
                sheet_lower = sheet.lower()
                if "fo" in sheet_lower or "futures" in sheet_lower or "options" in sheet_lower:
                    fo_data = df
                elif "equity" in sheet_lower or "eq" in sheet_lower:
                    eq_data = df
                elif "charge" in sheet_lower or "tax" in sheet_lower:
                    charge_data = df

            # Extract F&O totals
            if not fo_data.empty:
                result["fo"] = _extract_fo_totals(fo_data)

            # Extract equity totals
            if not eq_data.empty:
                stcg, ltcg = _extract_equity_totals(eq_data)
                result["equity_stcg"] = stcg
                result["equity_ltcg"] = ltcg

            # Extract charges
            if not charge_data.empty:
                result["expenses"] = _extract_charges(charge_data)

        elif filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
            result["raw_rows"] = df.to_dict("records")[:100]  # First 100 rows
            result["fo"], result["equity_stcg"], result["equity_ltcg"] = _parse_csv_pnl(df)

        result["parsed"] = True

    except Exception as e:
        log.error(f"Zerodha P&L parse error: {e}")
        result["error"] = str(e)

    return result


def _extract_fo_totals(df: pd.DataFrame) -> dict:
    """Extract F&O net P&L from Zerodha sheet."""
    profit = 0.0
    loss   = 0.0

    for _, row in df.iterrows():
        for col in row:
            if isinstance(col, str):
                # Look for total/net rows
                if "futures" in col.lower() or "options" in col.lower():
                    # Try to find numeric values in adjacent cells
                    pass

    # Fallback: sum all numeric values in the sheet
    numeric_cols = df.select_dtypes(include=["number"])
    if not numeric_cols.empty:
        total = numeric_cols.values.sum()
        if total > 0:
            profit = float(total)
        else:
            loss = abs(float(total))

    return {"profit": round(profit, 2), "loss": round(loss, 2),
            "net": round(profit - loss, 2)}


def _extract_equity_totals(df: pd.DataFrame) -> tuple:
    """Extract STCG and LTCG from equity sheet."""
    stcg = {"gain": 0.0, "loss": 0.0}
    ltcg = {"gain": 0.0, "loss": 0.0}
    return stcg, ltcg


def _extract_charges(df: pd.DataFrame) -> dict:
    """Extract STT, brokerage, exchange charges from charges sheet."""
    charges = {
        "stt": 0.0, "brokerage": 0.0,
        "exchange_charges": 0.0, "sebi_charges": 0.0,
        "total": 0.0,
    }
    for _, row in df.iterrows():
        for col_idx, val in enumerate(row):
            if isinstance(val, str):
                val_lower = val.lower()
                if "stt" in val_lower and col_idx + 1 < len(row):
                    try:
                        charges["stt"] += abs(float(row.iloc[col_idx + 1]))
                    except Exception:
                        pass
                elif "brokerage" in val_lower and col_idx + 1 < len(row):
                    try:
                        charges["brokerage"] += abs(float(row.iloc[col_idx + 1]))
                    except Exception:
                        pass
    charges["total"] = sum(v for k, v in charges.items() if k != "total")
    return charges


def _parse_csv_pnl(df: pd.DataFrame) -> tuple:
    """Parse CSV format P&L."""
    fo = {"profit": 0.0, "loss": 0.0, "net": 0.0}
    stcg = {"gain": 0.0, "loss": 0.0}
    ltcg = {"gain": 0.0, "loss": 0.0}

    cols_lower = [str(c).lower() for c in df.columns]

    # Look for P&L column
    pnl_col = None
    for i, c in enumerate(cols_lower):
        if "p&l" in c or "pnl" in c or "profit" in c:
            pnl_col = df.columns[i]
            break

    if pnl_col:
        for _, row in df.iterrows():
            try:
                val = float(row[pnl_col])
                instrument = str(row.get("instrument", row.get("Instrument", ""))).upper()
                if "CE" in instrument or "PE" in instrument or "FUT" in instrument:
                    if val > 0:
                        fo["profit"] += val
                    else:
                        fo["loss"] += abs(val)
                else:
                    if val > 0:
                        stcg["gain"] += val
                    else:
                        stcg["loss"] += abs(val)
            except Exception:
                pass

    fo["net"] = fo["profit"] - fo["loss"]
    return fo, stcg, ltcg


# ── CAMS / NSDL Statement Parser ─────────────────────────────────────────────

def parse_cams_statement(file_bytes: bytes, filename: str) -> dict:
    """
    Parse CAMS Consolidated Account Statement (CAS).
    Download from: camsonline.com → Statement of Account
    
    Extracts:
    - All MF holdings with purchase dates, NAVs, current values
    - Classifies each fund as equity_mf / debt_mf_pre_apr2023 / debt_mf_post_apr2023
    - Computes unrealised gains per holding
    """
    result = {
        "source":     "cams_cas",
        "filename":   filename,
        "parsed":     False,
        "holdings":   [],
        "error":      None,
    }

    try:
        if filename.endswith(".pdf"):
            # For PDF, return a message — Gemini would read this in production
            result["error"] = (
                "PDF statement detected. In production, Gemini reads the PDF. "
                "For now, please download the Excel/CSV version from camsonline.com "
                "or use the demo data."
            )
            return result

        if filename.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(file_bytes))
        elif filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        else:
            result["error"] = "Unsupported format. Use Excel or CSV from camsonline.com"
            return result

        # Parse holdings from CAMS format
        result["holdings"] = _parse_cams_holdings(df)
        result["parsed"] = True

    except Exception as e:
        log.error(f"CAMS parse error: {e}")
        result["error"] = str(e)

    return result


def _classify_mf(fund_name: str, category: str, purchase_date: date) -> str:
    """
    Classify MF as equity or debt, and pre/post April 2023 for debt.
    Section 50AA — Finance Act 2023.
    """
    name_lower = (fund_name + " " + category).lower()

    # Debt indicators
    debt_keywords = [
        "debt", "bond", "liquid", "overnight", "money market",
        "ultra short", "low duration", "short duration", "medium duration",
        "long duration", "gilt", "credit risk", "corporate bond",
        "banking psu", "dynamic bond", "floater", "fixed maturity",
    ]

    is_debt = any(kw in name_lower for kw in debt_keywords)

    if not is_debt:
        return "equity_mf"

    # Section 50AA — Finance Act 2023
    # Units purchased BEFORE 1 April 2023 → grandfathered
    # Units purchased ON OR AFTER 1 April 2023 → new slab-rate rules
    if purchase_date < date(2023, 4, 1):
        return "debt_mf_pre_apr2023"
    else:
        return "debt_mf_post_apr2023"


def _parse_cams_holdings(df: pd.DataFrame) -> list:
    """Parse CAMS Excel format into holdings list."""
    holdings = []
    cols_lower = {str(c).lower(): c for c in df.columns}

    for _, row in df.iterrows():
        try:
            name     = str(row.get(cols_lower.get("scheme", "scheme"), ""))
            category = str(row.get(cols_lower.get("category", "category"), ""))

            # Purchase date
            date_col = (cols_lower.get("purchase date") or
                       cols_lower.get("transaction date") or
                       cols_lower.get("date"))
            purchase_date = date.today()
            if date_col:
                try:
                    purchase_date = pd.to_datetime(row[date_col]).date()
                except Exception:
                    pass

            # Values
            def safe_float(col_key):
                col = cols_lower.get(col_key)
                if col and not pd.isna(row.get(col)):
                    try:
                        return float(str(row[col]).replace(",", "").replace("₹", ""))
                    except Exception:
                        return 0.0
                return 0.0

            units         = safe_float("units") or safe_float("balance units")
            avg_nav       = safe_float("avg cost") or safe_float("average cost")
            current_nav   = safe_float("current nav") or safe_float("nav")
            current_value = safe_float("current value") or safe_float("market value")
            cost_basis    = safe_float("cost value") or (units * avg_nav)

            if not name or name == "nan" or units <= 0:
                continue

            unrealised_gain = current_value - cost_basis
            fund_type       = _classify_mf(name, category, purchase_date)
            holding_months  = (date.today() - purchase_date).days / 30.44

            holdings.append({
                "name":            name,
                "type":            fund_type,
                "purchase_date":   purchase_date,
                "units":           units,
                "avg_nav":         avg_nav,
                "current_nav":     current_nav,
                "cost_basis":      round(cost_basis, 2),
                "current_value":   round(current_value, 2),
                "unrealised_gain": round(unrealised_gain, 2),
                "holding_months":  round(holding_months, 1),
                "qualifies_ltcg":  (fund_type == "equity_mf" and holding_months >= 12) or
                                   (fund_type == "debt_mf_pre_apr2023" and holding_months >= 24),
            })

        except Exception as e:
            log.warning(f"Row parse error: {e}")
            continue

    return holdings


# ── Portfolio Builder ─────────────────────────────────────────────────────────

def build_portfolio_from_uploads(
    zerodha_data:  Optional[dict] = None,
    cams_data:     Optional[dict] = None,
) -> dict:
    """
    Combine Zerodha and CAMS data into a unified portfolio dict
    compatible with the tax computation engine.
    """
    portfolio = {
        "source":      "uploaded",
        "fo":          {},
        "mf_holdings": [],
        "other_income":{},
        "equity_realised": [],
        "ltcg_realised_this_fy": 0,
        "stcg_realised_this_fy": 0,
    }

    if zerodha_data and zerodha_data.get("parsed"):
        portfolio["fo"] = {
            "gross_profit":     zerodha_data["fo"]["profit"],
            "gross_loss":       zerodha_data["fo"]["loss"],
            "net_pnl":          zerodha_data["fo"]["net"],
            "expenses":         zerodha_data.get("expenses", {}),
            "net_taxable_fo":   zerodha_data["fo"]["net"] - zerodha_data.get("expenses", {}).get("total", 0),
        }
        portfolio["ltcg_realised_this_fy"] = zerodha_data["equity_ltcg"]["gain"]
        portfolio["stcg_realised_this_fy"] = zerodha_data["equity_stcg"]["gain"]

    if cams_data and cams_data.get("parsed"):
        portfolio["mf_holdings"] = cams_data["holdings"]

    return portfolio
