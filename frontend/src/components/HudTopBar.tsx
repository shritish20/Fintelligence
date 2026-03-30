import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useApp } from '@/context/AppContext'

const TONE_COLOR: Record<string, string> = {
  CLEAR:            'text-neon-green',
  CAUTIOUS_NEUTRAL: 'text-yellow-400',
  CAUTIOUS:         'text-orange-400',
  RISK_OFF:         'text-signal-red',
  MIXED:            'text-muted-foreground',
  UNKNOWN:          'text-muted-foreground',
}
const TONE_DOT: Record<string, string> = {
  CLEAR:            'bg-neon-green',
  CAUTIOUS_NEUTRAL: 'bg-yellow-400',
  CAUTIOUS:         'bg-orange-400',
  RISK_OFF:         'bg-signal-red',
  MIXED:            'bg-muted-foreground',
  UNKNOWN:          'bg-muted-foreground',
}

const MODULES = [
  { path: '/volguard',     label: 'VOLGUARD',     live: true  },
  { path: '/mf',           label: 'MF INTEL',     live: false },
  { path: '/equity',       label: 'EQUITY',       live: false },
  { path: '/tax',          label: 'TAX',          live: false },
  { path: '/subscription', label: 'PLANS',        live: false },
]

interface LiveData {
  spot:       number | null
  vix:        number | null
  regimeScore:number | null
  tone:       string
  briefReady: boolean
  aiOnline:   boolean
}

export function HudTopBar({ onDisconnect }: { onDisconnect: () => void }) {
  const nav      = useNavigate()
  const location = useLocation()
  const { regime, setRegime, user, logout } = useApp()

  const handleDisconnect = () => { logout(); onDisconnect() }

  const [time,     setTime]     = useState('')
  const [live,     setLive]     = useState<LiveData>({ spot: null, vix: null, regimeScore: null, tone: 'UNKNOWN', briefReady: false, aiOnline: false })
  const [prevSpot, setPrevSpot] = useState<number | null>(null)

  // IST clock
  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }))
    tick()
    const iv = setInterval(tick, 1000)
    return () => clearInterval(iv)
  }, [])

  // Pull live data from Volguard backend (best-effort — other modules work fine without it)
  useEffect(() => {
    const fetch = async () => {
      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (user?.accessToken) headers['Authorization'] = `Bearer ${user.accessToken}`

        const [priceRes, statusRes] = await Promise.allSettled([
          window.fetch('/api/market/bulk-last-price?instruments=NSE_INDEX%7CNifty+50%2CNSE_INDEX%7CIndia+VIX', { headers }),
          window.fetch('/api/v5/status', { headers }),
        ])

        if (priceRes.status === 'fulfilled' && priceRes.value.ok) {
          const p = await priceRes.value.json()
          setPrevSpot(live.spot)
          const prices = p?.prices ?? p
          const spot = prices['NSE_INDEX|Nifty 50'] ?? null
          const vix  = prices['NSE_INDEX|India VIX'] ?? null
          setLive(prev => ({ ...prev, spot, vix }))
          if (vix) setRegime({ vix })
        }

        if (statusRes.status === 'fulfilled' && statusRes.value.ok) {
          const s = await statusRes.value.json()
          const tone       = s?.morning_brief?.global_tone ?? 'UNKNOWN'
          const briefReady = s?.morning_brief?.status === 'AVAILABLE'
          const aiOnline   = s?.intelligence_layer === 'ONLINE'
          setLive(prev => ({ ...prev, tone, briefReady, aiOnline }))
          setRegime({ label: tone, briefReady })
        }
      } catch {
        // Volguard backend unreachable — HUD still works for other modules
      }
    }
    fetch()
    const iv = setInterval(fetch, 15000)
    return () => clearInterval(iv)
  }, [])

  const spotDir = prevSpot && live.spot ? (live.spot > prevSpot ? 'up' : live.spot < prevSpot ? 'down' : null) : null
  const tone    = live.tone ?? regime.label ?? 'UNKNOWN'
  const activeModule = MODULES.find(m => location.pathname.startsWith(m.path))

  const isHome = location.pathname === '/' || location.pathname === '/home'

  return (
    <header className="sticky top-0 z-50 border-b border-white/10 backdrop-blur-md bg-black/85">
      <div className="max-w-[1800px] mx-auto px-4 h-12 flex items-center gap-4">

        {/* Wordmark → home */}
        <button
          onClick={() => nav('/')}
          className="flex items-center gap-2 shrink-0 group"
        >
          <div className="w-6 h-6 rounded bg-electric-blue/20 border border-electric-blue/40 flex items-center justify-center group-hover:bg-electric-blue/30 transition-colors">
            <span className="text-electric-blue text-[9px] font-black">FI</span>
          </div>
          <span className="text-sm font-black tracking-widest uppercase text-foreground group-hover:text-electric-blue transition-colors">
            Fint<span className="text-electric-blue">elligence</span>
          </span>
        </button>

        <div className="w-px h-4 bg-white/10 shrink-0" />

        {/* Module pills */}
        <nav className="flex items-center gap-1 shrink-0">
          {MODULES.map(m => {
            const active = location.pathname.startsWith(m.path)
            return (
              <button
                key={m.path}
                onClick={() => nav(m.path)}
                className={`relative flex items-center gap-1.5 px-3 py-1 text-[10px] font-semibold tracking-widest rounded transition-colors
                  ${active
                    ? 'bg-electric-blue/15 text-electric-blue border border-electric-blue/40'
                    : 'text-muted-foreground hover:text-foreground border border-transparent'}`}
              >
                {m.live && (
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${live.briefReady ? 'bg-neon-green pulse-green' : 'bg-yellow-400'}`} />
                )}
                {m.label}
              </button>
            )
          })}
        </nav>

        <div className="w-px h-4 bg-white/10 shrink-0" />

        {/* Live market data — center */}
        <div className="flex-1 flex items-center gap-5 text-xs font-mono-data overflow-hidden">
          {live.spot && (
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground text-[10px]">NIFTY</span>
              <span className={`font-bold tabular-nums ${spotDir === 'up' ? 'text-neon-green tick-up' : spotDir === 'down' ? 'text-signal-red tick-down' : 'text-foreground'}`}>
                {live.spot.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </span>
              {spotDir === 'up' && <span className="text-neon-green text-[8px]">▲</span>}
              {spotDir === 'down' && <span className="text-signal-red text-[8px]">▼</span>}
            </div>
          )}

          {live.vix && (
            <>
              <div className="w-px h-3 bg-white/10" />
              <div className="flex items-center gap-1.5">
                <span className="text-muted-foreground text-[10px]">VIX</span>
                <span className={`font-bold tabular-nums ${live.vix > 20 ? 'text-signal-red' : live.vix > 15 ? 'text-yellow-400' : 'text-neon-green'}`}>
                  {live.vix.toFixed(2)}
                </span>
              </div>
            </>
          )}

          {tone !== 'UNKNOWN' && (
            <>
              <div className="w-px h-3 bg-white/10" />
              <div className="flex items-center gap-1.5">
                <span className="text-muted-foreground text-[10px]">TONE</span>
                <div className={`w-1.5 h-1.5 rounded-full ${TONE_DOT[tone] ?? 'bg-muted-foreground'}`} />
                <span className={`font-bold text-[11px] ${TONE_COLOR[tone] ?? 'text-muted-foreground'}`}>{tone.replace('_', ' ')}</span>
              </div>
            </>
          )}

          {tone !== 'UNKNOWN' && (
            <>
              <div className="w-px h-3 bg-white/10 hidden lg:block" />
              <div className="hidden lg:flex items-center gap-1.5">
                <span className="text-muted-foreground text-[10px]">BRIEF</span>
                <span className={`flex items-center gap-1 text-[10px] font-bold ${live.briefReady ? 'text-neon-green' : 'text-yellow-400'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${live.briefReady ? 'bg-neon-green pulse-green' : 'bg-yellow-400'}`} />
                  {live.briefReady ? 'READY' : 'PENDING'}
                </span>
              </div>
            </>
          )}

          {/* Module breadcrumb */}
          {activeModule && (
            <>
              <div className="w-px h-3 bg-white/10 hidden xl:block" />
              <span className="hidden xl:block text-[10px] text-electric-blue/60 font-semibold tracking-widest">
                {activeModule.label}
              </span>
            </>
          )}
        </div>

        {/* Right: user + time + disconnect */}
        <div className="flex items-center gap-3 shrink-0">
          {user?.email && (
            <span className="font-mono-data text-[10px] text-muted-foreground hidden md:block truncate max-w-[140px]">{user.email}</span>
          )}
          <span className="font-mono-data text-[11px] text-muted-foreground hidden sm:block">{time} IST</span>
          <div className="w-px h-3 bg-white/10" />
          <button
            onClick={handleDisconnect}
            className="text-[10px] uppercase tracking-wider text-muted-foreground hover:text-signal-red transition-colors font-semibold border border-white/10 px-3 py-1.5 rounded hover:border-signal-red/50"
          >
            Sign Out
          </button>
        </div>

      </div>
    </header>
  )
}
