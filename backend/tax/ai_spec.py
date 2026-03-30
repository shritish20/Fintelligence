"""
AI API Usage — Fintelligence Tax Module 4
==========================================

THREE AI ROLES. THREE TOOLS. CLEAR BOUNDARIES.

─────────────────────────────────────────────────────────────────
ROLE 1: GEMINI — Finance Act PDF Reader (Rule Extraction)
─────────────────────────────────────────────────────────────────
Purpose : Extract exact rules from Finance Act PDFs
Model   : gemini-2.0-flash (or gemini-2.5-flash if available)
When    : Every time a tax rule needs to be determined
What    : Reads the relevant Finance Act PDF, extracts the exact
          section text, returns structured JSON with:
            - section number
            - Finance Act year and act number
            - effective date
            - verbatim text
            - plain interpretation
Input   : PDF bytes + structured extraction prompt
Output  : Structured JSON — NEVER free-form narrative
Rule    : NEVER answer from memory. Only from the PDF provided.
          If section not found in PDF → return {"found": false}

─────────────────────────────────────────────────────────────────
ROLE 2: CLAUDE (primary) / GROQ (fallback) — Narrative Writer
─────────────────────────────────────────────────────────────────
Purpose : Write plain English from computed numbers + extracted rules
Priority: Claude (ANTHROPIC_API_KEY) → Groq (GROQ_API_KEY) → Rule-based
When    : After Python computes all numbers AND Gemini extracts the rule
What    : 2-4 sentences. Plain language. Specific numbers. 
          Section cited. Year cited. Nothing else.
Input   : Structured computation output + Gemini-extracted rule
Output  : Plain English narrative
Rules   : 
  - Every sentence must reference a number from the input
  - Never add information not in the input
  - Never use: should, advise, recommend, suggest
  - Never speculate about future budgets
  - Always end with: Source: [Section], [Finance Act Year]
  - If any ambiguity in rule: add "Verify with a CA before filing"

─────────────────────────────────────────────────────────────────
ROLE 3: CLAUDE (primary) / GROQ (fallback) — Query Answerer
─────────────────────────────────────────────────────────────────
Purpose : Answer user queries about Finance Act or their portfolio tax
Priority: Same as Role 2
When    : User submits a query in the query box
What    : 
  Step 1 — Gemini reads relevant section from Finance Act PDF
  Step 2 — Python applies to user's portfolio if relevant
  Step 3 — Claude/Groq writes the answer
Rules   :
  - Only answer tax questions referencing Finance Acts
  - Only answer portfolio-specific questions using actual holdings
  - For everything else → refuse with specific redirect message
  - Never answer from memory
  - Always cite section + Finance Act year + effective date

─────────────────────────────────────────────────────────────────
RULE-BASED FALLBACK (no API keys)
─────────────────────────────────────────────────────────────────
If no Gemini key  → cannot extract rules → all outputs flagged 
                    "Set GEMINI_API_KEY for Finance Act references"
If no Claude/Groq → use pre-built templates with computed numbers
                    No narrative, but all numbers still computed and shown
The module still works without LLMs — just no plain English narrative.
Numbers, sections, and Finance Act references are always Python-computed.

─────────────────────────────────────────────────────────────────
FINANCE ACT PDFs — THE ONLY SOURCE OF TRUTH
─────────────────────────────────────────────────────────────────
finance_act_2023.pdf      → Section 50AA (debt MF restructuring)
finance_act_2024_no2.pdf  → LTCG 12.5%, STCG 20%, SGB (w.e.f 23 Jul 2024)
income_tax_act_2025.pdf   → Consolidated, all amendments in force Apr 2025

Download from: https://incometaxindia.gov.in/pages/acts/income-tax-act.aspx
               https://indiacode.nic.in

These PDFs are the ONLY source Gemini is allowed to read for rules.
If a rule is not in these PDFs → the module says "verify with a CA".
"""
