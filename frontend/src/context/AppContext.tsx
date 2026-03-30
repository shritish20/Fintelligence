import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

export type Module = 'home' | 'volguard' | 'mf' | 'equity' | 'tax'

interface RegimeState {
  score: number | null
  label: string
  vix: number | null
  fiiDirection: 'BUYING' | 'SELLING' | 'NEUTRAL' | null
  briefReady: boolean
  lastUpdated: Date | null
}

export interface AuthUser {
  userId: number
  email: string
  isAdmin: boolean
  subscriptionTier: 'free' | 'pro' | 'team'
  accessToken: string
  // NOTE (Option B): upstoxToken is NOT stored in localStorage or on the server.
  // It lives only in sessionStorage — cleared when the browser tab closes.
  // Never put it in the user object that gets persisted to localStorage.
}

interface AppContextType {
  isAuthenticated: boolean
  user: AuthUser | null
  login: (user: AuthUser) => void
  logout: () => void
  // Broker token — sessionStorage only, never touches server or localStorage
  upstoxToken: string | null
  setUpstoxToken: (token: string) => void
  clearUpstoxToken: () => void
  regime: RegimeState
  setRegime: (r: Partial<RegimeState>) => void
  activeModule: Module
  setActiveModule: (m: Module) => void
}

const AppContext = createContext<AppContextType | null>(null)

const REGIME_DEFAULTS: RegimeState = {
  score: null, label: 'UNKNOWN', vix: null,
  fiiDirection: null, briefReady: false, lastUpdated: null,
}

const AUTH_STORAGE_KEY    = 'fintelligence_user'
const UPSTOX_SESSION_KEY  = 'fintelligence_upstox_token'  // sessionStorage only

function loadStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    if (!raw) return null
    const u = JSON.parse(raw) as AuthUser
    if (!u.accessToken || !u.userId) return null
    // Ensure legacy objects with upstoxToken field are stripped
    const { ...clean } = u as any
    delete clean.upstoxToken
    delete clean.hasUpstoxToken
    return clean as AuthUser
  } catch { return null }
}

function loadSessionToken(): string | null {
  try {
    return sessionStorage.getItem(UPSTOX_SESSION_KEY) || null
  } catch { return null }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser]                 = useState<AuthUser | null>(loadStoredUser)
  const [upstoxToken, setUpstoxState]   = useState<string | null>(loadSessionToken)
  const [regime, setRegimeState]        = useState<RegimeState>(REGIME_DEFAULTS)
  const [activeModule, setActiveModule] = useState<Module>('home')

  useEffect(() => {
    const handler = () => {
      localStorage.removeItem(AUTH_STORAGE_KEY)
      // Also clear session token on auth logout
      sessionStorage.removeItem(UPSTOX_SESSION_KEY)
      setUser(null)
      setUpstoxState(null)
      setRegimeState(REGIME_DEFAULTS)
    }
    window.addEventListener('auth:logout', handler)
    return () => window.removeEventListener('auth:logout', handler)
  }, [])

  const login = (u: AuthUser) => {
    // Strip any accidental upstox token from the user object before persisting
    const { ...safe } = u as any
    delete safe.upstoxToken
    delete safe.hasUpstoxToken
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(safe))
    setUser(safe as AuthUser)
  }

  const logout = () => {
    localStorage.removeItem(AUTH_STORAGE_KEY)
    sessionStorage.removeItem(UPSTOX_SESSION_KEY)
    setUser(null)
    setUpstoxState(null)
    setRegimeState(REGIME_DEFAULTS)
  }

  // Option B: broker token lives in sessionStorage only.
  // Cleared automatically when the tab closes. Never touches localStorage or server DB.
  const setUpstoxToken = (token: string) => {
    sessionStorage.setItem(UPSTOX_SESSION_KEY, token)
    setUpstoxState(token)
  }

  const clearUpstoxToken = () => {
    sessionStorage.removeItem(UPSTOX_SESSION_KEY)
    setUpstoxState(null)
  }

  const setRegime = (updates: Partial<RegimeState>) =>
    setRegimeState(prev => ({ ...prev, ...updates, lastUpdated: new Date() }))

  return (
    <AppContext.Provider value={{
      isAuthenticated: !!user,
      user,
      login,
      logout,
      upstoxToken,
      setUpstoxToken,
      clearUpstoxToken,
      regime,
      setRegime,
      activeModule,
      setActiveModule,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
