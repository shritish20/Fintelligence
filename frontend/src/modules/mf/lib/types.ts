export interface SearchResult {
  scheme_code: number
  scheme_name: string
  fund_house:  string
  scheme_type: string
  scheme_category: string
}

export interface RollingReturns {
  available:       boolean
  n_obs:           number
  mean:            number | null
  median:          number | null
  min:             number | null
  max:             number | null
  pct_positive:    number | null
  pct_above_8:     number | null
  pct_above_12:    number | null
  pct_above_rf?:   number | null
}

export interface CaptureRatios {
  upside_capture:   number | null
  downside_capture: number | null
}

export interface BetaAlpha {
  beta:      number | null
  alpha:     number | null
  r_squared: number | null
}

export interface MaxDrawdown {
  max_drawdown_pct: number | null
  peak_date:        string | null
  trough_date:      string | null
  recovery_date:    string | null
}

export interface YTMEstimate {
  ytm_estimate: number | null
  note:         string
}

export interface Metrics {
  as_of:              string
  fund_type:          'equity' | 'debt'
  cagr:               Record<string, number | null>
  benchmark_cagr?:    Record<string, number | null>
  rolling_1Y?:        RollingReturns
  rolling_3Y?:        RollingReturns
  rolling_5Y?:        RollingReturns
  std_dev:            number | null
  sharpe:             number | null
  sortino?:           number | null
  max_drawdown:       MaxDrawdown
  sip_xirr:          number | null
  dd_covid?:          number | null
  dd_2022?:           number | null
  dd_ilfs?:           number | null
  beta_alpha?:        BetaAlpha
  information_ratio?: number | null
  capture_ratios?:    CaptureRatios
  bench_name?:        string | null
  // Debt specific
  negative_months?:   number | null
  ytm_estimate?:      YTMEstimate
  rate_sensitivity?:  Record<string, unknown>
  sd_anomaly?:        Record<string, unknown>
  expense_efficiency?:Record<string, unknown>
  debt_profile?:      Record<string, unknown>
}

export interface FundMeta {
  aum_crore:     number | null
  expense_ratio: number | null
  fund_manager:  string | null
  isin:          string | null
  meta_source:   string | null
}

export interface Holdings {
  available:    boolean
  total_stocks: number
  top5_pct:     number | null
  top10_pct:    number | null
  cash_pct:     number | null
  holdings:     Array<{name:string; pct_nav:number; sector?:string; isin?:string}>
  sector_alloc: Record<string, number>
}

export interface AIBrief {
  narrative: string
  provider:  string
}

export interface Flags {
  green: string[]
  amber: string[]
  red:   string[]
}

export interface FundBrief {
  status:            'ready' | 'processing' | 'error' | 'not_found' | 'expired'
  scheme_code?:      number
  scheme_name?:      string
  fund_house?:       string
  category?:         string
  fund_type?:        'equity' | 'debt'
  metadata?:         FundMeta
  metrics?:          Metrics
  ai?:               AIBrief
  conviction?:       string
  conviction_reason?:string
  flags?:            Flags
  holdings?:         Holdings
  regime?:           Record<string, unknown> | null
  generated_at?:     string
  cached_at?:        string
  expires_at?:       string
  message?:          string
  error?:            string
}

export interface CompareResult {
  status:   'ready' | 'not_ready'
  fund_a?:  Record<string, unknown>
  fund_b?:  Record<string, unknown>
  overlap?: Record<string, unknown> | null
  missing?: number[]
  message?: string
}

export interface PortfolioOverlap {
  status:         'ready' | 'not_ready'
  funds?:         Array<Record<string, unknown>>
  overlap_matrix?:Record<string, Record<string, number | null>>
  fund_names?:    Record<string, string>
  missing?:       number[]
}

export interface HistoryItem {
  scheme_code: string
  scheme_name: string
  fund_type:   string
  conviction:  string | null
  analysed_at: string
}
