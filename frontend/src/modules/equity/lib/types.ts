// ── Search ────────────────────────────────────────────────────────────────────
export interface EquitySearchResult {
  bse_code:     string
  nse_symbol:   string
  company_name: string
  sector:       string
  screener_url?: string
}

// ── Metrics ───────────────────────────────────────────────────────────────────
export interface EquityMetrics {
  revenue?:       number | null
  ebitda?:        number | null
  ebitda_margin?: number | null
  pat?:           number | null
  pat_margin?:    number | null
  cfo?:           number | null
  fcf?:           number | null
  capex?:         number | null
  borrowings?:    number | null
  cash?:          number | null
  net_debt?:      number | null
  total_equity?:  number | null
  roce?:          number | null
  roe?:           number | null
  cfo_to_pat?:    number | null
  interest_cov?:  number | null
  net_debt_ebitda?:number | null
  debt_equity?:   number | null
  nwc_days?:      number | null
  inventory_days?:number | null
  receivable_days?:number | null
  pe?:            number | null
  market_cap_cr?: number | null
  current_price?: number | null
  book_value?:    number | null
  // CAGRs
  rev_cagr_3y?:   number | null
  rev_cagr_5y?:   number | null
  rev_cagr_10y?:  number | null
  pat_cagr_3y?:   number | null
  pat_cagr_5y?:   number | null
  // Arrays for trend table
  rev_arr?:       (number|null)[]
  ebit_arr?:      (number|null)[]
  pat_arr?:       (number|null)[]
  roce_arr?:      (number|null)[]
  cfo_arr?:       (number|null)[]
  margin_hist?:   (number|null)[]
  // Trends
  roce_trend?:    string
  rev_trend?:     string
  margin_trend?:  string
  cwip_pct?:      number | null
  // Other
  [key: string]:  unknown
}

// ── Qualitative (from Gemini) ─────────────────────────────────────────────────
export interface Qualitative {
  business?:      Record<string,unknown>
  strategy?:      Record<string,unknown>
  risks?:         string[]
  management?:    string
  moat?:          string
  [key: string]:  unknown
}

// ── DCF ───────────────────────────────────────────────────────────────────────
export interface DCFResult {
  available:       boolean
  bear_cr?:        number | null
  base_cr?:        number | null
  bull_cr?:        number | null
  wacc_pct?:       number | null
  terminal_growth?:number | null
  cost_of_equity?: number | null
  anchor_label?:   string
  base_growth?:    number[]
  ebitda_margin?:  number | null
  capex_pct?:      number | null
  sensitivity?:    Record<string, Record<string,number|null>>
}

// ── Pattern ───────────────────────────────────────────────────────────────────
export interface PatternInsight {
  name:    string
  insight: string
  signal:  'STRENGTH' | 'WARNING' | 'NORMAL' | 'INFO'
}

// ── Early warning ─────────────────────────────────────────────────────────────
export interface EarlyWarning {
  label:            string
  current:          number | null
  threshold_warn:   number | null
  threshold_crit:   number | null
  status:           'OK' | 'WARN' | 'CRITICAL'
  calibration?:     string
  interpretation?:  string
}

// ── Scenarios ─────────────────────────────────────────────────────────────────
export interface ScenarioResult {
  label:          string
  probability:    number
  rev_cagr_mult:  number
  margin_delta:   number
  intrinsic_value?:number | null
  trigger?:       string
}

export interface ProbabilityScenarios {
  bear?:  ScenarioResult
  base?:  ScenarioResult
  bull?:  ScenarioResult
  implied_disruption_prob?: number | null
}

// ── Macro signal ──────────────────────────────────────────────────────────────
export interface MacroSignal {
  signal:  string
  text:    string
  impact:  string
}

// ── AI intelligence ───────────────────────────────────────────────────────────
export interface Intelligence {
  essence?:       string
  misses?:        string
  verdict?:       string
  watchlist?:     Array<{metric:string; threshold:string; interpretation:string}>
  provider?:      string
  raw?:           string
}

// ── Full brief ────────────────────────────────────────────────────────────────
export interface EquityBrief {
  status:            'ready'|'processing'|'error'|'not_found'|'expired'
  bse_code?:         string
  nse_symbol?:       string
  company_name?:     string
  sector?:           string
  fy_year?:          number
  fin_raw?:          Record<string,unknown>
  metrics?:          EquityMetrics
  qualitative?:      Qualitative
  sec_d?:            Record<string,unknown>
  dcf?:              DCFResult
  peers?:            Record<string, Record<string,number|null>>
  spreads?:          Record<string, Record<string,unknown>>
  implied_growth?:   number | null
  patterns?:         PatternInsight[]
  early_warnings?:   EarlyWarning[]
  scenarios?:        ProbabilityScenarios
  macro_signals?:    MacroSignal[]
  intelligence?:     Intelligence
  conviction?:       string
  conviction_reason?:string
  generated_at?:     string
  cached_at?:        string
  expires_at?:       string
  message?:          string
  error?:            string
}

export interface HistoryItem {
  bse_code:     string
  company_name: string
  sector:       string
  conviction:   string | null
  analysed_at:  string
}

export interface SectorProfile {
  key:          string
  peers:        string[]
  value_driver: string
  normal_roce:  [number,number] | null
  normal_margin:[number,number] | null
}
