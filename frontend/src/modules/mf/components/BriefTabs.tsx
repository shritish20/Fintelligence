import { useState } from 'react'
import type { FundBrief, RollingReturns } from '../lib/types'
import { fmt, fmtSign, colorVal, fmtCr, categoryColor } from '../lib/utils'

// ── Shared primitives ─────────────────────────────────────────────────────────
function SH({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-4">
      <p className="text-header text-[10px]">{title}</p>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  )
}

function MRow({ label, value, cls = 'text-foreground' }: { label: string; value: string; cls?: string }) {
  return (
    <div className="flex justify-between items-baseline py-1.5 border-b border-white/5 last:border-0">
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
      <span className={`font-mono-data text-sm font-bold ${cls}`}>{value}</span>
    </div>
  )
}

function Bar({ label, pct, color = 'bg-electric-blue', valueLabel }: { label: string; pct: number | null | undefined; color?: string; valueLabel?: string }) {
  const p = Math.max(0, Math.min(100, pct ?? 0))
  return (
    <div className="flex items-center gap-3">
      <span className="text-[10px] text-muted-foreground w-8 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${p}%` }} />
      </div>
      <span className="font-mono-data text-xs font-bold text-foreground w-8 text-right shrink-0">{valueLabel ?? `${p.toFixed(0)}%`}</span>
    </div>
  )
}

// ── RETURNS TAB ───────────────────────────────────────────────────────────────
export function ReturnsTab({ brief }: { brief: FundBrief }) {
  const m = brief.metrics!
  const periods = ['1Y', '3Y', '5Y', 'Full'] as const

  return (
    <div className="space-y-4">
      {/* CAGR grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {periods.map(p => {
          const fv = m.cagr?.[p]
          const bv = m.benchmark_cagr?.[p]
          const alpha = fv != null && bv != null ? fv - bv : null
          return (
            <div key={p} className="glass-card p-4">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold mb-2">
                {p === 'Full' ? 'SINCE INCEPTION' : `${p} CAGR`}
              </p>
              <p className={`font-mono-data text-3xl font-black tabular-nums ${colorVal(fv)}`}>{fmt(fv)}</p>
              {bv != null && <p className="text-[10px] text-muted-foreground mt-1.5">Bench: <span className="font-mono-data">{fmt(bv)}</span></p>}
              {alpha != null && (
                <span className={`inline-block text-[9px] mt-2 px-2 py-0.5 rounded-full font-bold border
                  ${alpha >= 0 ? 'bg-neon-green/10 text-neon-green border-neon-green/30' : 'bg-signal-red/10 text-signal-red border-signal-red/30'}`}>
                  {fmtSign(alpha)} vs bench
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* SIP XIRR hero */}
      <div className="glass-card intel-glow p-6 text-center">
        <p className="text-[9px] text-muted-foreground uppercase tracking-[0.2em] font-bold mb-3">SIP XIRR — ₹10,000 / MONTH OVER 3 YEARS</p>
        <p className={`font-mono-data text-6xl font-black tabular-nums ${colorVal(m.sip_xirr)}`}>{fmt(m.sip_xirr)}</p>
        <p className="text-[11px] text-muted-foreground mt-2">What a systematic investor actually earned. Not NAV CAGR.</p>
      </div>

      {/* Rolling returns */}
      {(['rolling_1Y', 'rolling_3Y', 'rolling_5Y'] as const).map(key => {
        const rr = m[key] as RollingReturns | undefined
        if (!rr?.available) return null
        const window = key.replace('rolling_', '')
        return (
          <div key={key} className="glass-card p-5">
            <div className="flex justify-between items-center mb-4">
              <SH title={`${window} ROLLING RETURNS`} sub={`${rr.n_obs?.toLocaleString() ?? '—'} observations`} />
            </div>
            <div className="grid grid-cols-4 gap-4 mb-5">
              {[{ l: 'MIN', v: rr.min }, { l: 'MAX', v: rr.max }, { l: 'AVG', v: rr.mean }, { l: 'MEDIAN', v: rr.median }].map(({ l, v }) => (
                <div key={l} className="text-center">
                  <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">{l}</p>
                  <p className={`font-mono-data text-lg font-bold tabular-nums ${colorVal(v)}`}>{fmt(v)}</p>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              <Bar label=">0%" pct={rr.pct_positive} color="bg-neon-green" valueLabel={`${(rr.pct_positive ?? 0).toFixed(0)}%`} />
              <Bar label=">8%" pct={rr.pct_above_8} color="bg-electric-blue" valueLabel={`${(rr.pct_above_8 ?? 0).toFixed(0)}%`} />
              <Bar label=">12%" pct={rr.pct_above_12} color="bg-yellow-400/70" valueLabel={`${(rr.pct_above_12 ?? 0).toFixed(0)}%`} />
              {rr.pct_above_rf != null && <Bar label=">RF" pct={rr.pct_above_rf} color="bg-silver/50" valueLabel={`${rr.pct_above_rf.toFixed(0)}%`} />}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── RISK TAB ──────────────────────────────────────────────────────────────────
export function RiskTab({ brief }: { brief: FundBrief }) {
  const m = brief.metrics!
  const rows = [
    { label: 'STD DEV 3Y', value: m.std_dev != null ? `${m.std_dev.toFixed(1)}%` : 'N/A', color: m.std_dev == null ? '' : m.std_dev < 12 ? 'text-neon-green' : m.std_dev < 20 ? 'text-yellow-400' : 'text-signal-red', note: m.std_dev ? `Expect NAV swings of ±${m.std_dev.toFixed(0)}%/year` : '' },
    { label: 'SHARPE 3Y', value: m.sharpe?.toFixed(3) ?? 'N/A', color: m.sharpe == null ? '' : m.sharpe >= 1 ? 'text-neon-green' : m.sharpe >= 0.5 ? 'text-yellow-400' : 'text-signal-red', note: m.sharpe == null ? '' : m.sharpe >= 1 ? 'Excellent risk-adjusted return' : m.sharpe >= 0.5 ? 'Adequate' : 'Poor risk per unit' },
    { label: 'SORTINO 3Y', value: m.sortino?.toFixed(3) ?? 'N/A', color: m.sortino == null ? '' : m.sortino >= 1 ? 'text-neon-green' : m.sortino >= 0.5 ? 'text-yellow-400' : 'text-signal-red', note: m.sortino == null ? '' : m.sortino >= 1.5 ? 'Strong downside protection' : 'Moderate' },
    { label: 'MAX DRAWDOWN', value: m.max_drawdown?.max_drawdown_pct != null ? `${m.max_drawdown.max_drawdown_pct}%` : 'N/A', color: m.max_drawdown?.max_drawdown_pct != null ? (m.max_drawdown.max_drawdown_pct > -30 ? 'text-neon-green' : m.max_drawdown.max_drawdown_pct > -45 ? 'text-yellow-400' : 'text-signal-red') : '', note: m.max_drawdown?.recovery_date ? `Recovery: ${m.max_drawdown.recovery_date}` : '' },
  ]

  const { upside_capture, downside_capture } = m.capture_ratios ?? {}

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {rows.map(r => (
          <div key={r.label} className="glass-card p-4">
            <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold mb-2">{r.label}</p>
            <p className={`font-mono-data text-3xl font-black tabular-nums ${r.color}`}>{r.value}</p>
            {r.note && <p className="text-[10px] text-muted-foreground mt-1.5 leading-tight">{r.note}</p>}
          </div>
        ))}
      </div>

      {(upside_capture != null || downside_capture != null) && (
        <div className="glass-card p-5">
          <SH title="CAPTURE RATIOS (3Y)" sub="vs benchmark" />
          <div className="grid grid-cols-3 gap-6">
            <div className="text-center">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">UPSIDE CAPTURE</p>
              <p className={`font-mono-data text-2xl font-black tabular-nums ${upside_capture != null && upside_capture > 100 ? 'text-neon-green' : 'text-foreground'}`}>
                {upside_capture != null ? `${upside_capture.toFixed(0)}%` : 'N/A'}
              </p>
              <p className="text-[10px] text-muted-foreground mt-1">
                {upside_capture != null && upside_capture > 100 ? 'Outperforms in rising market' : 'Underperforms in rally'}
              </p>
            </div>
            <div className="text-center border-l border-r border-white/10">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">DOWNSIDE CAPTURE</p>
              <p className={`font-mono-data text-2xl font-black tabular-nums ${downside_capture != null && downside_capture < 100 ? 'text-neon-green' : 'text-signal-red'}`}>
                {downside_capture != null ? `${downside_capture.toFixed(0)}%` : 'N/A'}
              </p>
              <p className="text-[10px] text-muted-foreground mt-1">
                {downside_capture != null && downside_capture < 100 ? 'Protects better than bench' : 'Falls more than bench'}
              </p>
            </div>
            <div className="text-center">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">ASSESSMENT</p>
              <p className={`font-mono-data text-sm font-black mt-1 ${
                upside_capture != null && downside_capture != null && upside_capture > 100 && downside_capture < 100
                  ? 'text-neon-green' : 'text-yellow-400'
              }`}>
                {upside_capture != null && downside_capture != null
                  ? (upside_capture > 100 && downside_capture < 100 ? 'IDEAL' : upside_capture > 100 ? 'AGGRESSIVE' : downside_capture < 100 ? 'DEFENSIVE' : 'TRACKING')
                  : 'N/A'}
              </p>
              <p className="text-[10px] text-muted-foreground mt-1">Captures more up, less down</p>
            </div>
          </div>
        </div>
      )}

      {m.beta_alpha?.beta != null && (
        <div className="glass-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold mb-1">BETA (3Y vs benchmark)</p>
              <p className={`font-mono-data text-2xl font-black ${m.beta_alpha.beta > 1.1 ? 'text-signal-red' : m.beta_alpha.beta < 0.9 ? 'text-neon-green' : 'text-foreground'}`}>{m.beta_alpha.beta.toFixed(2)}</p>
            </div>
            <p className="text-[11px] text-muted-foreground max-w-[240px] text-right leading-relaxed">
              {m.beta_alpha.beta > 1.1 ? 'Moves more than the market — higher volatility.' : m.beta_alpha.beta < 0.9 ? 'Moves less than the market — lower volatility.' : 'Moves broadly with the market.'}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

// ── BENCHMARK TAB ─────────────────────────────────────────────────────────────
export function BenchmarkTab({ brief }: { brief: FundBrief }) {
  const m = brief.metrics!
  const periods = ['1Y', '3Y', '5Y', 'Full'] as const
  const hasBench = periods.some(p => m.benchmark_cagr?.[p] != null)

  if (!hasBench) return (
    <div className="glass-card p-8 text-center">
      <p className="text-sm text-muted-foreground">Benchmark data not available for this fund.</p>
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="glass-card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10 bg-white/[0.02]">
              <th className="text-left px-5 py-3 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Period</th>
              <th className="text-right px-5 py-3 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Fund</th>
              <th className="text-right px-5 py-3 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Benchmark</th>
              <th className="text-right px-5 py-3 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Alpha</th>
            </tr>
          </thead>
          <tbody>
            {periods.map(p => {
              const fv = m.cagr?.[p]; const bv = m.benchmark_cagr?.[p]
              const alpha = fv != null && bv != null ? fv - bv : null
              return (
                <tr key={p} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02] transition-colors">
                  <td className="px-5 py-3 text-sm font-medium text-foreground">{p === 'Full' ? 'Since Inception' : p}</td>
                  <td className={`px-5 py-3 text-right font-mono-data text-sm font-bold tabular-nums ${colorVal(fv)}`}>{fmt(fv)}</td>
                  <td className={`px-5 py-3 text-right font-mono-data text-sm font-bold tabular-nums ${colorVal(bv)}`}>{fmt(bv)}</td>
                  <td className={`px-5 py-3 text-right font-mono-data text-sm font-bold tabular-nums ${alpha != null ? (alpha >= 0 ? 'text-neon-green' : 'text-signal-red') : 'text-muted-foreground'}`}>
                    {alpha != null ? fmtSign(alpha) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="glass-card p-4">
        <p className="text-[10px] text-muted-foreground leading-relaxed">
          <span className="text-foreground font-semibold">Alpha</span> = fund return − benchmark return for the same period.
          Consistent positive alpha over 3Y+ means the fund is genuinely adding value beyond passive exposure.
          Negative alpha means an index fund would have served better.
        </p>
      </div>
    </div>
  )
}

// ── DRAWDOWN TAB ──────────────────────────────────────────────────────────────
export function DrawdownTab({ brief }: { brief: FundBrief }) {
  const m = brief.metrics!
  const dd = m.max_drawdown

  // Build crisis drawdowns from individual fields
  const crisisEvents = [
    { label: 'COVID Crash (Mar 2020)', val: m.dd_covid },
    { label: 'Rate Hike Selloff (2022)', val: m.dd_2022 },
    { label: 'IL&FS Crisis (2018)', val: m.dd_ilfs },
  ].filter(e => e.val != null)

  return (
    <div className="space-y-4">
      {dd && (
        <div className="glass-card p-5">
          <SH title="MAXIMUM DRAWDOWN" sub="Worst peak-to-trough decline in fund history" />
          <div className="grid grid-cols-3 gap-6">
            <div className="text-center">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">MAX DECLINE</p>
              <p className="font-mono-data text-4xl font-black text-signal-red tabular-nums">{dd.max_drawdown_pct != null ? `${dd.max_drawdown_pct}%` : 'N/A'}</p>
            </div>
            <div className="text-center border-l border-r border-white/10">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">TROUGH DATE</p>
              <p className="font-mono-data text-base font-bold text-yellow-400">{dd.trough_date ?? '—'}</p>
              <p className="text-[10px] text-muted-foreground mt-1">Recovery: {dd.recovery_date ?? 'Pending'}</p>
            </div>
            <div className="text-center">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">ASSESSMENT</p>
              <p className={`font-mono-data text-sm font-black mt-2 ${dd.max_drawdown_pct != null && dd.max_drawdown_pct > -30 ? 'text-neon-green' : dd.max_drawdown_pct != null && dd.max_drawdown_pct > -45 ? 'text-yellow-400' : 'text-signal-red'}`}>
                {dd.max_drawdown_pct != null ? (dd.max_drawdown_pct > -30 ? 'RESILIENT' : dd.max_drawdown_pct > -45 ? 'MODERATE' : 'SEVERE') : 'N/A'}
              </p>
            </div>
          </div>
        </div>
      )}

      {crisisEvents.length > 0 && (
        <div className="glass-card overflow-hidden">
          <div className="px-5 py-3 border-b border-white/10 bg-white/[0.02]">
            <SH title="CRISIS DRAWDOWNS" sub="How the fund held up in major market events" />
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/5">
                <th className="text-left px-5 py-2.5 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Event</th>
                <th className="text-right px-5 py-2.5 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Fund Drawdown</th>
              </tr>
            </thead>
            <tbody>
              {crisisEvents.map(({ label, val }) => (
                <tr key={label} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
                  <td className="px-5 py-2.5 text-sm text-foreground">{label}</td>
                  <td className="px-5 py-2.5 text-right font-mono-data text-sm font-bold tabular-nums text-signal-red">{val != null ? `${val}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!dd && crisisEvents.length === 0 && (
        <div className="glass-card p-8 text-center">
          <p className="text-sm text-muted-foreground">Drawdown data not available. Fund may have insufficient history.</p>
        </div>
      )}
    </div>
  )
}

// ── HOLDINGS TAB ──────────────────────────────────────────────────────────────
export function HoldingsTab({ brief }: { brief: FundBrief }) {
  const holdings = brief.holdings?.holdings ?? []

  if (!holdings.length) return (
    <div className="glass-card p-8 text-center">
      <p className="text-sm text-muted-foreground mb-1">Holdings data not available from AMFI.</p>
      <p className="text-[11px] text-muted-foreground opacity-70">Available monthly after 10th. Check amfiindia.com directly.</p>
    </div>
  )

  const top10 = holdings.slice(0, 10)
  const otherPct = holdings.slice(10).reduce((s: number, h: any) => s + (h.pct_nav ?? 0), 0)

  return (
    <div className="space-y-4">
      <div className="glass-card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10 bg-white/[0.02]">
              <th className="text-left px-5 py-2.5 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">#</th>
              <th className="text-left px-5 py-2.5 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Company</th>
              <th className="text-right px-5 py-2.5 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">% NAV</th>
            </tr>
          </thead>
          <tbody>
            {top10.map((h: any, i: number) => (
              <tr key={i} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02] transition-colors">
                <td className="px-5 py-2.5 font-mono-data text-sm text-muted-foreground">{String(i + 1).padStart(2, '0')}</td>
                <td className="px-5 py-2.5">
                  <p className="text-sm font-medium text-foreground">{h.name}</p>
                  {h.sector && <p className="text-[10px] text-muted-foreground mt-0.5">{h.sector}</p>}
                </td>
                <td className="px-5 py-2.5 text-right font-mono-data text-sm font-bold tabular-nums text-electric-blue">
                  {h.pct_nav != null ? `${h.pct_nav.toFixed(1)}%` : '—'}
                </td>
              </tr>
            ))}
            {otherPct > 0 && (
              <tr className="bg-white/[0.01]">
                <td className="px-5 py-2.5 font-mono-data text-sm text-muted-foreground">—</td>
                <td className="px-5 py-2.5 text-sm text-muted-foreground">Others ({holdings.length - 10} stocks)</td>
                <td className="px-5 py-2.5 text-right font-mono-data text-sm font-bold tabular-nums text-muted-foreground">{otherPct.toFixed(1)}%</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── AI BRIEF TAB ──────────────────────────────────────────────────────────────
export function AIBriefTab({ brief, loading, onGenerate }: { brief: FundBrief; loading: boolean; onGenerate: () => void }) {
  const ai = brief.ai
  const conv = brief.conviction ?? ''
  const borderColor = conv.includes('STRONG BUY') ? 'border-l-neon-green' : conv.includes('BUY') ? 'border-l-neon-green/60' : conv.includes('AVOID') ? 'border-l-signal-red' : 'border-l-yellow-400'

  if (!ai?.narrative) return (
    <div className="glass-card p-8 text-center space-y-4">
      <p className="text-sm text-muted-foreground">AI analysis not generated yet.</p>
      <button onClick={onGenerate} disabled={loading} className="px-6 py-2.5 bg-electric-blue/20 border border-electric-blue/40 text-electric-blue text-xs font-bold tracking-widest uppercase rounded-lg hover:bg-electric-blue/30 disabled:opacity-50 transition-colors">
        {loading ? 'Generating…' : 'Generate AI Brief'}
      </button>
    </div>
  )

  return (
    <div className="space-y-4">
      <div className={`glass-card p-6 border-l-4 ${borderColor}`}>
        <div className="flex items-center justify-between mb-4">
          <p className="text-[9px] text-muted-foreground uppercase tracking-[0.2em] font-bold">AI ANALYSIS</p>
          {ai.provider && <span className="text-[9px] text-muted-foreground bg-secondary px-2 py-0.5 rounded border border-white/10 font-mono-data">{ai.provider.toUpperCase()}</span>}
        </div>
        <div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{ai.narrative}</div>
      </div>

      {/* Flags from brief.flags object */}
      {(brief.flags?.red?.length || brief.flags?.amber?.length || brief.flags?.green?.length) ? (
        <div className="glass-card p-5">
          <p className="text-header text-[10px] mb-3">KEY FLAGS</p>
          <div className="space-y-2">
            {[...(brief.flags?.red ?? []).map((t: string) => ({ t, color: 'text-signal-red border-signal-red/30 bg-signal-red/10' })),
              ...(brief.flags?.amber ?? []).map((t: string) => ({ t, color: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10' })),
              ...(brief.flags?.green ?? []).map((t: string) => ({ t, color: 'text-neon-green border-neon-green/30 bg-neon-green/10' }))
            ].map(({ t, color }, i) => (
              <div key={i} className={`text-xs px-3 py-2 rounded border ${color}`}>{t}</div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
