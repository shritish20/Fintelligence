import { useState, useEffect } from 'react'
import { useApp } from '@/context/AppContext'

const MODULES = [
  { label: 'VOLGUARD', sub: 'Options Intelligence',  color: 'text-neon-green',    dot: 'bg-neon-green',    status: 'LIVE' },
  { label: 'MF INTEL', sub: 'Mutual Fund Analysis',  color: 'text-electric-blue', dot: 'bg-electric-blue', status: 'LIVE' },
  { label: 'EQUITY',   sub: 'Stock Intelligence',    color: 'text-electric-blue', dot: 'bg-electric-blue', status: 'LIVE' },
  { label: 'TAX',      sub: 'Taxation Intelligence', color: 'text-yellow-400',    dot: 'bg-yellow-400',    status: 'LIVE' },
  { label: 'MACRO',    sub: 'Macro & G-Sec Context', color: 'text-electric-blue', dot: 'bg-electric-blue', status: 'IN VOLGUARD' },
]

const API_BASE = (import.meta.env.VITE_API_BASE as string || '').trim()

type Screen = 'login' | 'register'

export function LoginScreen() {
  const { login } = useApp()

  const [screen,   setScreen]   = useState<Screen>('login')
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [err,      setErr]      = useState('')
  const [time,     setTime]     = useState('')

  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    }))
    tick()
    const iv = setInterval(tick, 1000)
    return () => clearInterval(iv)
  }, [])

  const clearErr = () => setErr('')

  async function handleAuth() {
    setErr('')
    if (!email.trim() || !email.includes('@')) { setErr('Enter a valid email address'); return }
    if (password.length < 8) { setErr('Password must be at least 8 characters'); return }

    setLoading(true)
    try {
      const endpoint = screen === 'login' ? '/api/auth/login' : '/api/auth/register'
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const data = await res.json()
      if (!res.ok) { setErr(data.detail || 'Authentication failed'); return }

      // ✅ Go straight to dashboard — no mandatory Upstox step
      // Broker token is set later inside the Volguard module via sessionStorage (Option B)
      login({
        userId:           data.user_id,
        email:            data.email,
        isAdmin:          data.is_admin ?? false,
        subscriptionTier: data.subscription_tier ?? 'free',
        accessToken:      data.access_token,
      })
    } catch {
      setErr('Could not reach server — check your connection')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-black bg-radial-subtle flex items-center justify-center p-4">
      <div className="w-full max-w-2xl space-y-6">

        {/* Header */}
        <div className="text-center space-y-3">
          <div className="flex items-center justify-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-electric-blue/20 border border-electric-blue/40 flex items-center justify-center">
              <span className="text-electric-blue text-sm font-black">FI</span>
            </div>
          </div>
          <h1 className="text-4xl font-black tracking-widest uppercase text-white">
            Fint<span className="text-electric-blue">elligence</span>
          </h1>
          <p className="text-xs text-muted-foreground font-mono-data tracking-widest">
            FINANCIAL INTELLIGENCE OPERATING SYSTEM
          </p>
          <div className="flex items-center justify-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-neon-green pulse-green" />
            <span className="text-[10px] text-neon-green font-mono-data">SYSTEM ONLINE · {time} IST</span>
          </div>
        </div>

        {/* Module strip */}
        <div className="grid grid-cols-5 gap-2">
          {MODULES.map(m => (
            <div key={m.label} className="glass-card p-3 text-center space-y-1.5">
              <div className="flex items-center justify-center gap-1">
                <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
              </div>
              <p className={`text-[10px] font-bold tracking-wider ${m.color}`}>{m.label}</p>
              <p className="text-[8px] text-muted-foreground leading-tight">{m.sub}</p>
              <p className="text-[8px] font-mono-data text-muted-foreground opacity-60">{m.status}</p>
            </div>
          ))}
        </div>

        {/* Auth card */}
        <div className="glass-card p-8 space-y-6">
          {/* Tab toggle */}
          <div className="flex bg-secondary rounded-lg p-1 gap-1">
            {(['login', 'register'] as const).map(s => (
              <button key={s} onClick={() => { setScreen(s); clearErr() }}
                className={`flex-1 py-2 rounded-md text-xs font-bold uppercase tracking-widest transition-all ${
                  screen === s
                    ? 'bg-electric-blue text-white'
                    : 'text-muted-foreground hover:text-foreground'
                }`}>
                {s === 'login' ? 'Sign In' : 'Create Account'}
              </button>
            ))}
          </div>

          {err && (
            <div className="bg-signal-red/10 border border-signal-red/30 rounded p-3">
              <p className="text-signal-red text-xs">{err}</p>
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-[10px] text-header block">EMAIL ADDRESS</label>
              <input
                type="email"
                value={email}
                onChange={e => { setEmail(e.target.value); clearErr() }}
                onKeyDown={e => e.key === 'Enter' && handleAuth()}
                placeholder="you@example.com"
                autoComplete="email"
                className="w-full bg-secondary border border-white/10 rounded px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-electric-blue"
              />
            </div>

            <div className="space-y-2">
              <label className="text-[10px] text-header block">PASSWORD</label>
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => { setPassword(e.target.value); clearErr() }}
                  onKeyDown={e => e.key === 'Enter' && handleAuth()}
                  placeholder={screen === 'register' ? 'At least 8 characters' : 'Your password'}
                  autoComplete={screen === 'login' ? 'current-password' : 'new-password'}
                  className="w-full bg-secondary border border-white/10 rounded px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-electric-blue"
                />
                <button type="button" onClick={() => setShowPass(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs">
                  {showPass ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>
          </div>

          <button onClick={handleAuth} disabled={loading}
            className="w-full bg-electric-blue hover:bg-electric-blue/80 disabled:opacity-50 text-white font-bold uppercase tracking-widest py-2.5 rounded-md transition-all text-sm">
            {loading ? 'Please wait...' : screen === 'login' ? 'Sign In →' : 'Create Account →'}
          </button>

          <p className="text-center text-[10px] text-muted-foreground">
            {screen === 'login'
              ? "Don't have an account? "
              : 'Already have an account? '}
            <button onClick={() => { setScreen(screen === 'login' ? 'register' : 'login'); clearErr() }}
              className="text-electric-blue hover:underline">
              {screen === 'login' ? 'Create one' : 'Sign in'}
            </button>
          </p>
        </div>

        <p className="text-center text-[10px] text-muted-foreground">
          Five modules · One system · Zero compromises
        </p>
      </div>
    </div>
  )
}
