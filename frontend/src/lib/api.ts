import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios'
import type {
  ProfessionalDashboard, LiveData, TradeEntry, SystemConfig,
  HealthData, ReconcileData, FillQualityData, GTTOrder, PnLAttribution,
  V5BriefResponse, V5NewsResponse, V5VetoLogResponse, V5AlertsResponse,
  V5MacroSnapshot, V5GlobalTone, V5Status, V5LLMUsage,
} from './types'

// Empty baseURL = requests go to whatever host served the HTML (nginx in prod)
const API_BASE = (import.meta.env.VITE_API_BASE as string || '').trim()

const STORAGE_KEY = 'fintelligence_user'

function getJWT(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw)?.accessToken ?? null
  } catch { return null }
}

interface CacheEntry<T> { data: T; timestamp: number; ttl: number }

class ApiCache {
  private cache = new Map<string, CacheEntry<unknown>>()
  private pending = new Map<string, Promise<unknown>>()
  get<T>(key: string): T | null {
    const e = this.cache.get(key)
    if (!e) return null
    if (Date.now() - e.timestamp > e.ttl) { this.cache.delete(key); return null }
    return e.data as T
  }
  set<T>(key: string, data: T, ttl: number) { this.cache.set(key, { data, timestamp: Date.now(), ttl }) }
  getPending<T>(key: string): Promise<T> | undefined { return this.pending.get(key) as Promise<T> }
  setPending<T>(key: string, p: Promise<T>) { this.pending.set(key, p as Promise<unknown>); p.finally(() => this.pending.delete(key)) }
  clear() { this.cache.clear() }
  clearKey(key: string) { this.cache.delete(key) }
}

const cache = new ApiCache()
const TTL = { DASHBOARD: 60000, LIVE: 2000, INTEL: 60000, NEWS: 30000, HEALTH: 15000 }

let isLoggingOut = false

const api: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
})

// Attach JWT on every request
api.interceptors.request.use((config) => {
  if (isLoggingOut) {
    const ctrl = new AbortController()
    config.signal = ctrl.signal
    ctrl.abort()
    return config
  }
  const jwt = getJWT()
  if (jwt) config.headers['Authorization'] = `Bearer ${jwt}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  async (err: AxiosError) => {
    if (axios.isCancel(err)) return Promise.reject(err)
    const cfg = err.config as AxiosRequestConfig & { _retry?: number }
    if (err.response?.status === 401 && !isLoggingOut) {
      isLoggingOut = true
      localStorage.removeItem(STORAGE_KEY)
      window.dispatchEvent(new CustomEvent('auth:logout'))
      setTimeout(() => { isLoggingOut = false }, 5000)
      return Promise.reject(err)
    }
    const retryable = [408, 429, 500, 502, 503, 504]
    if (cfg && retryable.includes(err.response?.status ?? 0)) {
      cfg._retry = cfg._retry ?? 0
      if (cfg._retry < 3) {
        cfg._retry++
        await new Promise(r => setTimeout(r, 1000 * Math.pow(2, cfg._retry! - 1)))
        return api(cfg)
      }
    }
    return Promise.reject(err)
  }
)

async function cached<T>(key: string, fn: () => Promise<T>, ttl: number, force = false): Promise<T> {
  if (!force) { const hit = cache.get<T>(key); if (hit) return hit }
  const pending = cache.getPending<T>(key); if (pending) return pending
  const promise = fn(); cache.setPending(key, promise)
  const data = await promise; cache.set(key, data, ttl); return data
}

// ── Auth API ──────────────────────────────────────────────────────────────────
export interface AuthResponse {
  access_token: string
  token_type: string
  email: string
  user_id: number
  has_upstox_token?: boolean
}

export async function authRegister(email: string, password: string): Promise<AuthResponse> {
  const r = await api.post('/api/auth/register', { email, password })
  return r.data
}

export async function authLogin(email: string, password: string): Promise<AuthResponse> {
  const r = await api.post('/api/auth/login', { email, password })
  return r.data
}

// ── Broker token helpers (Option B) ──────────────────────────────────────────
// The broker token never touches localStorage or the server database.
// It lives only in sessionStorage (see AppContext) and is sent per-request
// via X-Upstox-Token for endpoints that need live broker access.

const UPSTOX_SESSION_KEY = 'fintelligence_upstox_token'

function getUpstoxToken(): string | null {
  try { return sessionStorage.getItem(UPSTOX_SESSION_KEY) } catch { return null }
}

/**
 * Activates the broker session on the server in-memory.
 * The token is NOT stored in the DB — it is held only in the server process
 * for the current SDK session, and in the client's sessionStorage.
 */
export async function activateUpstoxToken(token: string): Promise<{ success: boolean }> {
  const r = await api.post('/api/auth/upstox-token', { upstox_token: token })
  return r.data
}

/** @deprecated Use activateUpstoxToken instead */
export const saveUpstoxToken = activateUpstoxToken

// Attach X-Upstox-Token on requests that need live broker access
// Usage: api.get('/api/live/positions', withBrokerToken())
export function withBrokerToken(): { headers: Record<string, string> } {
  const token = getUpstoxToken()
  return token ? { headers: { 'X-Upstox-Token': token } } : { headers: {} }
}

// ── Volguard API ──────────────────────────────────────────────────────────────
// Intelligence endpoints — JWT only, no broker token needed
export async function fetchDashboard(force = false): Promise<ProfessionalDashboard> {
  return cached('dashboard', async () => { const r = await api.get('/api/dashboard/professional'); return r.data }, TTL.DASHBOARD, force)
}
export async function fetchJournal(limit = 50): Promise<TradeEntry[]> {
  const r = await api.get(`/api/journal/history?limit=${limit}`); return r.data
}
export async function fetchCurrentConfig(): Promise<SystemConfig> {
  const r = await api.get('/api/system/config/current'); return r.data
}
export async function saveConfig(payload: Record<string, unknown>): Promise<unknown> {
  const r = await api.post('/api/system/config', payload); cache.clearKey('dashboard'); return r.data
}
export async function fetchLogs(lines = 50): Promise<Array<{ timestamp: string; level: string; message: string }>> {
  const r = await api.get(`/api/system/logs?lines=${lines}`); return r.data?.logs ?? []
}
export async function fetchHealth(force = false): Promise<HealthData> {
  return cached('health', async () => { const r = await api.get('/api/health'); return r.data }, TTL.HEALTH, force)
}

// ── Trading endpoints — require X-Upstox-Token header (Option B) ─────────────
// These call broker APIs. The token lives in sessionStorage and is sent
// per-request via withBrokerToken(). Never stored server-side.
export async function fetchLivePositions(force = false): Promise<LiveData> {
  return cached('live', async () => {
    const r = await api.get('/api/live/positions', withBrokerToken())
    return r.data
  }, TTL.LIVE, force)
}
export async function fetchBulkPrice(instruments: string[]): Promise<Record<string, number>> {
  const r = await api.get(
    `/api/market/bulk-last-price?instruments=${encodeURIComponent(instruments.join(','))}`,
    withBrokerToken()
  )
  return r.data?.prices ?? {}
}
export async function fetchReconcile(): Promise<ReconcileData> {
  const r = await api.get('/api/positions/reconcile', withBrokerToken()); return r.data
}
export async function triggerReconcile(): Promise<{ success: boolean; message: string }> {
  const r = await api.post('/api/positions/reconcile/trigger', {}, withBrokerToken()); return r.data
}
export async function fetchFillQuality(): Promise<FillQualityData | null> {
  try {
    const r = await api.get('/api/orders/fill-quality', withBrokerToken())
    if (!r.data?.total_fills) return null
    return r.data
  } catch { return null }
}
export async function fetchGTTList(): Promise<GTTOrder[]> {
  const r = await api.get('/api/gtt/list', withBrokerToken()); return r.data?.gtt_orders ?? []
}
export async function cancelGTT(gttId: string): Promise<unknown> {
  const r = await api.delete(`/api/gtt/${gttId}`, withBrokerToken()); return r.data
}
export async function fetchPnLAttribution(): Promise<PnLAttribution | null> {
  try {
    const r = await api.get('/api/pnl/attribution', withBrokerToken())
    if (!r.data || Object.keys(r.data).length === 0) return null
    return r.data
  } catch { return null }
}
export async function emergencyExitAll(): Promise<{ success: boolean; orders_placed: number; message: string }> {
  const r = await api.post('/api/emergency/exit-all', {}, withBrokerToken()); return r.data
}

// ── Intelligence layer — JWT only ─────────────────────────────────────────────
export async function fetchV5Status(force = false): Promise<V5Status> {
  return cached('v5status', async () => { const r = await api.get('/api/v5/status'); return r.data }, TTL.INTEL, force)
}
export async function fetchMorningBrief(force = false): Promise<V5BriefResponse> {
  return cached('brief', async () => { const r = await api.get('/api/intelligence/brief'); return r.data }, TTL.INTEL, force)
}
export async function generateBrief(): Promise<{ status: string; message: string }> {
  cache.clearKey('brief'); const r = await api.post('/api/intelligence/brief/generate'); return r.data
}
export async function fetchGlobalTone(force = false): Promise<V5GlobalTone> {
  return cached('globaltone', async () => { const r = await api.get('/api/intelligence/global-tone'); return r.data }, TTL.INTEL, force)
}
export async function fetchMacroSnapshot(force = false): Promise<V5MacroSnapshot> {
  return cached('macro', async () => { const r = await api.get('/api/intelligence/macro-snapshot'); return r.data }, TTL.INTEL, force)
}
export async function fetchNews(force = false): Promise<V5NewsResponse> {
  return cached('news', async () => { const r = await api.get('/api/intelligence/news'); return r.data }, TTL.NEWS, force)
}
export async function fetchVetoLog(limit = 20): Promise<V5VetoLogResponse> {
  const r = await api.get(`/api/intelligence/veto-log?limit=${limit}`); return r.data
}
export async function overrideVeto(reason: string): Promise<{ success: boolean; message: string }> {
  const r = await api.post('/api/intelligence/override', { reason }); return r.data
}
export async function fetchAlerts(limit = 10): Promise<V5AlertsResponse> {
  const r = await api.get(`/api/intelligence/alerts?limit=${limit}`); return r.data
}
export async function triggerMonitorScan(): Promise<unknown> {
  const r = await api.post('/api/intelligence/monitor/scan'); return r.data
}
export async function fetchLLMUsage(): Promise<V5LLMUsage> {
  const r = await api.get('/api/intelligence/claude-usage'); return r.data
}
export function clearAllCache() { cache.clear() }
export default api

// ── Subscription API ──────────────────────────────────────────────────────────
export interface SubscriptionStatus {
  tier: 'free' | 'pro' | 'team'
  expires_at: string | null
  is_active: boolean
}

export async function fetchSubscriptionStatus(): Promise<SubscriptionStatus> {
  const r = await api.get('/api/subscription/status')
  return r.data
}

export async function fetchSubscriptionPlans(): Promise<{ plans: any[]; razorpay_key_id: string }> {
  const r = await api.get('/api/subscription/plans')
  return r.data
}

export async function createSubscriptionOrder(tier: string): Promise<{ order_id: string; amount_paise: number; currency: string; key_id: string }> {
  const r = await api.post('/api/subscription/create-order', { tier })
  return r.data
}

export async function verifySubscriptionPayment(payload: {
  razorpay_order_id: string
  razorpay_payment_id: string
  razorpay_signature: string
}): Promise<{ success: boolean; tier: string; expires_at: string; message: string }> {
  const r = await api.post('/api/subscription/verify-payment', payload)
  return r.data
}
