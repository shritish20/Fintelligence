import { useState, useEffect } from 'react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { WebSocketProvider } from '@/context/WebSocketContext'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { DashboardTab }    from './pages/DashboardTab'
import { LiveDeskTab }     from './pages/LiveDeskTab'
import { JournalTab }      from './pages/JournalTab'
import { IntelligenceTab } from './pages/IntelligenceTab'
import { SystemTab }       from './pages/SystemTab'
import { useApp }          from '@/context/AppContext'
import { activateUpstoxToken } from '@/lib/api'

const TABS = [
  { value: 'intel',    label: 'V5 INTEL'  },
  { value: 'market',   label: 'MARKET'    },
  { value: 'position', label: 'POSITIONS' },
  { value: 'log',      label: 'LOG'       },
  { value: 'system',   label: 'SYSTEM'    },
]

export function VolguardModule() {
  const { upstoxToken, setUpstoxToken } = useApp()
  const [tokenInput,  setTokenInput]  = useState('')
  const [tokenSaving, setTokenSaving] = useState(false)
  const [tokenErr,    setTokenErr]    = useState('')
  const [showTokenBar, setShowTokenBar] = useState(!upstoxToken)

  // Show token bar again if token is cleared (e.g. new tab, morning reset)
  useEffect(() => {
    if (!upstoxToken) setShowTokenBar(true)
  }, [upstoxToken])

  async function handleActivateToken() {
    const token = tokenInput.trim()
    if (!token || token.length < 20) { setTokenErr('Token too short — paste the full Upstox token'); return }
    setTokenSaving(true)
    setTokenErr('')
    try {
      // 1. Store in sessionStorage via context (Option B — never touches server DB)
      setUpstoxToken(token)
      // 2. Activate in-memory SDK on server for this session
      await activateUpstoxToken(token)
      setTokenInput('')
      setShowTokenBar(false)
    } catch (e: any) {
      // Token is already in sessionStorage — trading features work client-side
      // Server activation failure is non-fatal for read-only intelligence features
      setTokenErr(e?.response?.data?.detail || 'Server activation failed — live orders may not work')
    } finally {
      setTokenSaving(false)
    }
  }

  return (
    <WebSocketProvider>
      <div className="max-w-[1800px] mx-auto px-4 py-4">

        {/* Token Banner — shown when no broker token in session */}
        {showTokenBar && !upstoxToken && (
          <div className="mb-4 glass-card border border-yellow-400/30 bg-yellow-400/5 rounded-lg px-5 py-3">
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-yellow-400">Connect Trading Terminal</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Intelligence layer is live. Paste your daily Upstox token to unlock live positions, P&amp;L, and order execution.
                  <span className="text-yellow-400/70 ml-1">Your token never leaves this device.</span>
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <input
                  type="password"
                  value={tokenInput}
                  onChange={e => { setTokenInput(e.target.value); setTokenErr('') }}
                  onKeyDown={e => e.key === 'Enter' && handleActivateToken()}
                  placeholder="Paste daily Upstox token..."
                  className="bg-secondary border border-white/10 rounded px-3 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-yellow-400 w-72"
                />
                <button
                  onClick={handleActivateToken}
                  disabled={tokenSaving}
                  className="bg-yellow-400 hover:bg-yellow-300 disabled:opacity-50 text-black font-bold uppercase tracking-wider px-4 py-1.5 rounded text-xs transition-colors"
                >
                  {tokenSaving ? 'Connecting...' : 'Connect'}
                </button>
                <button
                  onClick={() => setShowTokenBar(false)}
                  className="text-muted-foreground hover:text-foreground text-xs px-2"
                >
                  ✕
                </button>
              </div>
            </div>
            {tokenErr && <p className="text-signal-red text-xs mt-2">{tokenErr}</p>}
          </div>
        )}

        {/* Token active badge */}
        {upstoxToken && (
          <div className="mb-3 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-neon-green bg-neon-green/10 border border-neon-green/20 rounded px-2 py-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-neon-green animate-pulse" />
              BROKER CONNECTED · SESSION ONLY
            </span>
            <button
              onClick={() => { setShowTokenBar(true) }}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              change
            </button>
          </div>
        )}

        <Tabs defaultValue="intel">
          <TabsList className="w-full justify-start bg-card border border-white/10 mb-6 h-10">
            {TABS.map(t => (
              <TabsTrigger
                key={t.value}
                value={t.value}
                className="text-[10px] uppercase tracking-widest text-muted-foreground data-[state=active]:text-electric-blue data-[state=active]:bg-secondary font-semibold h-8 px-4"
              >
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <ErrorBoundary><TabsContent value="intel"><IntelligenceTab /></TabsContent></ErrorBoundary>
          <ErrorBoundary><TabsContent value="market"><DashboardTab /></TabsContent></ErrorBoundary>
          <ErrorBoundary><TabsContent value="position"><LiveDeskTab /></TabsContent></ErrorBoundary>
          <ErrorBoundary><TabsContent value="log"><JournalTab /></TabsContent></ErrorBoundary>
          <ErrorBoundary><TabsContent value="system"><SystemTab /></TabsContent></ErrorBoundary>
        </Tabs>
      </div>
    </WebSocketProvider>
  )
}
