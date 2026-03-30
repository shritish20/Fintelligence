import { useNavigate } from 'react-router-dom'
import type { EquityBrief } from '../lib/types'

interface Props {
  brief: EquityBrief | null; loading: boolean; statusMsg: string
  onAnalyse: (force?: boolean) => void
}

const CONV_STYLE: Record<string, { border: string; bg: string; text: string }> = {
  'STRONG BUY':   { border: 'border-neon-green/50', bg: 'bg-neon-green/10',   text: 'text-neon-green'   },
  'BUY':          { border: 'border-neon-green/30', bg: 'bg-neon-green/5',    text: 'text-neon-green'   },
  'HOLD':         { border: 'border-yellow-400/40', bg: 'bg-yellow-400/5',    text: 'text-yellow-400'   },
  'AVOID':        { border: 'border-signal-red/40', bg: 'bg-signal-red/5',    text: 'text-signal-red'   },
  'STRONG AVOID': { border: 'border-signal-red/50', bg: 'bg-signal-red/10',   text: 'text-signal-red'   },
}

function Row({ label, value, color = 'text-foreground' }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between items-baseline py-1.5 border-b border-white/5 last:border-0 gap-2">
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide shrink-0">{label}</span>
      <span className={`font-mono-data text-sm font-bold tabular-nums text-right ${color}`}>{value}</span>
    </div>
  )
}

function fmtCr(v: number | null | undefined) {
  if (v == null) return 'N/A'
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L Cr`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}K Cr`
  return `₹${v.toFixed(0)} Cr`
}

export function LeftPanel({ brief, loading, statusMsg, onAnalyse }: Props) {
  const nav = useNavigate()

  if (loading && !brief) {
    return (
      <div className="w-72 shrink-0">
        <div className="glass-card intel-glow p-5 sticky top-16 space-y-4">
          <div className="space-y-2">
            <div className="skeleton h-5 w-3/4 rounded" />
            <div className="skeleton h-3 w-1/2 rounded" />
          </div>
          <div className="skeleton h-12 w-full rounded-lg" />
          {[1,2,3,4,5].map(i => <div key={i} className="skeleton h-8 w-full rounded" />)}
          {statusMsg && (
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 border-2 border-electric-blue border-t-transparent rounded-full animate-spin shrink-0" />
              <span className="text-[10px] text-electric-blue">{statusMsg}</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (!brief || brief.status === 'not_found') {
    return (
      <div className="w-72 shrink-0">
        <div className="glass-card p-5 sticky top-16 text-center">
          <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center mx-auto mb-3">
            <span className="text-muted-foreground text-lg">◈</span>
          </div>
          <p className="text-xs text-muted-foreground">Select a company to begin analysis</p>
          <button onClick={() => nav('/equity')} className="mt-3 text-[10px] text-electric-blue hover:underline">← Back to search</button>
        </div>
      </div>
    )
  }

  if (brief.status === 'error') {
    return (
      <div className="w-72 shrink-0">
        <div className="glass-card veto-glow p-5 sticky top-16">
          <p className="text-header text-xs mb-2">Analysis Failed</p>
          <p className="text-xs text-signal-red leading-relaxed">{(brief as any).error}</p>
          <button onClick={() => onAnalyse(true)} className="mt-4 w-full py-2 text-xs text-muted-foreground border border-white/15 rounded-lg hover:border-electric-blue/40 transition-colors">Retry</button>
        </div>
      </div>
    )
  }

  const conv = brief.conviction ?? 'HOLD'
  const cs = CONV_STYLE[conv] ?? CONV_STYLE['HOLD']
  const m = brief.metrics ?? {}

  return (
    <div className="w-72 shrink-0">
      <div className="glass-card intel-glow p-5 sticky top-16 space-y-4">

        {/* Identity */}
        <div>
          <h2 className="text-sm font-bold text-foreground leading-tight mb-1">{brief.company_name}</h2>
          <div className="flex items-center gap-2 flex-wrap">
            {brief.bse_code && <span className="text-[10px] font-mono-data text-muted-foreground">BSE {brief.bse_code}</span>}
            {brief.nse_symbol && <span className="text-[10px] font-mono-data text-muted-foreground">· NSE {brief.nse_symbol}</span>}
          </div>
          {brief.sector && (
            <span className="inline-block mt-2 text-[9px] px-2 py-0.5 rounded-full border border-electric-blue/30 bg-electric-blue/10 text-electric-blue font-bold uppercase tracking-wider">
              {brief.sector.replace(/_/g, ' ')}
            </span>
          )}
        </div>

        {/* Conviction */}
        <div className={`rounded-lg px-3 py-2.5 border ${cs.border} ${cs.bg}`}>
          <p className={`font-black text-base tracking-widest ${cs.text}`}>{conv}</p>
          {brief.conviction_reason && (
            <p className="text-[10px] text-muted-foreground mt-1 leading-relaxed line-clamp-3">{brief.conviction_reason}</p>
          )}
        </div>

        <div className="border-t border-white/10" />

        {/* Key metrics */}
        <div>
          {m.market_cap_cr != null && <Row label="Mkt Cap" value={fmtCr(m.market_cap_cr)} />}
          {m.current_price != null && <Row label="CMP" value={`₹${m.current_price.toLocaleString('en-IN')}`} />}
          {m.pe != null && <Row label="P/E" value={`${m.pe.toFixed(1)}x`} color={m.pe > 50 ? 'text-signal-red' : m.pe > 25 ? 'text-yellow-400' : 'text-neon-green'} />}
          {m.roce != null && <Row label="ROCE" value={`${m.roce.toFixed(1)}%`} color={m.roce > 20 ? 'text-neon-green' : m.roce < 10 ? 'text-signal-red' : 'text-foreground'} />}
          {m.pat != null && <Row label="PAT" value={fmtCr(m.pat)} />}
          {m.ebitda_margin != null && <Row label="EBITDA %" value={`${m.ebitda_margin.toFixed(1)}%`} color={m.ebitda_margin > 20 ? 'text-neon-green' : m.ebitda_margin < 10 ? 'text-signal-red' : 'text-foreground'} />}
          {brief.fy_year && <Row label="FY Year" value={`FY${brief.fy_year}`} />}
        </div>

        {/* Sector macro signals */}
        {brief.macro_signals && brief.macro_signals.length > 0 && (
          <>
            <div className="border-t border-white/10" />
            <div>
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold mb-2">SECTOR MACRO</p>
              <div className="space-y-1.5">
                {brief.macro_signals.slice(0, 2).map((s, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className={`text-[8px] font-black px-1 py-0.5 rounded border shrink-0 mt-0.5 ${s.signal === 'POSITIVE' ? 'text-neon-green border-neon-green/30 bg-neon-green/10' : s.signal === 'WARNING' ? 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10' : 'text-muted-foreground border-white/10 bg-secondary'}`}>
                      {s.signal === 'POSITIVE' ? '↑' : s.signal === 'WARNING' ? '⚠' : '→'}
                    </span>
                    <p className="text-[10px] text-muted-foreground leading-tight line-clamp-2">{s.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        <div className="border-t border-white/10" />

        {/* Actions */}
        <button onClick={() => onAnalyse(true)} disabled={loading}
          className="w-full py-2.5 bg-electric-blue/20 border border-electric-blue/40 text-electric-blue text-[11px] font-black tracking-widest uppercase rounded-lg hover:bg-electric-blue/30 disabled:opacity-50 transition-colors">
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-3 h-3 border-2 border-electric-blue border-t-transparent rounded-full animate-spin" />
              {statusMsg || 'Analysing…'}
            </span>
          ) : 'Refresh Analysis'}
        </button>

        <div className="flex items-center gap-4">
          <button onClick={() => nav('/equity')} className="text-[10px] text-muted-foreground hover:text-foreground transition-colors underline">← Back</button>
          {brief.generated_at && <p className="text-[9px] text-muted-foreground opacity-40 ml-auto">{new Date(brief.generated_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })}</p>}
        </div>
      </div>
    </div>
  )
}
