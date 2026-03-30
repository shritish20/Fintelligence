"""
Finance Act PDF Reader — Gemini
================================
Gemini's ONLY job in this module:
Read the Finance Act PDF and extract the exact rule.
Never answer from memory. Only from the document.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types

log = logging.getLogger("fintelligence_tax.gemini")

TAX_DOCS_DIR = Path(__file__).parent / "tax_docs"

# Map of which document to use for which query type
SECTION_TO_DOC = {
    "50AA":    "finance_act_2023.pdf",
    "112A":    "finance_act_2024_no2.pdf",
    "111A":    "finance_act_2024_no2.pdf",
    "47":      "finance_act_2024_no2.pdf",
    "115BAC":  "income_tax_act_2025.pdf",
    "234C":    "income_tax_act_2025.pdf",
    "211":     "income_tax_act_2025.pdf",
    "37":      "income_tax_act_2025.pdf",
    "43":      "income_tax_act_2025.pdf",
    "112":     "income_tax_act_2025.pdf",
    "default": "income_tax_act_2025.pdf",
}


def _get_gemini_client() -> Optional[object]:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    try:
        return genai.Client(api_key=key)
    except Exception as e:
        log.error(f"Gemini init failed: {e}")
        return None


def _load_pdf(filename: str) -> Optional[bytes]:
    path = TAX_DOCS_DIR / filename
    if not path.exists():
        log.warning(f"Finance Act PDF not found: {path}")
        log.warning("Download from: https://incometaxindia.gov.in/pages/acts/income-tax-act.aspx")
        return None
    return path.read_bytes()


def extract_rule_from_finance_act(
    section: str,
    question: str,
    context: str = "",
) -> dict:
    """
    Ask Gemini to extract a specific rule from the Finance Act PDF.
    Returns structured JSON with section text and applicability.
    If PDF not available → returns fallback with note to download.
    """
    client = _get_gemini_client()
    if not client:
        return {
            "found":       False,
            "source":      "Gemini API key not configured",
            "note":        "Set GEMINI_API_KEY to enable Finance Act rule extraction",
            "rule_text":   None,
            "effective_from": None,
        }

    # Determine which document to use
    doc_file = SECTION_TO_DOC.get(section.replace("Section ", "").split("(")[0].strip(),
                                   SECTION_TO_DOC["default"])
    pdf_bytes = _load_pdf(doc_file)

    if not pdf_bytes:
        return {
            "found":       False,
            "source":      f"PDF not found: {doc_file}",
            "note":        f"Download Finance Act PDF and place at backend/tax_docs/{doc_file}. "
                           f"Source: https://incometaxindia.gov.in",
            "rule_text":   None,
            "effective_from": None,
        }

    extraction_prompt = f"""
You are reading a Finance Act / Income Tax Act PDF.

Your task: Extract the EXACT text and details of {section}.

Question being answered: {question}

{f"Context: {context}" if context else ""}

Return ONLY a JSON object with these exact keys:
{{
  "found": true/false,
  "section_number": "exact section number",
  "act_name": "exact name of the Act",
  "act_year": "year of the Act (e.g. Finance Act 2023)",
  "act_number": "act number (e.g. No. 8 of 2023)",
  "effective_from": "DD Month YYYY or AY YYYY-YY or FY YYYY-YY",
  "verbatim_text": "exact verbatim text of the section (first 300 words)",
  "plain_english": "plain English explanation in 2-3 sentences",
  "applicable_to": "what instruments/situations this applies to",
  "rate_or_treatment": "the tax rate or treatment specified",
  "exceptions": "any exceptions or provisos (empty string if none)",
  "amended_by": "if this section was amended, which Act amended it"
}}

CRITICAL RULES:
- Answer ONLY from what is written in this document
- If the section is not in this document, set "found" to false
- Do not add any information from outside this document
- Quote verbatim text exactly as written — do not paraphrase the verbatim field
- For "plain_english" — your own plain language explanation is fine
- Return ONLY the JSON object, no other text
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(parts=[
                    types.Part(inline_data=types.Blob(
                        mime_type="application/pdf",
                        data=pdf_bytes,
                    )),
                    types.Part(text=extraction_prompt),
                ])
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,  # Zero temperature — we want exact extraction
                max_output_tokens=1000,
            )
        )

        raw = response.text.strip()
        # Clean JSON fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)
        result["pdf_source"] = doc_file
        return result

    except json.JSONDecodeError as e:
        log.error(f"Gemini returned non-JSON: {e}")
        return {"found": False, "source": "Parse error", "note": str(e)}
    except Exception as e:
        log.error(f"Gemini extraction failed: {e}")
        return {"found": False, "source": "API error", "note": str(e)}


def answer_tax_query(
    user_query: str,
    portfolio_context: dict,
) -> dict:
    """
    Answer a user's tax query by:
    1. Identifying the relevant Finance Act section
    2. Reading that section from the PDF
    3. Returning structured answer
    
    This function returns ONLY the extracted rule and computed numbers.
    The narrative is written by Claude/Groq separately.
    """
    client = _get_gemini_client()
    if not client:
        return {
            "answerable": False,
            "reason": "GEMINI_API_KEY not configured",
            "note": "Gemini is required to read Finance Act PDFs for accurate answers",
        }

    # Step 1: Ask Gemini to identify the relevant section
    # We load the consolidated 2025 act as the primary reference
    pdf_bytes = _load_pdf("income_tax_act_2025.pdf")

    if not pdf_bytes:
        # Try Finance Act 2024 as fallback
        pdf_bytes = _load_pdf("finance_act_2024_no2.pdf")

    if not pdf_bytes:
        return {
            "answerable": False,
            "reason": "No Finance Act PDFs found",
            "note": "Download PDFs from incometaxindia.gov.in and place in backend/tax_docs/",
        }

    # Check if query is tax-related (simple keyword check before burning API)
    TAX_KEYWORDS = [
        "tax", "section", "ltcg", "stcg", "capital gain", "income",
        "finance act", "deduction", "exemption", "slab", "regime",
        "advance tax", "audit", "turnover", "fo", "f&o", "futures",
        "options", "mutual fund", "sgb", "bond", "gsec", "ncd",
        "80c", "80d", "hra", "87a", "234c", "50aa", "112a", "111a",
    ]
    query_lower = user_query.lower()
    is_tax_query = any(kw in query_lower for kw in TAX_KEYWORDS)

    if not is_tax_query:
        return {
            "answerable": False,
            "reason": "not_tax_query",
            "redirect": "This module only answers questions about tax rules from the Finance Acts "
                        "or how they apply to your specific holdings.",
        }

    portfolio_summary = json.dumps({
        "fo_profit_ytd":    portfolio_context.get("fo_profit_ytd", 0),
        "equity_holdings":  len(portfolio_context.get("equity_holdings", [])),
        "mf_holdings":      len(portfolio_context.get("mf_holdings", [])),
        "ltcg_used_ytd":    portfolio_context.get("ltcg_used_ytd", 0),
    }, indent=2)

    query_prompt = f"""
You are reading an Income Tax Act / Finance Act PDF.

User question: "{user_query}"

User's portfolio (for context if question is portfolio-specific):
{portfolio_summary}

Your task:
1. Find the relevant section(s) in this document
2. Extract the exact rule that answers this question
3. If the question is portfolio-specific, note how the rule applies

Return ONLY a JSON object:
{{
  "is_answerable_from_document": true/false,
  "reason_if_not": "why not answerable (e.g. not a tax question, investment advice, etc.)",
  "redirect_module": "if not tax, suggest: MF_INTEL or EQUITY_INTEL or none",
  "relevant_sections": ["Section X", "Section Y"],
  "primary_section": "Section X",
  "act_name": "Finance Act YYYY",
  "effective_from": "date",
  "rule_text": "verbatim text of relevant section",
  "plain_answer": "2-3 sentence plain English answer to the specific question",
  "applies_to_portfolio": true/false,
  "portfolio_computation": "if applies to portfolio, the specific numbers (or empty)",
  "caveat": "any important caveat or 'Verify with a CA before filing'"
}}

CRITICAL: 
- Answer ONLY from this document
- If you cannot find it, set is_answerable_from_document to false
- Never speculate about future budgets
- Never give investment advice
- If the question asks what to DO (buy/sell/invest), set is_answerable_from_document to false
  and set redirect_module appropriately
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(parts=[
                    types.Part(inline_data=types.Blob(
                        mime_type="application/pdf",
                        data=pdf_bytes,
                    )),
                    types.Part(text=query_prompt),
                ])
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=1200,
            )
        )

        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw.strip())
        return result

    except Exception as e:
        log.error(f"Query answer failed: {e}")
        return {
            "is_answerable_from_document": False,
            "reason_if_not": f"Technical error: {e}",
        }
