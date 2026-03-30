import type { SearchResult, FundBrief, CompareResult, PortfolioOverlap, HistoryItem } from './types'

const BASE = '/api/mf'
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

export const api = {
  health:          () => get<{ status: string; engine: string }>('/health'),
  search:          (q: string): Promise<{ results: SearchResult[]; count: number }> => get(`/search?q=${encodeURIComponent(q)}`),
  analyse:         (scheme_code: number, with_regime = false) => post<{ status: string; cache_key: string; message: string }>('/analyse', { scheme_code, with_regime }),
  getBrief:        (scheme_code: number, with_regime = false): Promise<FundBrief> => get(`/brief/${scheme_code}?with_regime=${with_regime}`),
  compare:         (code_a: number, code_b: number): Promise<CompareResult> => post('/compare', { code_a, code_b }),
  portfolioOverlap:(scheme_codes: number[], names?: string[]): Promise<PortfolioOverlap> => post('/portfolio/overlap', { scheme_codes, names }),
  history:         (limit = 10): Promise<{ history: HistoryItem[] }> => get(`/history?limit=${limit}`),
  clearCache:      (scheme_code: number) => fetch(`${BASE}/cache/${scheme_code}`, { method: 'DELETE', headers: authHeaders() }).then(r => r.json()),
}

export async function pollBrief(scheme_code: number, with_regime = false, onStatus?: (msg: string) => void, maxSeconds = 240): Promise<FundBrief> {
  // 240s = 4 min. NAV fetch + AMFI holdings + AI synthesis typically takes 60-120s.
  const deadline = Date.now() + maxSeconds * 1000
  const messages = [
    'Fetching NAV history from mfapi.in...',
    'Loading fund metadata and ISIN...',
    'Fetching AMFI portfolio holdings...',
    'Computing rolling returns (1Y / 3Y / 5Y)...',
    'Calculating Sharpe, Sortino, drawdown, capture ratios...',
    'Running AI synthesis — writing conviction brief...',
    'Finalising brief...',
  ]
  let msgIdx = 0
  while (Date.now() < deadline) {
    const brief = await api.getBrief(scheme_code, with_regime)
    if (brief.status === 'ready')     return brief
    if (brief.status === 'error')     return brief
    if (brief.status === 'not_found') return brief
    if (onStatus) { onStatus(messages[Math.min(msgIdx, messages.length - 1)]); msgIdx++ }
    await new Promise(r => setTimeout(r, 5000))
  }
  return { status: 'error', error: 'Analysis timed out after 4 minutes. Try opening this fund again — it may have completed in the background.' }
}
