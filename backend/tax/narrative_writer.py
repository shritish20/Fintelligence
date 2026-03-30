"""
Narrative Writer — Claude (primary) / Groq (fallback)
=======================================================
ONE job: Take computed numbers + Finance Act rule → Write plain English.
Never answer from memory. Only from the structured input.
Every sentence must reference a number from the input.
Always cite section and Finance Act year.
"""

import os
import json
import logging
from typing import Optional

log = logging.getLogger("fintelligence_tax.narrative")

# ── System prompt — locked tight ──────────────────────────────────────────────
SYSTEM_PROMPT = """You are a tax computation narrator for Indian investors.

You receive structured JSON input containing:
1. Computed tax numbers (calculated by Python from Finance Act rules)
2. The exact Finance Act rule extracted from the PDF by Gemini

Your ONLY job: Write 2-4 sentences in plain English explaining what the numbers mean.

MANDATORY RULES — no exceptions:
- Every sentence must reference at least one specific number from the input
- Cite the exact section number and Finance Act year from the input
- Include the effective date from the input
- Never add information not present in the structured input
- Never use: should, advise, recommend, suggest, consider, might, may want to
- Never speculate about future budget changes
- Never give investment advice
- Never say "you should sell" or "you should buy" — only state what the numbers show
- If the input shows a comparison (e.g. old vs new regime), state both numbers and the difference
- End with exactly this line (no variation):
  "Source: [section from input], [act year from input]. Verify with a CA before filing."

FORMAT:
- Plain prose, no bullet points, no headers
- 2-4 sentences maximum
- Numbers in Indian format (₹X,XX,XXX)
- Percentages as written (12.5%, 20%, etc.)

WHAT YOU ARE NOT:
- Not a financial advisor
- Not a tax advisor  
- Not making recommendations
- Not predicting the future

You are a narrator. The numbers speak. You translate them into plain English.
"""


def _call_claude(prompt: str) -> Optional[str]:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        log.error(f"Claude failed: {e}")
        return None


def _call_groq(prompt: str) -> Optional[str]:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            max_tokens=400,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"Groq failed: {e}")
        return None


def _rule_based_narrative(data: dict) -> str:
    """
    Fallback when no LLM is available.
    Template-based but always accurate — uses only computed numbers.
    """
    t = data.get("treatment", "")
    act = data.get("act_ref", "Verify with CA")
    gain = data.get("gain", 0)
    tax = data.get("tax", 0)
    rate = data.get("rate", "slab rate")

    if "LTCG" in t:
        exemption = data.get("exemption_applied", 0)
        return (f"This holding qualifies as Long Term Capital Gain. "
                f"Gain: ₹{gain:,.0f}. Exemption applied: ₹{exemption:,.0f}. "
                f"Taxable: ₹{gain-exemption:,.0f} at {rate} = ₹{tax:,.0f} tax. "
                f"Source: {act}. Verify with a CA before filing.")
    elif "STCG" in t:
        return (f"This holding qualifies as Short Term Capital Gain. "
                f"Gain: ₹{gain:,.0f} taxed at {rate} = ₹{tax:,.0f}. "
                f"Source: {act}. Verify with a CA before filing.")
    elif t == "Slab rate":
        return (f"This income is taxed at your applicable slab rate. "
                f"Amount: ₹{gain:,.0f}. Estimated tax at {rate}: ₹{tax:,.0f}. "
                f"Source: {act}. Verify with a CA before filing.")
    else:
        return f"Estimated tax: ₹{tax:,.0f}. Source: {act}. Verify with a CA before filing."


def write_narrative(computation: dict, rule: dict) -> str:
    """
    Main entry point.
    Claude (primary) → Groq (fallback) → Rule-based template.
    """
    # Build the input prompt with all computed data
    prompt = f"""
Structured computation input:

COMPUTATION:
{json.dumps(computation, indent=2, default=str)}

FINANCE ACT RULE (extracted from PDF by Gemini):
{json.dumps(rule, indent=2, default=str)}

Write 2-4 sentences explaining what these numbers mean for this investor.
Follow all rules in your system prompt exactly.
"""

    # Try Claude first
    narrative = _call_claude(prompt)
    if narrative:
        log.info("Narrative: Claude")
        return narrative

    # Try Groq
    narrative = _call_groq(prompt)
    if narrative:
        log.info("Narrative: Groq")
        return narrative

    # Rule-based fallback
    log.info("Narrative: Rule-based fallback")
    return _rule_based_narrative({**computation, **rule})


def write_query_answer(query_result: dict, portfolio_computation: dict) -> str:
    """
    Write the answer to a user's Finance Act query.
    Same LLM priority: Claude → Groq → rule-based.
    """
    if not query_result.get("is_answerable_from_document"):
        reason = query_result.get("reason_if_not", "")
        redirect = query_result.get("redirect_module", "")

        if reason == "not_tax_query":
            redirect_text = ""
            if redirect == "MF_INTEL":
                redirect_text = " For fund analysis, use MF Intel."
            elif redirect == "EQUITY_INTEL":
                redirect_text = " For stock analysis, use Equity Intel."
            return (f"This module answers only questions about Finance Act tax rules "
                    f"or how they apply to your holdings.{redirect_text}")

        return (f"This question cannot be answered from the Finance Acts provided. "
                f"Reason: {reason}. Verify with a CA before filing.")

    prompt = f"""
Query result from Finance Act PDF:

QUERY RESULT:
{json.dumps(query_result, indent=2, default=str)}

PORTFOLIO COMPUTATION (if applicable):
{json.dumps(portfolio_computation, indent=2, default=str)}

Write 2-4 sentences answering the user's question.
Reference specific numbers where available.
Cite the exact section and Finance Act year.
End with: "Source: [section], [act year]. Verify with a CA before filing."
"""

    narrative = _call_claude(prompt)
    if narrative:
        return narrative

    narrative = _call_groq(prompt)
    if narrative:
        return narrative

    # Rule-based fallback for query
    section = query_result.get("primary_section", "")
    act     = query_result.get("act_name", "")
    answer  = query_result.get("plain_answer", "See Finance Act for details.")
    caveat  = query_result.get("caveat", "Verify with a CA before filing.")
    return f"{answer} Source: {section}, {act}. {caveat}"


def write_flag_narrative(flag_data: dict) -> str:
    """
    Write 1-2 sentences for a specific tax flag/opportunity.
    Used for the FLAGS AND OPPORTUNITIES section of the brief.
    """
    prompt = f"""
Tax flag data:
{json.dumps(flag_data, indent=2, default=str)}

Write exactly 1-2 sentences describing this flag.
Include: the specific number(s), the Finance Act reference, and the effective date.
Do NOT say what the investor should do. Only state what the numbers show.
End with: "Source: [section], [act year]."
"""

    narrative = _call_claude(prompt)
    if narrative:
        return narrative

    narrative = _call_groq(prompt)
    if narrative:
        return narrative

    # Rule-based fallback
    return (f"{flag_data.get('description', '')} "
            f"Source: {flag_data.get('act_ref', 'Verify with CA')}.")
