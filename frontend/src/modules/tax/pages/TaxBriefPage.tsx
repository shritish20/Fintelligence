import { useState, useEffect, useRef } from 'react'
import { api, fmtINR, fmtINRFull, colorAmt, flagClass, flagIcon, flagColor, type TaxBrief, type Flag, type QueryResponse } from '../lib/api'

// ── Skeletons ─────────────────────────────────────────────────────────────────
function Sk({ cls = '' }: { cls?: string }) { return <div className={`skeleton rounded ${cls}`} /> }

// ── Primitives ────────────────────────────────────────────────────────────────
function SH({ title, sub, right }: { title: string; sub?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between mb-4">
      <div>
        <p className="text-header text-[10px]">{title}</p>
        {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
      </div>
      {right}
    </div>
  )
}

function ActBadge({ ref: r }: { ref: string }) {
  return <span className="text-[9px] text-muted-foreground bg-secondary border border-white/10 px-1.5 py-0.5 rounded font-mono-data">{r}</span>
}

// ── Demo banner ───────────────────────────────────────────────────────────────
function DemoBanner({ onUpload }: { onUpload: () => void }) {
  return (
    <div className="glass-card border border-electric-blue/30 bg-electric-blue/5 p-4 mb-6 flex items-center justify-between">
      <div>
        <p className="text-xs font-black text-electric-blue tracking-wide">⚡  DEMO MODE — Simulated Nifty options seller portfolio</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">Real numbers. Not your numbers. Upload Zerodha Tax P&L + CAMS to see yours.</p>
      </div>
      <button onClick={onUpload} className="ml-4 shrink-0 px-4 py-2 bg-electric-blue/20 border border-electric-blue/40 text-electric-blue text-[10px] font-black tracking-widest uppercase rounded-lg hover:bg-electric-blue/30 transition-colors">
        Upload Your Data →
      </button>
    </div>
  )
}

// ── Upload modal ──────────────────────────────────────────────────────────────
function UploadModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: (b: TaxBrief) => void }) {
  const [zerodha, setZerodha] = useState<File | null>(null)
  const [cams, setCams] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!zerodha && !cams) { setError('Upload at least one file'); return }
    setLoading(true); setError('')
    try { const brief = await api.uploadStatements(zerodha || undefined, cams || undefined); onSuccess(brief) }
    catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 px-4">
      <div className="glass-card intel-glow w-full max-w-lg p-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-sm font-bold text-foreground">Upload Your Portfolio Data</h3>
            <p className="text-[11px] text-muted-foreground mt-1">Zerodha Tax P&L CSV · CAMS Consolidated Statement</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors text-lg">×</button>
        </div>

        <div className="space-y-4">
          {[
            { label: 'Zerodha Tax P&L (CSV)', hint: 'Reports → Tax P&L → Download CSV', file: zerodha, set: setZerodha },
            { label: 'CAMS Statement (PDF/CSV)', hint: 'myCAMS.com → Statement → Download', file: cams, set: setCams },
          ].map(({ label, hint, file, set }) => (
            <div key={label}>
              <label className="block text-xs font-semibold text-foreground mb-1">{label}</label>
              <p className="text-[10px] text-muted-foreground mb-2">{hint}</p>
              <label className={`flex items-center justify-center gap-2 h-12 border border-dashed rounded-lg cursor-pointer transition-colors ${file ? 'border-neon-green/40 bg-neon-green/5' : 'border-white/20 hover:border-electric-blue/40 hover:bg-electric-blue/5'}`}>
                <input type="file" accept=".csv,.pdf" className="hidden" onChange={e => set(e.target.files?.[0] ?? null)} />
                <span className="text-[11px] text-muted-foreground">{file ? `✓ ${file.name}` : 'Click to upload'}</span>
              </label>
            </div>
          ))}
        </div>

        {error && <p className="text-xs text-signal-red mt-3">{error}</p>}

        <div className="flex gap-3 mt-6">
          <button onClick={onClose} className="flex-1 py-2 text-xs border border-white/20 rounded-lg text-muted-foreground hover:border-white/40 transition-colors">Cancel</button>
          <button onClick={submit} disabled={loading} className="flex-1 py-2 text-xs bg-electric-blue/20 border border-electric-blue/40 text-electric-blue font-bold rounded-lg hover:bg-electric-blue/30 disabled:opacity-50 transition-colors">
            {loading ? 'Analysing…' : 'Analyse My Portfolio'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Top HUD ───────────────────────────────────────────────────────────────────
function TaxHud({ isDemo, onUpload }: { isDemo: boolean; onUpload: () => void }) {
  const [time, setTime] = useState('')
  const [health, setHealth] = useState<{ gemini: string; pdf_count: number } | null>(null)

  useEffect(() => {
    const t = () => setTime(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    t(); const iv = setInterval(t, 1000); return () => clearInterval(iv)
  }, [])

  useEffect(() => { api.health().then(h => setHealth({ gemini: h.gemini, pdf_count: h.pdf_count })).catch(() => {}) }, [])

  return (
    <div className="fixed top-12 left-0 right-0 z-40 h-10 glass-card border-t-0 border-l-0 border-r-0 rounded-none border-b border-white/10 flex items-center px-4 gap-4 bg-black/90 backdrop-blur">
      <span className="text-xs font-black tracking-widest text-electric-blue">FINTELLIGENCE</span>
      <div className="w-px h-4 bg-white/10" />
      <span className="text-[9px] text-muted-foreground uppercase tracking-[0.2em] font-bold">TAX INTEL</span>
      <div className="flex-1" />
      {health && (
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${health.gemini === 'ok' ? 'bg-neon-green' : 'bg-signal-red'}`} />
            <span className={`text-[10px] font-mono-data font-bold ${health.gemini === 'ok' ? 'text-neon-green' : 'text-signal-red'}`}>
              {health.gemini === 'ok' ? 'GEMINI OK' : 'GEMINI OFF'}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${health.pdf_count > 0 ? 'bg-neon-green' : 'bg-yellow-400'}`} />
            <span className={`text-[10px] font-mono-data ${health.pdf_count > 0 ? 'text-neon-green' : 'text-yellow-400'}`}>
              {health.pdf_count} ACT{health.pdf_count !== 1 ? 'S' : ''} LOADED
            </span>
          </div>
        </div>
      )}
      <div className="w-px h-4 bg-white/10" />
      {isDemo && <button onClick={onUpload} className="text-[10px] text-electric-blue hover:underline font-semibold">Upload Your Data →</button>}
      <span className="font-mono-data text-[11px] text-muted-foreground">{time} IST</span>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function TaxBriefPage() {
  const [brief, setBrief] = useState<TaxBrief | null>(null)
  const [loading, setLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [queryResult, setQueryResult] = useState<QueryResponse | null>(null)
  const [querying, setQuerying] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.getDemoBrief().then(b => setBrief(b)).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])

  const submitQuery = async () => {
    if (!query.trim()) return
    setQuerying(true); setQueryResult(null)
    try { setQueryResult(await api.query(query)) } catch (e: any) { setQueryResult({ query, answer: `Error: ${e.message}`, answerable: false, caveat: '' }) }
    finally { setQuerying(false) }
  }

  if (loading) return (
    <div className="pt-24 px-4 pb-8 max-w-[1100px] mx-auto space-y-4">
      <Sk cls="h-32 w-full" />
      <div className="grid grid-cols-3 gap-4">{[1,2,3].map(i => <Sk key={i} cls="h-28" />)}</div>
      {[1,2,3].map(i => <Sk key={i} cls="h-20 w-full" />)}
    </div>
  )

  if (error) return (
    <div className="pt-24 px-4"><div className="glass-card veto-glow p-8 text-center max-w-md mx-auto"><p className="text-signal-red font-bold mb-2">Failed to load</p><p className="text-xs text-muted-foreground">{error}</p></div></div>
  )

  if (!brief) return null

  const isDemo = !!brief.is_demo
  const { summary, income_breakdown, regime_comparison, flags, harvest_opportunities, advance_tax, fo_detail, mf_breakdown } = brief

  return (
    <>
      <TaxHud isDemo={isDemo} onUpload={() => setShowUpload(true)} />
      {showUpload && <UploadModal onClose={() => setShowUpload(false)} onSuccess={b => { setBrief(b); setShowUpload(false) }} />}

      <div className="pt-24 px-4 pb-12 max-w-[1100px] mx-auto space-y-6">
        {isDemo && <DemoBanner onUpload={() => setShowUpload(true)} />}

        {/* ── Snapshot: 3 cards ── */}
        <div className="grid grid-cols-3 gap-4">
          <div className="glass-card p-5">
            <p className="text-[9px] text-muted-foreground uppercase tracking-[0.2em] font-bold mb-3">ESTIMATED TAX</p>
            <p className="font-mono-data text-3xl font-black text-foreground">{fmtINR(summary?.estimated_tax_new_regime)}</p>
            <p className="text-[10px] text-muted-foreground mt-1">New Regime · FY {brief.financial_year ?? '2025-26'}</p>
            <div className="mt-3 pt-3 border-t border-white/10">
              <div className="flex justify-between items-baseline">
                <span className="text-[10px] text-muted-foreground">Old Regime</span>
                <span className="font-mono-data text-sm text-muted-foreground">{fmtINR(summary?.estimated_tax_old_regime)}</span>
              </div>
            </div>
          </div>

          <div className="glass-card p-5 border border-neon-green/20 bg-neon-green/[0.03]">
            <p className="text-[9px] text-muted-foreground uppercase tracking-[0.2em] font-bold mb-3">REGIME CHOICE</p>
            <p className={`font-mono-data text-3xl font-black ${summary?.better_regime === 'new' ? 'text-neon-green' : 'text-yellow-400'}`}>
              {summary?.better_regime?.toUpperCase() ?? 'NEW'} REGIME
            </p>
            <p className="text-[10px] text-muted-foreground mt-1">Saves {fmtINR(summary?.regime_saving)} over old regime</p>
            <p className="text-[10px] text-muted-foreground mt-1 font-mono-data">{regime_comparison?.act_ref ?? 'Sec 115BAC'}</p>
          </div>

          <div className="glass-card p-5 border border-yellow-400/20 bg-yellow-400/[0.03]">
            <p className="text-[9px] text-muted-foreground uppercase tracking-[0.2em] font-bold mb-3">HARVEST OPPORTUNITY</p>
            <p className="font-mono-data text-3xl font-black text-yellow-400">{fmtINR(summary?.total_harvest_opportunity)}</p>
            <p className="text-[10px] text-muted-foreground mt-1">LTCG exemption remaining: {fmtINR(summary?.ltcg_exemption_remaining)}</p>
            <button onClick={() => document.getElementById('harvest-section')?.scrollIntoView({ behavior: 'smooth' })} className="mt-2 text-[10px] text-yellow-400 hover:underline">View opportunities →</button>
          </div>
        </div>

        {/* ── Flags ── */}
        {flags && flags.length > 0 && (
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-3 border-b border-white/10 bg-white/[0.02]">
              <SH title="FLAGS" sub="Sorted by urgency" />
            </div>
            <div className="divide-y divide-white/5">
              {flags.sort((a: Flag, b: Flag) => {
                const order = { URGENT: 0, WATCH: 1, GREEN: 2 }
                return (order[a.priority as keyof typeof order] ?? 1) - (order[b.priority as keyof typeof order] ?? 1)
              }).map((f: Flag, i: number) => (
                <div key={i} className="px-5 py-4">
                  <div className="flex items-start gap-3">
                    <span className={`text-[9px] font-black px-2 py-0.5 rounded border shrink-0 mt-0.5 ${
                      f.priority === 'URGENT' ? 'text-signal-red border-signal-red/30 bg-signal-red/10' :
                      f.priority === 'WATCH'  ? 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10' :
                      'text-neon-green border-neon-green/30 bg-neon-green/10'
                    }`}>
                      {f.priority === 'URGENT' ? '🔴' : f.priority === 'WATCH' ? '🟡' : '🟢'} {f.priority}
                    </span>
                    <div className="flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-foreground">{f.title}</p>
                        {f.act_ref && <ActBadge ref={f.act_ref} />}
                      </div>
                      {f.narrative && <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{f.narrative}</p>}
                      {f.saving && f.saving > 0 && (
                        <p className="text-[10px] text-neon-green mt-1 font-mono-data font-bold">Potential saving: {fmtINR(f.saving)}</p>
                      )}
                      {f.action_date && <p className="text-[10px] text-signal-red mt-1 font-semibold">Due: {f.action_date}</p>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Income breakdown ── */}
        {income_breakdown && income_breakdown.length > 0 && (
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-3 border-b border-white/10 bg-white/[0.02]">
              <SH title="INCOME BREAKDOWN" sub={`FY ${brief.financial_year ?? '2025-26'} · AY ${brief.assessment_year ?? '2026-27'}`} />
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/5">
                  {['Head', 'Amount', 'Treatment', 'Tax at Rate'].map(h => (
                    <th key={h} className="px-5 py-2.5 text-left text-[10px] text-muted-foreground font-bold uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {income_breakdown.map((row: any, i: number) => (
                  <tr key={i} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
                    <td className="px-5 py-3 text-sm font-medium text-foreground">{row.head}</td>
                    <td className="px-5 py-3 font-mono-data text-sm font-bold tabular-nums text-foreground">{fmtINR(row.amount)}</td>
                    <td className="px-5 py-3 text-xs text-muted-foreground">{row.treatment} {row.act_ref ? <span className="font-mono-data text-[9px] opacity-70">· {row.act_ref}</span> : ''}</td>
                    <td className={`px-5 py-3 font-mono-data text-sm font-bold tabular-nums ${row.tax_at_slab > 0 ? 'text-signal-red' : 'text-neon-green'}`}>{fmtINR(row.tax_at_slab)}</td>
                  </tr>
                ))}
                <tr className="bg-white/[0.02] border-t border-white/15">
                  <td className="px-5 py-3 text-sm font-black text-foreground">TOTAL</td>
                  <td className="px-5 py-3 font-mono-data text-sm font-black text-foreground">{fmtINR(income_breakdown.reduce((s: number, r: any) => s + (r.amount ?? 0), 0))}</td>
                  <td />
                  <td className="px-5 py-3 font-mono-data text-sm font-black text-signal-red">{fmtINR(income_breakdown.reduce((s: number, r: any) => s + (r.tax_at_slab ?? 0), 0))}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* ── Harvest opportunities ── */}
        {harvest_opportunities && harvest_opportunities.length > 0 && (
          <div id="harvest-section" className="glass-card overflow-hidden">
            <div className="px-5 py-3 border-b border-white/10 bg-yellow-400/[0.03] border-yellow-400/20">
              <SH title="LTCG HARVEST OPPORTUNITIES" sub="Sell and immediately rebuy. 3-day settlement gap. Section 112A." />
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/5">
                  {['Instrument', 'Unrealised', 'Harvestable', 'Tax Saving', 'Strategy'].map(h => (
                    <th key={h} className="px-5 py-2.5 text-left text-[10px] text-muted-foreground font-bold uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {harvest_opportunities.map((h: any, i: number) => (
                  <tr key={i} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
                    <td className="px-5 py-3 text-sm font-medium text-foreground">{h.instrument}</td>
                    <td className="px-5 py-3 font-mono-data text-sm text-yellow-400 font-bold">{fmtINR(h.unrealised_gain)}</td>
                    <td className="px-5 py-3 font-mono-data text-sm text-foreground font-bold">{fmtINR(h.harvestable)}</td>
                    <td className="px-5 py-3 font-mono-data text-sm text-neon-green font-bold">{fmtINR(h.tax_saving)}</td>
                    <td className="px-5 py-3 text-xs text-muted-foreground">{h.strategy}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Advance tax timeline ── */}
        {advance_tax?.schedule && advance_tax.schedule.length > 0 && (
          <div className="glass-card p-5">
            <SH title="ADVANCE TAX SCHEDULE" sub={`Estimated annual tax: ${fmtINR(advance_tax.estimated_annual_tax)} · Paid so far: ${fmtINR(advance_tax.paid_so_far)}`} />
            <div className="flex items-center gap-0">
              {advance_tax.schedule.map((inst: any, i: number) => (
                <div key={i} className="flex-1 relative">
                  {i > 0 && <div className="absolute left-0 top-2.5 w-full h-px bg-white/15 -z-0" />}
                  <div className="relative z-10 flex flex-col items-center">
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                      inst.status === 'PAID' ? 'bg-neon-green border-neon-green' :
                      inst.status === 'OVERDUE' ? 'bg-signal-red border-signal-red' :
                      'bg-secondary border-white/30'
                    }`}>
                      {inst.status === 'PAID' && <span className="text-black text-[8px] font-black">✓</span>}
                      {inst.status === 'OVERDUE' && <span className="text-white text-[8px] font-black">!</span>}
                    </div>
                    <p className="text-[9px] font-mono-data text-muted-foreground mt-2">{inst.due_date}</p>
                    <p className="text-[9px] text-muted-foreground">{inst.label}</p>
                    <p className={`font-mono-data text-xs font-bold mt-1 ${inst.status === 'PAID' ? 'text-neon-green' : inst.status === 'OVERDUE' ? 'text-signal-red' : 'text-foreground'}`}>
                      {fmtINR(inst.amount_due)}
                    </p>
                    {inst.status !== 'PAID' && inst.is_past && (
                      <p className="text-[9px] text-signal-red mt-0.5">OVERDUE</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Regime comparison ── */}
        {regime_comparison && (
          <div className="glass-card overflow-hidden">
            <div className="px-5 py-3 border-b border-white/10 bg-white/[0.02]">
              <SH title="REGIME COMPARISON" sub={regime_comparison.act_ref} />
            </div>
            <div className="grid grid-cols-2 divide-x divide-white/10">
              {[
                { label: 'NEW REGIME', data: regime_comparison.new_regime, isBetter: regime_comparison.better_regime === 'new' } as any,
                { label: 'OLD REGIME', data: regime_comparison.old_regime as any, isBetter: regime_comparison.better_regime === 'old' },
              ].map(({ label, data, isBetter }) => (
                <div key={label} className={`p-5 ${isBetter ? 'bg-neon-green/[0.03]' : ''}`}>
                  <div className="flex items-center gap-2 mb-4">
                    <p className="text-header text-[10px]">{label}</p>
                    {isBetter && <span className="text-[9px] font-black text-neon-green bg-neon-green/10 border border-neon-green/30 px-1.5 py-0.5 rounded">BETTER</span>}
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between"><span className="text-[10px] text-muted-foreground">Slab Tax</span><span className="font-mono-data text-sm font-bold">{fmtINR(data?.slab_tax)}</span></div>
                    {data?.deductions_claimed > 0 && <div className="flex justify-between"><span className="text-[10px] text-muted-foreground">Deductions</span><span className="font-mono-data text-sm font-bold text-neon-green">-{fmtINR(data.deductions_claimed)}</span></div>}
                    <div className="flex justify-between border-t border-white/10 pt-2"><span className="text-[10px] text-foreground font-bold">TOTAL TAX</span><span className={`font-mono-data text-base font-black ${isBetter ? 'text-neon-green' : 'text-foreground'}`}>{fmtINR(data?.total_tax)}</span></div>
                  </div>
                </div>
              ))}
            </div>
            {regime_comparison.saving > 0 && (
              <div className="px-5 py-3 border-t border-white/10 bg-neon-green/[0.03] text-center">
                <p className="text-sm font-bold text-neon-green">{regime_comparison.better_regime === 'new' ? 'New' : 'Old'} regime saves <span className="font-mono-data">{fmtINR(regime_comparison.saving)}</span></p>
                {regime_comparison.note && <p className="text-[11px] text-muted-foreground mt-1">{regime_comparison.note}</p>}
              </div>
            )}
          </div>
        )}

        {/* ── Query box ── */}
        <div className="glass-card p-5">
          <SH title="ASK A FINANCE ACT QUESTION" sub="Gemini reads the actual Finance Act PDF. Not from memory." />
          <div className="flex gap-2">
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submitQuery()}
              placeholder='e.g. "What is the tax on SGBs sold before maturity?" or "Is F&O income eligible for 44AD?"'
              className="flex-1 bg-secondary border border-white/15 rounded-lg px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-electric-blue/50 transition-colors"
            />
            <button onClick={submitQuery} disabled={querying || !query.trim()} className="px-5 py-2.5 bg-electric-blue/20 border border-electric-blue/40 text-electric-blue text-xs font-bold rounded-lg hover:bg-electric-blue/30 disabled:opacity-50 transition-colors whitespace-nowrap">
              {querying ? 'Asking…' : 'Ask →'}
            </button>
          </div>
          {queryResult && (
            <div className={`mt-4 p-4 rounded-lg border ${queryResult.answerable ? 'border-electric-blue/30 bg-electric-blue/5' : 'border-yellow-400/30 bg-yellow-400/5'}`}>
              {(queryResult.section || queryResult.act) && (
                <div className="flex items-center gap-2 mb-2">
                  {queryResult.act && <span className="text-[9px] text-muted-foreground bg-secondary px-2 py-0.5 rounded border border-white/10 font-mono-data">{queryResult.act}</span>}
                  {queryResult.section && <span className="text-[9px] text-electric-blue bg-electric-blue/10 px-2 py-0.5 rounded border border-electric-blue/30 font-mono-data">Section {queryResult.section}</span>}
                </div>
              )}
              <p className="text-sm text-foreground leading-relaxed">{queryResult.answer}</p>
              {queryResult.caveat && <p className="text-[10px] text-muted-foreground mt-2 italic">{queryResult.caveat}</p>}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
