import type { EquitySearchResult, EquityBrief, HistoryItem, SectorProfile } from './types'

const BASE = '/api/equity'
const STORAGE_KEY = 'fintelligence_user'

function getJWT(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw)?.accessToken ?? null
  } catch { return null }
}

function authHeaders(): Record<string, string> {
  const jwt = getJWT()
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (jwt) h['Authorization'] = `Bearer ${jwt}`
  return h
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (!r.ok) { const e = await r.json().catch(() => ({ detail: r.statusText })); throw new Error(e.detail || `HTTP ${r.status}`) }
  return r.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { method: 'POST', headers: authHeaders(), body: JSON.stringify(body) })
  if (!r.ok) { const e = await r.json().catch(() => ({ detail: r.statusText })); throw new Error(e.detail || `HTTP ${r.status}`) }
  return r.json()
}

export interface AnalyseRequest {
  bse_code: string; nse_symbol: string; company_name: string; sector: string
  fy_year?: number
  sector_params?: { beta: number; risk_free_rate: number; equity_risk_premium: number; terminal_growth: number; cost_of_debt_pretax: number; tax_rate: number }
}

export const api = {
  health:     () => get<{ status: string; engine: string; gemini: string; groq: string }>('/health'),
  search:     (q: string) => get<{ results: EquitySearchResult[]; count: number }>(`/search?q=${encodeURIComponent(q)}`),
  analyse:    (req: AnalyseRequest) => post<{ status: string; message: string }>('/analyse', {
    fy_year: 2024,
    sector_params: { beta:1.0, risk_free_rate:7.0, equity_risk_premium:6.5, terminal_growth:6.5, cost_of_debt_pretax:8.0, tax_rate:25.0 },
    ...req,
  }),
  getBrief:   (bse_code: string, fy_year = 2024): Promise<EquityBrief> => get(`/brief/${bse_code}?fy_year=${fy_year}`),
  getSectors: (): Promise<{ sectors: SectorProfile[] }> => get('/sectors'),
  getMacro:   (sector: string) => get<{ signals: any[]; raw: Record<string, unknown> }>(`/macro/${sector}`),
  history:    (limit = 10): Promise<{ history: HistoryItem[] }> => get(`/history?limit=${limit}`),
  clearCache: (bse_code: string, fy_year = 2024) =>
    fetch(`${BASE}/cache/${bse_code}?fy_year=${fy_year}`, { method: 'DELETE', headers: authHeaders() }).then(r => r.json()),
}

export async function pollBrief(bse_code: string, fy_year = 2024, onStatus?: (msg: string) => void, maxSeconds = 480): Promise<EquityBrief> {
  // 480s = 8 min hard ceiling. Gemini reading a large annual report PDF takes 3-5 min on average.
  // The backend keeps running even if the frontend times out — result lands in cache for next open.
  const deadline = Date.now() + maxSeconds * 1000
  const steps = [
    'Connecting to BSE India — fetching annual report PDF...',
    'PDF fetched. Gemini 2.5 Flash reading the annual report — this takes 3–5 minutes for large filings...',
    'Gemini still reading — annual reports can be 200-400 pages...',
    'Gemini read complete. Extracting financial statements...',
    'Fetching 10-year financials from Screener.in...',
    'Fetching peer companies and sector data...',
    'Computing DCF valuation and implied growth rate...',
    'Running sector-specific pattern recognition...',
    'Checking early warning thresholds...',
    'Running probability scenarios (bear / base / bull)...',
    'Groq synthesis — writing essence and verdict...',
    'Almost done — finalising brief...',
  ]
  let step = 0
  while (Date.now() < deadline) {
    const brief = await api.getBrief(bse_code, fy_year)
    if (brief.status === 'ready')     return brief
    if (brief.status === 'error')     return brief
    if (brief.status === 'not_found') return brief
    if (onStatus) { onStatus(steps[Math.min(step, steps.length - 1)]); step++ }
    await new Promise(r => setTimeout(r, 8000))
  }
  return { status: 'error', error: 'Analysis timed out after 8 minutes. The backend may still be running — try opening this company again in a minute to load from cache.' }
}
