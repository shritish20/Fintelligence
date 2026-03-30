import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { fmt, fmtCr, fmtSign, colorVal, trendColor } from '../lib/utils'
import type { EquityBrief, PatternInsight, EarlyWarning, MacroSignal } from '../lib/types'

// ── Primitives ────────────────────────────────────────────────────────────────
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
      <span className={`font-mono-data text-sm font-bold tabular-nums ${cls}`}>{value}</span>
    </div>
  )
}

// ── FINANCIALS TAB ────────────────────────────────────────────────────────────
export function FinancialsTab({ brief }: { brief: EquityBrief }) {
  const m = brief.metrics || {}
  const fy = brief.fy_year || 2024
  const years = Array.from({ length: 10 }, (_, i) => `FY${fy - i}`)

  const leftMetrics = [
    { label: 'Revenue',   val: fmtCr(m.revenue)      },
    { label: 'EBITDA',    val: fmtCr(m.ebitda)        },
    { label: 'EBITDA %',  val: fmt(m.ebitda_margin),   cls: colorVal(m.ebitda_margin) },
    { label: 'PAT',       val: fmtCr(m.pat)           },
    { label: 'PAT %',     val: fmt(m.pat_margin),      cls: colorVal(m.pat_margin) },
    { label: 'CFO',       val: fmtCr(m.cfo)           },
    { label: 'FCF',       val: fmtCr(m.fcf)           },
  ]
  const rightMetrics = [
    { label: 'ROCE',        val: fmt(m.roce),             cls: m.roce && m.roce > 20 ? 'text-neon-green' : m.roce && m.roce < 10 ? 'text-signal-red' : 'text-foreground' },
    { label: 'ROE',         val: fmt(m.roe),              cls: colorVal(m.roe) },
    { label: 'CFO / PAT',   val: m.cfo_to_pat?.toFixed(2) ?? 'N/A', cls: m.cfo_to_pat && m.cfo_to_pat > 0.9 ? 'text-neon-green' : m.cfo_to_pat && m.cfo_to_pat < 0.7 ? 'text-signal-red' : 'text-foreground' },
    { label: 'Int. Coverage', val: m.interest_cov ? `${m.interest_cov.toFixed(1)}x` : 'N/A', cls: m.interest_cov && m.interest_cov > 5 ? 'text-neon-green' : m.interest_cov && m.interest_cov < 2 ? 'text-signal-red' : 'text-foreground' },
    { label: 'Net Debt',    val: fmtCr(m.net_debt),      cls: m.net_debt && m.net_debt < 0 ? 'text-neon-green' : 'text-foreground' },
    { label: 'ND/EBITDA',   val: m.net_debt_ebitda ? `${m.net_debt_ebitda.toFixed(1)}x` : 'N/A', cls: m.net_debt_ebitda && m.net_debt_ebitda > 3 ? 'text-signal-red' : 'text-foreground' },
    { label: 'D/E',         val: m.debt_equity?.toFixed(2) ?? 'N/A' },
    { label: 'NWC Days',    val: m.nwc_days ? `${m.nwc_days.toFixed(0)}d` : 'N/A', cls: m.nwc_days && m.nwc_days < 0 ? 'text-neon-green' : 'text-foreground' },
  ]

  const cagrs = [
    { l: 'Rev 3Y', v: m.rev_cagr_3y }, { l: 'Rev 5Y', v: m.rev_cagr_5y },
    { l: 'Rev 10Y', v: m.rev_cagr_10y }, { l: 'PAT 3Y', v: m.pat_cagr_3y }, { l: 'PAT 5Y', v: m.pat_cagr_5y },
  ]

  const trendRows = [
    { label: 'Revenue ₹Cr', arr: m.rev_arr as number[], isMargin: false, rev: null },
    { label: 'EBITDA %', arr: m.ebit_arr as number[], isMargin: true, rev: m.rev_arr as number[] },
    { label: 'PAT ₹Cr', arr: m.pat_arr as number[], isMargin: false, rev: null },
    { label: 'ROCE %', arr: m.roce_arr as number[], isMargin: false, rev: null },
    { label: 'CFO ₹Cr', arr: m.cfo_arr as number[], isMargin: false, rev: null },
  ]

  return (
    <div className="space-y-4">
      {/* Snapshot */}
      <div className="grid grid-cols-2 gap-4">
        <div className="glass-card p-4"><SH title="INCOME & CASH" />{leftMetrics.map(x => <MRow key={x.label} label={x.label} value={x.val} cls={(x as any).cls || 'text-foreground'} />)}</div>
        <div className="glass-card p-4"><SH title="RETURNS & STRUCTURE" />{rightMetrics.map(x => <MRow key={x.label} label={x.label} value={x.val} cls={(x as any).cls || 'text-foreground'} />)}</div>
      </div>

      {/* CAGR chips */}
      <div className="flex flex-wrap gap-2">
        {cagrs.map(({ l, v }) => (
          <div key={l} className="glass-card px-4 py-2.5 text-center">
            <p className="text-[9px] text-muted-foreground uppercase tracking-widest">{l}</p>
            <p className={`font-mono-data text-base font-black mt-0.5 tabular-nums ${colorVal(v as number | null)}`}>{fmt(v as number | null)}</p>
          </div>
        ))}
      </div>

      {/* 10-year trend */}
      {trendRows.some(r => r.arr?.length) && (
        <div className="glass-card overflow-x-auto">
          <div className="px-4 py-3 border-b border-white/10 bg-white/[0.02]">
            <SH title="10-YEAR TREND" sub="Most recent → oldest  ·  green = improving  ·  red = declining" />
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left px-4 py-2 text-muted-foreground font-medium w-28">Metric</th>
                {years.map(y => <th key={y} className="text-right px-2 py-2 text-muted-foreground font-mono-data font-normal whitespace-nowrap">{y}</th>)}
              </tr>
            </thead>
            <tbody>
              {trendRows.map(({ label, arr, isMargin, rev }) => {
                const display = isMargin && rev ? arr?.map((v, i) => rev[i] && v ? +((v / rev[i]) * 100).toFixed(1) : null) : arr
                if (!display?.some(v => v != null)) return null
                return (
                  <tr key={label} className="border-b border-white/5 last:border-0">
                    <td className="px-4 py-2 text-muted-foreground whitespace-nowrap">{label}</td>
                    {years.map((_, i) => {
                      const cur = display?.[i]; const prev = display?.[i + 1]
                      const bg = cur != null && prev != null ? trendColor(cur, prev, false) : ''
                      return (
                        <td key={i} className={`text-right px-2 py-2 font-mono-data font-bold tabular-nums ${bg}`}>
                          {cur != null ? (isMargin ? `${cur}%` : `${(cur / 100).toFixed(0)}`) : '—'}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── DCF / VALUATION TAB ───────────────────────────────────────────────────────
export function DCFTab({ brief }: { brief: EquityBrief }) {
  const dcf = brief.dcf
  const m = brief.metrics || {}
  const imp = brief.implied_growth
  const spreads = (brief.spreads as any) ?? {}

  if (!dcf?.available && !imp) return (
    <div className="glass-card p-8 text-center">
      <p className="text-sm text-muted-foreground">DCF data not available — Screener data or annual report may be incomplete.</p>
    </div>
  )

  const cmp = m.current_price ?? 0
  const premium = dcf?.base_cr && cmp ? ((cmp - dcf.base_cr) / dcf.base_cr * 100) : null

  return (
    <div className="space-y-4">
      {/* DCF card */}
      {dcf?.available && (
        <div className="glass-card intel-glow p-5">
          <div className="flex items-center justify-between mb-4">
            <SH title="DCF VALUATION" sub={`WACC ${dcf.wacc_pct?.toFixed(1) ?? '—'}%  ·  Terminal Growth ${dcf.terminal_growth?.toFixed(1) ?? '—'}%`} />
          </div>
          <div className="grid grid-cols-4 gap-3 mb-4">
            {[
              { label: 'BEAR CASE', val: dcf.bear_cr, color: 'text-signal-red' },
              { label: 'BASE CASE', val: dcf.base_cr, color: 'text-foreground' },
              { label: 'BULL CASE', val: dcf.bull_cr, color: 'text-neon-green' },
              { label: 'CMP', val: cmp || null, color: cmp && dcf.base_cr ? (cmp > dcf.base_cr ? 'text-yellow-400' : 'text-neon-green') : 'text-electric-blue' },
            ].map(({ label, val, color }) => (
              <div key={label} className="text-center">
                <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">{label}</p>
                <p className={`font-mono-data text-xl font-black tabular-nums ${color}`}>{val ? `₹${val.toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}</p>
              </div>
            ))}
          </div>
          {premium !== null && (
            <div className={`text-center py-2 rounded-lg border ${Math.abs(premium) < 10 ? 'border-yellow-400/30 bg-yellow-400/5 text-yellow-400' : premium > 0 ? 'border-signal-red/30 bg-signal-red/5 text-signal-red' : 'border-neon-green/30 bg-neon-green/5 text-neon-green'}`}>
              <p className="font-mono-data text-sm font-bold">
                {premium > 0 ? `+${premium.toFixed(1)}% premium to base case` : `${premium.toFixed(1)}% discount to base case`}
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                {Math.abs(premium) < 10 ? 'FAIRLY VALUED' : premium > 20 ? 'RICH — price in high growth' : premium > 0 ? 'SLIGHTLY RICH' : 'MARGIN OF SAFETY'}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Implied growth */}
      {imp != null && (
        <div className="glass-card p-5">
          <SH title="REVERSE DCF — IMPLIED GROWTH" sub="What earnings CAGR the market is pricing in at CMP" />
          <div className="flex items-center gap-6">
            <div>
              <p className="font-mono-data text-4xl font-black tabular-nums text-electric-blue">{imp.toFixed(1)}%/yr</p>
              <p className="text-[11px] text-muted-foreground mt-1">Market is pricing this earnings CAGR in perpetuity</p>
            </div>
            <div className="border-l border-white/10 pl-6">
              {m.pat_cagr_5y != null && (
                <div className="mb-2">
                  <p className="text-[10px] text-muted-foreground">Historical 5Y PAT CAGR</p>
                  <p className={`font-mono-data text-lg font-bold ${imp > (m.pat_cagr_5y ?? 0) + 2 ? 'text-signal-red' : 'text-neon-green'}`}>{m.pat_cagr_5y.toFixed(1)}%/yr</p>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {m.pat_cagr_5y != null ? (
                  imp > (m.pat_cagr_5y ?? 0) + 2 ? 'Market pricing above historical — premium requires acceleration.' : 'Implied growth below historical — modest expectations baked in.'
                ) : 'Compare against sector growth expectations.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ROCE spread */}
      {spreads.roce_spread != null && (
        <div className="glass-card p-5">
          <SH title="MOAT — ROCE SPREAD" sub="ROCE minus cost of capital. Positive = economic value creation." />
          <div className="flex items-center gap-4 mb-3">
            <div className="text-center">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Company ROCE</p>
              <p className="font-mono-data text-2xl font-black text-foreground">{m.roce?.toFixed(1) ?? '—'}%</p>
            </div>
            <p className="text-muted-foreground text-xl">−</p>
            <div className="text-center">
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Cost of Capital</p>
              <p className="font-mono-data text-2xl font-black text-muted-foreground">{dcf?.wacc_pct?.toFixed(1) ?? '—'}%</p>
            </div>
            <p className="text-muted-foreground text-xl">=</p>
            <div className={`text-center px-4 py-2 rounded-lg border ${spreads.roce_spread > 10 ? 'border-neon-green/40 bg-neon-green/10' : spreads.roce_spread > 0 ? 'border-yellow-400/40 bg-yellow-400/10' : 'border-signal-red/40 bg-signal-red/10'}`}>
              <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Spread</p>
              <p className={`font-mono-data text-2xl font-black ${spreads.roce_spread > 10 ? 'text-neon-green' : spreads.roce_spread > 0 ? 'text-yellow-400' : 'text-signal-red'}`}>
                {spreads.roce_spread > 0 ? '+' : ''}{spreads.roce_spread?.toFixed(1)}pp
              </p>
              <p className={`text-[9px] font-bold mt-0.5 ${spreads.roce_spread > 10 ? 'text-neon-green' : spreads.roce_spread > 0 ? 'text-yellow-400' : 'text-signal-red'}`}>
                {spreads.roce_spread > 15 ? 'STRONG MOAT' : spreads.roce_spread > 5 ? 'NARROW MOAT' : spreads.roce_spread > 0 ? 'MARGINAL' : 'DESTROYING VALUE'}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── PATTERNS TAB ──────────────────────────────────────────────────────────────
export function PatternsTab({ brief }: { brief: EquityBrief }) {
  const patterns = brief.patterns ?? []
  if (!patterns.length) return <div className="glass-card p-8 text-center"><p className="text-sm text-muted-foreground">No patterns detected.</p></div>

  const sigColor = { STRENGTH: 'text-neon-green border-neon-green/30 bg-neon-green/10', WARNING: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10', NORMAL: 'text-muted-foreground border-white/10 bg-secondary', INFO: 'text-electric-blue border-electric-blue/30 bg-electric-blue/10' }

  return (
    <div className="space-y-3">
      {patterns.map((p: PatternInsight, i: number) => (
        <div key={i} className="glass-card p-4">
          <div className="flex items-start gap-3">
            <span className={`text-[9px] font-black px-2 py-0.5 rounded border shrink-0 mt-0.5 ${sigColor[p.signal] ?? sigColor.INFO}`}>{p.signal}</span>
            <div>
              <p className="text-sm font-semibold text-foreground mb-1">{p.name}</p>
              <p className="text-xs text-muted-foreground leading-relaxed">{p.insight}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── WARNINGS TAB ──────────────────────────────────────────────────────────────
export function WarningsTab({ brief }: { brief: EquityBrief }) {
  const warnings = brief.early_warnings ?? []
  if (!warnings.length) return <div className="glass-card p-8 text-center"><p className="text-sm text-muted-foreground">No early warnings triggered.</p></div>

  const statusStyle = { OK: { icon: '✓', cls: 'text-neon-green border-neon-green/30 bg-neon-green/10' }, WARN: { icon: '⚠', cls: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10' }, CRITICAL: { icon: '✗', cls: 'text-signal-red border-signal-red/30 bg-signal-red/10' } }

  return (
    <div className="space-y-3">
      {warnings.map((w: EarlyWarning, i: number) => {
        const st = statusStyle[w.status] ?? statusStyle.WARN
        return (
          <div key={i} className="glass-card p-4">
            <div className="flex items-start gap-3">
              <span className={`text-[10px] font-black px-2 py-0.5 rounded border shrink-0 mt-0.5 ${st.cls}`}>{st.icon} {w.status}</span>
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-semibold text-foreground">{w.label}</p>
                  {w.current != null && <span className="font-mono-data text-sm font-bold text-foreground">{w.current.toFixed(1)}</span>}
                </div>
                {w.calibration && <p className="text-[11px] text-muted-foreground mb-1">{w.calibration}</p>}
                {w.interpretation && <p className="text-xs text-muted-foreground leading-relaxed">{w.interpretation}</p>}
                {(w.threshold_warn != null || w.threshold_crit != null) && (
                  <p className="text-[10px] text-muted-foreground mt-1.5 font-mono-data">
                    {w.threshold_warn != null ? `WARN ≥ ${w.threshold_warn}  ` : ''}{w.threshold_crit != null ? `CRIT ≥ ${w.threshold_crit}` : ''}
                  </p>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── PEERS TAB ─────────────────────────────────────────────────────────────────
export function PeersTab({ brief }: { brief: EquityBrief }) {
  const peers = brief.peers ?? {}
  const peerNames = Object.keys(peers)
  if (!peerNames.length) return <div className="glass-card p-8 text-center"><p className="text-sm text-muted-foreground">Peer data not available.</p></div>

  const cols = ['Revenue', 'EBITDA %', 'ROCE', 'PAT CAGR 3Y', 'PE', 'Net Debt/EBITDA']
  const getV = (data: any, col: string): string => {
    const map: Record<string, string> = { 'Revenue': 'revenue', 'EBITDA %': 'ebitda_margin', 'ROCE': 'roce', 'PAT CAGR 3Y': 'pat_cagr_3y', 'PE': 'pe', 'Net Debt/EBITDA': 'net_debt_ebitda' }
    const v = data?.[map[col]]
    if (v == null) return '—'
    if (col === 'Revenue') return `₹${((v as number) / 100).toFixed(0)}K`
    if (['EBITDA %', 'ROCE', 'PAT CAGR 3Y'].includes(col)) return `${(v as number).toFixed(1)}%`
    if (col === 'PE') return `${(v as number).toFixed(1)}x`
    return (v as number).toFixed(1)
  }

  return (
    <div className="glass-card overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-white/10 bg-white/[0.02]">
            <th className="text-left px-4 py-3 text-[10px] text-muted-foreground font-bold uppercase tracking-widest">Company</th>
            {cols.map(c => <th key={c} className="text-right px-4 py-3 text-[10px] text-muted-foreground font-bold uppercase tracking-widest whitespace-nowrap">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-white/5 bg-electric-blue/5">
            <td className="px-4 py-3 text-sm font-bold text-electric-blue">{brief.company_name} ★</td>
            {cols.map(c => <td key={c} className="px-4 py-3 text-right font-mono-data text-sm font-bold text-foreground">{getV(brief.metrics, c)}</td>)}
          </tr>
          {peerNames.map(peer => (
            <tr key={peer} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
              <td className="px-4 py-3 text-sm text-foreground">{peer}</td>
              {cols.map(c => <td key={c} className="px-4 py-3 text-right font-mono-data text-sm text-muted-foreground">{getV(peers[peer], c)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── SCENARIOS TAB ─────────────────────────────────────────────────────────────
export function ScenariosTab({ brief }: { brief: EquityBrief }) {
  const s = brief.scenarios
  if (!s) return <div className="glass-card p-8 text-center"><p className="text-sm text-muted-foreground">Scenario data not available.</p></div>

  const scenarios = [
    { key: 'bear', label: 'BEAR', color: 'text-signal-red', border: 'border-signal-red/30', bg: 'bg-signal-red/5', data: s.bear },
    { key: 'base', label: 'BASE', color: 'text-foreground', border: 'border-white/20', bg: 'bg-white/[0.02]', data: s.base },
    { key: 'bull', label: 'BULL', color: 'text-neon-green', border: 'border-neon-green/30', bg: 'bg-neon-green/5', data: s.bull },
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {scenarios.map(({ label, color, border, bg, data }) => data ? (
          <div key={label} className={`glass-card p-5 border ${border} ${bg}`}>
            <p className={`text-[9px] uppercase tracking-[0.2em] font-black mb-3 ${color}`}>{label}</p>
            <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">Probability</p>
            <p className={`font-mono-data text-2xl font-black tabular-nums mb-3 ${color}`}>{(data.probability * 100).toFixed(0)}%</p>
            {data.intrinsic_value && (
              <><p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">Fair Value</p>
              <p className="font-mono-data text-lg font-bold text-foreground">₹{data.intrinsic_value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</p></>
            )}
            <p className="text-[9px] text-muted-foreground uppercase tracking-widest mt-3 mb-0.5">Rev CAGR mult</p>
            <p className="font-mono-data text-sm font-bold text-foreground">{data.rev_cagr_mult.toFixed(1)}x</p>
            {data.trigger && <p className="text-[10px] text-muted-foreground mt-3 leading-relaxed">{data.trigger}</p>}
          </div>
        ) : null)}
      </div>
      {s.implied_disruption_prob != null && (
        <div className="glass-card p-4 text-center">
          <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">MARKET-IMPLIED DISRUPTION PROBABILITY</p>
          <p className="font-mono-data text-3xl font-black text-yellow-400">{(s.implied_disruption_prob * 100).toFixed(0)}%</p>
          <p className="text-[11px] text-muted-foreground mt-1">At current CMP, the market is pricing this probability of business disruption</p>
        </div>
      )}
    </div>
  )
}

// ── MACRO TAB ─────────────────────────────────────────────────────────────────
export function MacroTab({ brief }: { brief: EquityBrief }) {
  const [signals, setSignals] = useState<MacroSignal[]>(brief.macro_signals ?? [])
  const [loading, setLoading] = useState(false)

  const refresh = async () => {
    if (!brief.sector) return
    setLoading(true)
    try { const r = await api.getMacro(brief.sector); setSignals(r.signals) }
    catch { }
    finally { setLoading(false) }
  }

  useEffect(() => { if (!signals.length && brief.sector) refresh() }, [])

  if (!signals.length && !loading) return (
    <div className="glass-card p-8 text-center">
      <p className="text-sm text-muted-foreground mb-3">No macro signals available for {brief.sector}</p>
      <button onClick={refresh} className="text-[10px] text-electric-blue hover:underline">Refresh</button>
    </div>
  )

  const sigColor = { POSITIVE: 'text-neon-green border-neon-green/30 bg-neon-green/10', WARNING: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10', NEUTRAL: 'text-muted-foreground border-white/10 bg-secondary' }
  const impColor = { MARGIN: 'text-yellow-400', REVENUE: 'text-electric-blue', COST: 'text-orange-400', DEMAND: 'text-purple-400' }

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <p className="text-[10px] text-muted-foreground">Sector: <span className="text-foreground font-semibold">{brief.sector?.replace(/_/g, ' ').toUpperCase()}</span></p>
        <button onClick={refresh} disabled={loading} className="text-[10px] text-electric-blue hover:underline disabled:opacity-50">
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {signals.map((s: MacroSignal, i: number) => (
        <div key={i} className="glass-card p-4">
          <div className="flex items-start gap-3">
            <span className={`text-[9px] font-black px-2 py-0.5 rounded border shrink-0 mt-0.5 ${sigColor[s.signal as keyof typeof sigColor] ?? sigColor.NEUTRAL}`}>{s.signal}</span>
            <div className="flex-1">
              <p className="text-xs text-muted-foreground leading-relaxed">{s.text}</p>
              <span className={`inline-block mt-2 text-[9px] font-bold uppercase tracking-wider ${impColor[s.impact as keyof typeof impColor] ?? 'text-muted-foreground'}`}>{s.impact}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── AI BRIEF TAB ──────────────────────────────────────────────────────────────
export function AIBriefTab({ brief, loading, onGenerate }: { brief: EquityBrief; loading: boolean; onGenerate: () => void }) {
  const intel = brief.intelligence
  if (!intel?.verdict && !intel?.essence) return (
    <div className="glass-card p-8 text-center space-y-4">
      <p className="text-sm text-muted-foreground">AI analysis not generated yet.</p>
      <button onClick={onGenerate} disabled={loading} className="px-6 py-2.5 bg-electric-blue/20 border border-electric-blue/40 text-electric-blue text-xs font-bold tracking-widest uppercase rounded-lg hover:bg-electric-blue/30 disabled:opacity-50 transition-colors">
        {loading ? 'Generating…' : 'Generate AI Brief'}
      </button>
    </div>
  )

  const conv = brief.conviction ?? ''
  const borderColor = conv.includes('STRONG BUY') ? 'border-l-neon-green' : conv.includes('AVOID') ? 'border-l-signal-red' : 'border-l-yellow-400'

  return (
    <div className="space-y-4">
      {intel.essence && (
        <div className="glass-card p-5">
          <p className="text-[9px] text-muted-foreground uppercase tracking-[0.2em] font-bold mb-2">ESSENCE</p>
          <p className="text-sm font-medium text-foreground leading-relaxed">{intel.essence}</p>
        </div>
      )}

      {intel.verdict && (
        <div className={`glass-card p-6 border-l-4 ${borderColor}`}>
          <div className="flex items-center justify-between mb-4">
            <p className="text-[9px] text-muted-foreground uppercase tracking-[0.2em] font-bold">THE VERDICT</p>
            {intel.provider && <span className="text-[9px] text-muted-foreground bg-secondary px-2 py-0.5 rounded border border-white/10 font-mono-data">{intel.provider.toUpperCase()}</span>}
          </div>
          <div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{intel.verdict}</div>
          <div className="mt-4 pt-4 border-t border-white/10">
            <p className="text-[10px] text-muted-foreground italic">Intelligence, not advice. All reasoning shown. The investor decides.</p>
          </div>
        </div>
      )}

      {intel.watchlist && intel.watchlist.length > 0 && (
        <div className="glass-card p-5">
          <p className="text-header text-[10px] mb-3">WATCH LIST — METRICS TO MONITOR</p>
          <div className="space-y-2">
            {intel.watchlist.map((w: any, i: number) => (
              <div key={i} className="flex items-start gap-3 py-2 border-b border-white/5 last:border-0">
                <span className="text-[10px] font-mono-data text-electric-blue font-bold shrink-0 w-32 truncate">{w.metric}</span>
                <span className="text-[10px] text-muted-foreground leading-relaxed">{w.interpretation} <span className="text-foreground font-semibold">(Threshold: {w.threshold})</span></span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(brief.qualitative as any)?.hidden_insight && (
        <div className="glass-card p-5 border border-yellow-400/20 bg-yellow-400/[0.02]">
          <p className="text-[9px] text-yellow-400 uppercase tracking-[0.2em] font-black mb-2">HIDDEN INSIGHT — FROM ANNUAL REPORT (GEMINI)</p>
          <p className="text-sm text-muted-foreground leading-relaxed italic">"{(brief.qualitative as any).hidden_insight}"</p>
        </div>
      )}
    </div>
  )
}
