export interface Flag { priority: 'URGENT'|'WATCH'|'GREEN'; type: string; title: string; number: number; description: string; act_ref: string; effective: string; saving?: number; narrative?: string; action_date?: string }
export interface IncomeRow { head: string; amount: number; treatment: string; tax_at_slab: number; act_ref: string; exemption?: number; taxable?: number }
export interface RegimeComparison { old_regime: { total_tax:number; slab_tax:number; deductions_claimed:number }; new_regime: { total_tax:number; slab_tax:number }; better_regime:'new'|'old'; saving: number; act_ref: string; note: string }
export interface AdvanceTaxInstall { due_date: string; label: string; amount_due: number; status: 'OVERDUE'|'UPCOMING'|'PAID'; is_past: boolean; penalty_if_late: number; act_ref: string }
export interface HarvestOpportunity { instrument: string; unrealised_gain: number; harvestable: number; tax_if_harvest_now: number; tax_saving: number; strategy: string; act_ref: string }
export interface MFBreakdown { name: string; type: string; gain: number; treatment: string; act_section: string; act_year: string; tax_if_sold_today: number; note: string }
export interface TaxBrief { is_demo?: boolean; demo_note?: string; financial_year: string; assessment_year: string; generated_at: string; summary: { estimated_tax_new_regime: number; estimated_tax_old_regime: number; better_regime: string; regime_saving: number; ltcg_exemption_used: number; ltcg_exemption_remaining: number; total_harvest_opportunity: number; total_deductible_expenses: number; act_ref_regime: string }; income_breakdown: IncomeRow[]; regime_comparison: RegimeComparison; flags: Flag[]; harvest_opportunities: HarvestOpportunity[]; fo_detail: { gross_profit: number; gross_loss: number; net_pnl: number; net_taxable: number; expenses: { total:number; breakdown:Record<string,number>; act_ref:string }; act_ref: string }; mf_breakdown: MFBreakdown[]; advance_tax: { estimated_annual_tax: number; paid_so_far: number; schedule: AdvanceTaxInstall[]; act_ref: string }; data_sources?: { zerodha?:string; cams?:string; uploaded_at?:string } }
export interface QueryResponse { query: string; answer: string; section?: string; act?: string; effective?: string; answerable: boolean; redirect?: string; caveat: string }
export interface HealthStatus { status: string; gemini: string; claude: string; groq: string; finance_act_pdfs: string[]; pdf_count: number }

const BASE = '/api/tax'
const STORAGE_KEY = 'fintelligence_user'

function getJWT(): string | null {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')?.accessToken ?? null } catch { return null }
}

function authHeaders(): Record<string, string> {
  const jwt = getJWT()
  const h: Record<string, string> = {}
  if (jwt) h['Authorization'] = `Bearer ${jwt}`
  return h
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`) }
  return r.json()
}

export const api = {
  health:       () => get<HealthStatus>('/health'),
  // FIX: was '/tax/brief/demo' → double prefix. Now '/brief/demo' → /api/tax/brief/demo ✓
  getDemoBrief: () => get<TaxBrief>('/brief/demo'),

  uploadStatements: async (zerodhaFile?: File, camsFile?: File): Promise<TaxBrief> => {
    const form = new FormData()
    if (zerodhaFile) form.append('zerodha_file', zerodhaFile)
    if (camsFile)    form.append('cams_file', camsFile)
    // FIX: was '/tax/upload' → now '/upload'
    const r = await fetch(`${BASE}/upload`, { method: 'POST', headers: authHeaders(), body: form })
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`) }
    return r.json()
  },

  query: async (q: string): Promise<QueryResponse> => {
    // FIX: was '/tax/query' → now '/query'
    const r = await fetch(`${BASE}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ query: q }),
    })
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`) }
    return r.json()
  },

  // FIX: was '/tax/finance-acts' → now '/finance-acts'
  financeActs: () => get<{ available_pdfs: string[]; missing_pdfs: string[]; download_sources: Record<string, string> }>('/finance-acts'),
}

export const fmtINR = (v: number|null|undefined): string => { if (v == null || isNaN(v)) return 'N/A'; if (Math.abs(v) >= 100_000) return `₹${(v/100_000).toFixed(2)}L`; if (Math.abs(v) >= 1_000) return `₹${(v/1_000).toFixed(1)}K`; return `₹${v.toFixed(0)}` }
export const fmtINRFull = (v: number|null|undefined): string => { if (v == null || isNaN(v)) return 'N/A'; return `₹${Math.abs(v).toLocaleString('en-IN')}` }
export const colorAmt = (v: number|null|undefined, invert = false): string => { if (v == null || isNaN(v)) return 'text-muted-fg'; if (invert) return v > 0 ? 'text-signal-red' : v < 0 ? 'text-neon-green' : 'text-foreground'; return v > 0 ? 'text-neon-green' : v < 0 ? 'text-signal-red' : 'text-foreground' }

export const flagClass = (priority: Flag['priority']): string => {
  if (priority === 'URGENT') return 'border border-signal-red/40'
  if (priority === 'WATCH')  return 'border border-amber-500/40'
  return 'border border-neon-green/30'
}

export const flagIcon = (priority: Flag['priority']): string => {
  if (priority === 'URGENT') return '🚨'
  if (priority === 'WATCH')  return '⚠️'
  return '✅'
}

export const flagColor = (priority: Flag['priority']): string => {
  if (priority === 'URGENT') return 'text-signal-red'
  if (priority === 'WATCH')  return 'text-amber-400'
  return 'text-neon-green'
}
