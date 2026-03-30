import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '@/context/AppContext'
import { fetchV5Status, fetchDashboard } from '@/lib/api'

const TONE_COLOR: Record<string, string> = {
  CLEAR: 'text-neon-green', CAUTIOUS_NEUTRAL: 'text-yellow-400',
  CAUTIOUS: 'text-orange-400', RISK_OFF: 'text-signal-red',
  MIXED: 'text-muted-foreground', UNKNOWN: 'text-muted-foreground',
}
const TONE_BG: Record<string, string> = {
  CLEAR: 'border-neon-green/40 bg-neon-green/5',
  CAUTIOUS_NEUTRAL: 'border-yellow-400/40 bg-yellow-400/5',
  CAUTIOUS: 'border-orange-400/40 bg-orange-400/5',
  RISK_OFF: 'border-signal-red/40 bg-signal-red/5',
  MIXED: 'border-white/10 bg-secondary/30', UNKNOWN: 'border-white/10 bg-secondary/30',
}

function Chip({ label, value, color = 'text-foreground' }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">{label}</span>
      <span className={`font-mono-data text-sm font-bold tabular-nums ${color}`}>{value}</span>
    </div>
  )
}

function FlowArrow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 px-5 py-1.5">
      <div className="w-px h-5 bg-white/10 ml-10 shrink-0" />
      <span className="text-[9px] text-muted-foreground font-mono-data tracking-wider">{label}</span>
    </div>
  )
}

function LayerCard({ num, title, sub, onClick, children, glowClass = '', badge }: {
  num: string; title: string; sub: string; onClick: () => void
  children: React.ReactNode; glowClass?: string; badge?: React.ReactNode
}) {
  return (
    <div onClick={onClick} className={`glass-card border border-white/10 rounded-lg overflow-hidden cursor-pointer hover:border-electric-blue/30 transition-all group ${glowClass}`}>
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-white/5 bg-white/[0.02]">
        <div className="flex items-center gap-3">
          <span className="text-[9px] font-black text-muted-foreground font-mono-data bg-secondary border border-white/10 px-2 py-0.5 rounded tracking-widest">{num}</span>
          <div className="flex items-baseline gap-2">
            <span className="text-xs font-bold text-foreground tracking-wide">{title}</span>
            <span className="text-[10px] text-muted-foreground">· {sub}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {badge}
          <span className="text-[10px] text-electric-blue font-semibold tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">OPEN →</span>
        </div>
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  )
}

export function HomePage() {
  const nav = useNavigate()
  const { regime } = useApp()
  const [time, setTime] = useState('')
  const [vol, setVol] = useState<{ tone: string; score: number | null; strategy: string | null; vix: number | null; ivp: number | null; vov: number | null; briefReady: boolean }>({
    tone: 'UNKNOWN', score: null, strategy: null, vix: null, ivp: null, vov: null, briefReady: false,
  })

  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false }))
    tick(); const iv = setInterval(tick, 30000); return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        const [s, d] = await Promise.allSettled([fetchV5Status(), fetchDashboard()])
        let tone = 'UNKNOWN', briefReady = false, score: number | null = null
        let strategy: string | null = null, vix: number | null = null, ivp: number | null = null, vov: number | null = null
        if (s.status === 'fulfilled') { tone = s.value.morning_brief?.global_tone ?? 'UNKNOWN'; briefReady = s.value.morning_brief?.status === 'AVAILABLE' }
        if (d.status === 'fulfilled') {
          const dd = d.value; score = dd.regime_scores?.weekly?.composite?.score ?? null
          strategy = dd.mandates?.weekly?.strategy ?? null
          vix = dd.volatility_analysis?.vix ?? null; ivp = dd.volatility_analysis?.ivp_1y ?? null
          vov = dd.volatility_analysis?.vov_zscore ?? null
        }
        setVol({ tone, briefReady, score, strategy, vix, ivp, vov })
      } catch { setVol(prev => ({ ...prev, tone: 'UNKNOWN' })) }
    }; load()
  }, [])

  const tone = vol.tone !== 'UNKNOWN' ? vol.tone : (regime.label ?? 'UNKNOWN')
  const tColor = TONE_COLOR[tone] ?? 'text-muted-foreground'
  const tBg = TONE_BG[tone] ?? 'border-white/10'
  const isVeto = tone === 'RISK_OFF' || (vol.score !== null && vol.score < 3)
  const isGo = tone === 'CLEAR' || (vol.score !== null && vol.score >= 6.5)
  const glow = isVeto ? 'veto-glow' : isGo ? 'clear-glow' : vol.briefReady ? 'intel-glow' : ''

  return (
    <div className="max-w-[960px] mx-auto px-4 py-8">
      <div className="flex items-start justify-between mb-7">
        <div>
          <p className="text-[9px] font-black text-muted-foreground tracking-[0.22em] uppercase mb-1">YOUR CAPITAL ARCHITECTURE</p>
          <p className="text-sm font-medium text-foreground">Four layers. One compounding machine. <span className="text-muted-foreground">Every rupee doing two jobs.</span></p>
        </div>
        <span className="font-mono-data text-[11px] text-muted-foreground shrink-0">{time} IST</span>
      </div>

      <LayerCard num="LAYER 01" title="GOVERNMENT SECURITIES" sub="Foundation · Pledged as margin collateral" onClick={() => nav('/volguard')}>
        <div className="flex items-center gap-8 flex-wrap">
          <Chip label="Capital" value="₹10,00,000" />
          <Chip label="Margin Released" value="₹9,00,000" color="text-neon-green" />
          <Chip label="Haircut" value="90% of face value" color="text-electric-blue" />
          <Chip label="Yield" value="~7.2 – 7.3%" color="text-yellow-400" />
          <div className="flex-1 text-right"><button onClick={e => { e.stopPropagation(); nav('/volguard') }} className="text-[10px] text-electric-blue hover:underline font-semibold">MACRO SIGNALS IN VOLGUARD →</button></div>
        </div>
      </LayerCard>

      <FlowArrow label="releases ₹9,00,000 margin for overnight option selling" />

      <LayerCard num="LAYER 02" title="OPTIONS ENGINE" sub="Income engine · Nifty premium selling" onClick={() => nav('/volguard')} glowClass={glow}
        badge={tone !== 'UNKNOWN' ? <span className={`text-[9px] font-black tracking-widest px-2 py-0.5 rounded border ${tBg} ${tColor}`}>{tone.replace('_', ' ')}</span> : undefined}>
        {vol.score !== null ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-700 ${isVeto ? 'bg-signal-red' : isGo ? 'bg-neon-green' : 'bg-electric-blue'}`} style={{ width: `${((vol.score ?? 0) / 10) * 100}%` }} />
              </div>
              <span className={`font-mono-data text-base font-black tabular-nums ${tColor}`}>{vol.score.toFixed(1)}/10</span>
            </div>
            <div className="flex items-center gap-8 flex-wrap">
              {vol.vix !== null && <Chip label="VIX" value={vol.vix.toFixed(1)} color={vol.vix > 20 ? 'text-signal-red' : vol.vix > 15 ? 'text-yellow-400' : 'text-neon-green'} />}
              {vol.ivp !== null && <Chip label="IVP 1yr" value={`${vol.ivp.toFixed(0)}%`} color={vol.ivp > 75 ? 'text-neon-green' : vol.ivp < 25 ? 'text-signal-red' : 'text-foreground'} />}
              {vol.vov !== null && <Chip label="VoV Z" value={`${vol.vov.toFixed(1)}σ`} color={vol.vov >= 2.5 ? 'text-signal-red' : vol.vov >= 1.5 ? 'text-yellow-400' : 'text-neon-green'} />}
              {vol.strategy && <Chip label="Structure" value={vol.strategy.replace(/_/g, ' ')} color="text-electric-blue" />}
              <Chip label="Morning Brief" value={vol.briefReady ? '✓ READY' : 'PENDING'} color={vol.briefReady ? 'text-neon-green' : 'text-yellow-400'} />
              <div className="flex-1 text-right"><button onClick={e => { e.stopPropagation(); nav('/volguard') }} className="text-[10px] text-electric-blue hover:underline font-semibold">OPEN VOLGUARD →</button></div>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 border-2 border-electric-blue border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-muted-foreground">Loading Volguard status…</span>
            <button onClick={e => { e.stopPropagation(); nav('/volguard') }} className="ml-auto text-[10px] text-electric-blue hover:underline font-semibold">OPEN VOLGUARD →</button>
          </div>
        )}
      </LayerCard>

      <FlowArrow label="40% of premium → SIP · 20% withdrawn · 40% reserve" />

      <LayerCard num="LAYER 03" title="MUTUAL FUNDS" sub="Compounding engine · Funded by options income" onClick={() => nav('/mf')}>
        <div className="flex items-center gap-8 flex-wrap">
          <Chip label="Strategy" value="Equity + Hybrid" color="text-electric-blue" />
          <Chip label="SIP Amount" value="₹5,000 / month" color="text-neon-green" />
          <Chip label="Funded By" value="Options premium" color="text-yellow-400" />
          <Chip label="Horizon" value="10+ years" />
          <div className="flex-1 text-right"><button onClick={e => { e.stopPropagation(); nav('/mf') }} className="text-[10px] text-electric-blue hover:underline font-semibold">ANALYSE FUNDS →</button></div>
        </div>
      </LayerCard>

      <FlowArrow label="bluechip equity accumulated → future margin pledge pool" />

      <LayerCard num="LAYER 04" title="DIRECT EQUITY" sub="Long game · Future margin collateral" onClick={() => nav('/equity')}>
        <div className="flex items-center gap-8 flex-wrap">
          <Chip label="Core" value="3 bluechip + 3 large-cap" />
          <Chip label="Satellite" value="3 mid-cap + 1 high-conv" color="text-electric-blue" />
          <Chip label="Exit Thesis" value="Pledge to expand margin" color="text-yellow-400" />
          <div className="flex-1 text-right"><button onClick={e => { e.stopPropagation(); nav('/equity') }} className="text-[10px] text-electric-blue hover:underline font-semibold">ANALYSE STOCKS →</button></div>
        </div>
      </LayerCard>

      <div className="mt-4">
        <div onClick={() => nav('/tax')} className="glass-card border border-yellow-400/20 bg-yellow-400/[0.03] rounded-lg px-5 py-4 flex items-center justify-between cursor-pointer hover:border-yellow-400/40 transition-all group">
          <div className="flex items-center gap-8 flex-wrap">
            <div>
              <p className="text-[9px] text-yellow-400 uppercase tracking-[0.2em] font-black mb-1">₹  TAX INTELLIGENCE  ·  CROSS-LAYER</p>
              <p className="text-[11px] text-muted-foreground">F&O as business income · MF LTCG/STCG · Equity harvest · SGB redemption · Advance tax</p>
            </div>
            <Chip label="Rules Engine" value="Finance Act embedded" color="text-yellow-400" />
            <Chip label="Parses" value="Zerodha + CAMS" />
          </div>
          <span className="text-[10px] text-yellow-400 font-black tracking-widest opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-6">OPEN →</span>
        </div>
      </div>

      <p className="text-center text-[10px] text-muted-foreground mt-8 opacity-50">
        Click any layer to open the full intelligence module.
      </p>
    </div>
  )
}
