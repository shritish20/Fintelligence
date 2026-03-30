import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { FundBrief } from '../lib/types'
import { fmtCr, fmt, categoryColor } from '../lib/utils'

interface Props {
  brief: FundBrief | null; loading: boolean; statusMsg: string
  onAnalyse: (withRegime: boolean) => void; onCompare: () => void; onClear: () => void
}

const CONVICTION_STYLE: Record<string, { border: string; bg: string; text: string; label: string }> = {
  'STRONG BUY':  { border: 'border-neon-green/50', bg: 'bg-neon-green/10',    text: 'text-neon-green',    label: 'STRONG BUY'  },
  'BUY':         { border: 'border-neon-green/30', bg: 'bg-neon-green/5',     text: 'text-neon-green',    label: 'BUY'         },
  'HOLD':        { border: 'border-yellow-400/40', bg: 'bg-yellow-400/5',     text: 'text-yellow-400',    label: 'HOLD'        },
  'AVOID':       { border: 'border-signal-red/40', bg: 'bg-signal-red/5',     text: 'text-signal-red',    label: 'AVOID'       },
  'STRONG AVOID':{ border: 'border-signal-red/50', bg: 'bg-signal-red/10',    text: 'text-signal-red',    label: 'STRONG AVOID'},
  'INSUFFICIENT_DATA':{ border: 'border-white/20', bg: 'bg-secondary/30',     text: 'text-muted-foreground', label: 'NO DATA' },
}

function Row({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between items-baseline gap-2 py-1 border-b border-white/5 last:border-0">
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide shrink-0">{label}</span>
      <span className={`text-sm font-bold text-foreground text-right ${mono ? 'font-mono-data' : ''}`}>{value}</span>
    </div>
  )
}

export function LeftPanel({ brief, loading, statusMsg, onAnalyse, onCompare, onClear }: Props) {
  const [withRegime, setWithRegime] = useState(false)
  const nav = useNavigate()

  // Loading skeleton
  if (loading && !brief) {
    return (
      <div className="w-72 shrink-0">
        <div className="glass-card intel-glow p-5 sticky top-16 space-y-4">
          <div className="space-y-2">
            <div className="skeleton h-4 w-3/4 rounded" />
            <div className="skeleton h-3 w-1/2 rounded" />
            <div className="skeleton h-3 w-1/3 rounded" />
          </div>
          <div className="skeleton h-10 w-full rounded-lg" />
          {[1,2,3,4].map(i => <div key={i} className="skeleton h-8 w-full rounded" />)}
          {statusMsg && (
            <div className="flex items-center gap-2 pt-1">
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
            <span className="text-muted-foreground text-lg">◆</span>
          </div>
          <p className="text-xs text-muted-foreground">Select a fund to begin analysis</p>
          <button onClick={() => nav('/mf')} className="mt-3 text-[10px] text-electric-blue hover:underline">← Back to search</button>
        </div>
      </div>
    )
  }

  if (brief.status === 'error') {
    return (
      <div className="w-72 shrink-0">
        <div className="glass-card veto-glow p-5 sticky top-16">
          <p className="text-header text-xs mb-2">Analysis Failed</p>
          <p className="text-xs text-signal-red leading-relaxed">{brief.error}</p>
          <button onClick={onClear} className="mt-4 w-full py-2 text-xs text-muted-foreground border border-white/15 rounded-lg hover:border-electric-blue/40 transition-colors">
            Retry
          </button>
        </div>
      </div>
    )
  }

  const conv = brief.conviction ?? 'HOLD'
  const cs = CONVICTION_STYLE[conv] ?? CONVICTION_STYLE['HOLD']
  const meta = brief.metadata || {}

  return (
    <div className="w-72 shrink-0">
      <div className="glass-card intel-glow p-5 sticky top-16 space-y-4">

        {/* Identity */}
        <div>
          <h2 className="text-sm font-bold text-foreground leading-tight mb-1">{brief.scheme_name}</h2>
          <p className="text-[11px] text-muted-foreground">{brief.fund_house}</p>
          {brief.category && (
            <span className={`inline-block mt-2 text-[9px] px-2 py-0.5 rounded-full border font-bold uppercase tracking-wider ${categoryColor(brief.category)}`}>
              {brief.category}
            </span>
          )}
        </div>

        {/* Conviction badge */}
        <div className={`rounded-lg px-3 py-2.5 border ${cs.border} ${cs.bg}`}>
          <p className={`font-black text-base tracking-widest ${cs.text}`}>{cs.label}</p>
          {brief.conviction_reason && (
            <p className="text-[10px] text-muted-foreground mt-1 leading-relaxed line-clamp-3">{brief.conviction_reason}</p>
          )}
        </div>

        <div className="border-t border-white/10" />

        {/* Key stats */}
        <div>
          <Row label="AUM" value={fmtCr(meta.aum_crore)} />
          <Row label="Expense Ratio" value={meta.expense_ratio ? `${meta.expense_ratio}%` : 'N/A'} />
          <Row label="SIP XIRR 3Y" value={fmt(brief.metrics?.sip_xirr)} />
          <Row label="Sharpe 3Y" value={brief.metrics?.sharpe?.toFixed(2) ?? 'N/A'} />
          <Row label="Max Drawdown" value={brief.metrics?.max_drawdown?.max_drawdown_pct ? `${brief.metrics.max_drawdown.max_drawdown_pct}%` : 'N/A'} />
          {meta.fund_manager && <Row label="Manager" value={meta.fund_manager} mono={false} />}
          <Row label="As Of" value={brief.metrics?.as_of ?? 'N/A'} />
        </div>

        <div className="border-t border-white/10" />

        {/* Analyse button */}
        <div className="space-y-2">
          <button
            onClick={() => onAnalyse(withRegime)}
            disabled={loading}
            className="w-full py-2.5 bg-electric-blue/20 border border-electric-blue/40 text-electric-blue
              text-[11px] font-black tracking-widest uppercase rounded-lg
              hover:bg-electric-blue/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-3 h-3 border-2 border-electric-blue border-t-transparent rounded-full animate-spin" />
                {statusMsg || 'Analysing…'}
              </span>
            ) : 'Refresh Analysis'}
          </button>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={withRegime} onChange={e => setWithRegime(e.target.checked)} className="accent-electric-blue w-3 h-3" />
            <span className="text-[10px] text-muted-foreground">Include live regime context (+30s)</span>
          </label>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-4 pt-0.5">
          <button onClick={onCompare} className="text-[10px] text-muted-foreground hover:text-electric-blue transition-colors underline">Compare</button>
          <button onClick={onClear} className="text-[10px] text-muted-foreground hover:text-foreground transition-colors underline">Clear cache</button>
          <button onClick={() => nav('/mf')} className="text-[10px] text-muted-foreground hover:text-foreground transition-colors underline ml-auto">← Back</button>
        </div>

        {brief.cached_at && (
          <p className="text-[9px] text-muted-foreground opacity-40">
            {new Date(brief.cached_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
          </p>
        )}
      </div>
    </div>
  )
}
