import { useState, useEffect, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { SearchInput, ConvictionBadge, EmptyState } from '../ui'
import { fmt, fmtSign, fmtCr, colorVal, categoryColor } from '../lib/utils'
import type { SearchResult, CompareResult } from '../lib/types'

function FundPicker({
  label, selected, onSelect
}: {
  label:    string
  selected: SearchResult | null
  onSelect: (r: SearchResult) => void
}) {
  const [q, setQ]           = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const debounce = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    clearTimeout(debounce.current)
    if (q.length < 2) { setResults([]); return }
    debounce.current = setTimeout(async () => {
      setLoading(true)
      try { setResults((await api.search(q)).results) }
      catch { setResults([]) }
      finally { setLoading(false) }
    }, 400)
  }, [q])

  return (
    <div className="flex-1 min-w-0">
      <p className="text-header mb-3">{label}</p>
      {selected ? (
        <div className="glass-card p-4 intel-glow">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm font-bold text-foreground leading-tight">{selected.scheme_name}</p>
              <p className="text-xs text-muted-fg mt-1">{selected.fund_house}</p>
              {selected.scheme_category && (
                <span className={`inline-block mt-2 text-[10px] px-2 py-0.5 rounded-full border ${categoryColor(selected.scheme_category)}`}>
                  {selected.scheme_category.split('-').pop()?.trim()}
                </span>
              )}
            </div>
            <button onClick={() => { onSelect(null as any); setQ('') }}
              className="text-muted-fg hover:text-signal-red text-lg ml-3 shrink-0">×</button>
          </div>
        </div>
      ) : (
        <div className="relative">
          <SearchInput
            value={q} onChange={setQ} onSubmit={() => results[0] && onSelect(results[0])}
            placeholder={`Search ${label}...`} loading={loading}
          />
          {results.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 glass-card z-20 divide-y divide-white/5 shadow-xl">
              {results.slice(0,6).map(r => (
                <button key={r.scheme_code}
                  onClick={() => { onSelect(r); setQ(''); setResults([]) }}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-secondary/50 text-left"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">{r.scheme_name}</p>
                    <p className="text-[10px] text-muted-fg">{r.fund_house}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const METRICS = [
  { key: 'cagr_1y',            label: '1Y CAGR',            fmt: (v: any) => fmt(v), better: 'higher' },
  { key: 'cagr_3y',            label: '3Y CAGR',            fmt: (v: any) => fmt(v), better: 'higher' },
  { key: 'cagr_5y',            label: '5Y CAGR',            fmt: (v: any) => fmt(v), better: 'higher' },
  { key: 'sip_xirr',           label: 'SIP XIRR 3Y',        fmt: (v: any) => fmt(v), better: 'higher' },
  { key: 'alpha',              label: 'Alpha 3Y',           fmt: (v: any) => fmtSign(v), better: 'higher' },
  { key: 'sharpe',             label: 'Sharpe 3Y',          fmt: (v: any) => v?.toFixed(3) ?? 'N/A', better: 'higher' },
  { key: 'sortino',            label: 'Sortino 3Y',         fmt: (v: any) => v?.toFixed(3) ?? 'N/A', better: 'higher' },
  { key: 'beta',               label: 'Beta 3Y',            fmt: (v: any) => v?.toFixed(3) ?? 'N/A', better: 'lower' },
  { key: 'information_ratio',  label: 'Info Ratio',         fmt: (v: any) => v?.toFixed(3) ?? 'N/A', better: 'higher' },
  { key: 'upside_capture',     label: 'Upside Capture',     fmt: (v: any) => fmt(v), better: 'higher' },
  { key: 'downside_capture',   label: 'Downside Capture',   fmt: (v: any) => fmt(v), better: 'lower' },
  { key: 'max_drawdown',       label: 'Max Drawdown',       fmt: (v: any) => fmt(v, '%', 2), better: 'lower' },
  { key: 'std_dev',            label: 'Std Dev 3Y',         fmt: (v: any) => fmt(v), better: 'lower' },
  { key: 'expense_ratio',      label: 'Expense Ratio',      fmt: (v: any) => fmt(v), better: 'lower' },
  { key: 'aum_crore',          label: 'AUM',                fmt: (v: any) => fmtCr(v), better: 'neither' },
  { key: 'rolling_3y_pct_above_8', label: 'Rolling 3Y >8%', fmt: (v: any) => fmt(v), better: 'higher' },
]

export function ComparePage() {
  const [searchParams] = useSearchParams()
  const nav = useNavigate()
  const [fundA, setFundA] = useState<SearchResult | null>(null)
  const [fundB, setFundB] = useState<SearchResult | null>(null)
  const [result, setResult] = useState<CompareResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const [statusA, setStatusA] = useState('')
  const [statusB, setStatusB] = useState('')

  // Pre-fill from URL param
  useEffect(() => {
    const a = searchParams.get('a')
    if (a) {
      api.getBrief(parseInt(a)).then(b => {
        if (b.scheme_name) {
          setFundA({ scheme_code: parseInt(a), scheme_name: b.scheme_name,
            fund_house: b.fund_house || '', scheme_type: '', scheme_category: b.category || '' })
        }
      }).catch(() => {})
    }
  }, [])

  const compare = async () => {
    if (!fundA || !fundB) return
    setLoading(true); setError('')
    try {
      // Ensure both are analysed
      for (const [fund, setStatus] of [[fundA, setStatusA],[fundB, setStatusB]] as const) {
        const existing = await api.getBrief(fund.scheme_code)
        if (existing.status !== 'ready') {
          setStatus(`Analysing ${fund.scheme_name.slice(0,30)}...`)
          await api.analyse(fund.scheme_code)
          let tries = 0
          while (tries < 40) {
            await new Promise(r => setTimeout(r, 3000))
            const b = await api.getBrief(fund.scheme_code)
            if (b.status === 'ready' || b.status === 'error') break
            tries++
          }
        }
        setStatus('')
      }
      const r = await api.compare(fundA.scheme_code, fundB.scheme_code)
      setResult(r)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
      setStatusA(''); setStatusB('')
    }
  }

  const overlap = result?.overlap as any

  return (
    <div className="pt-16 px-4 pb-8 max-w-[1400px] mx-auto">
      <div className="mb-6">
        <p className="text-header">Fund Comparison</p>
        <h1 className="text-xl font-bold mt-1">Side-by-Side Analysis</h1>
      </div>

      {/* Fund pickers */}
      <div className="flex gap-4 mb-6">
        <FundPicker label="FUND A" selected={fundA} onSelect={setFundA} />
        <div className="flex items-center text-2xl text-muted-fg px-2 pt-8">⇔</div>
        <FundPicker label="FUND B" selected={fundB} onSelect={setFundB} />
      </div>

      {/* Status messages */}
      {(statusA || statusB) && (
        <div className="glass-card p-3 mb-4 flex gap-4 text-xs text-muted-fg">
          {statusA && <span className="flex items-center gap-2">
            <span className="w-3 h-3 border-2 border-electric-blue border-t-transparent rounded-full animate-spin" />
            {statusA}
          </span>}
          {statusB && <span className="flex items-center gap-2">
            <span className="w-3 h-3 border-2 border-electric-blue border-t-transparent rounded-full animate-spin" />
            {statusB}
          </span>}
        </div>
      )}

      {/* Compare button */}
      {fundA && fundB && !result && (
        <button
          onClick={compare}
          disabled={loading}
          className="mb-6 px-8 py-3 bg-electric-blue/20 border border-electric-blue/40
                     text-electric-blue text-xs font-semibold tracking-widest uppercase
                     rounded-lg hover:bg-electric-blue/30 disabled:opacity-50 transition-colors"
        >
          {loading ? 'Comparing...' : 'Compare Funds →'}
        </button>
      )}

      {error && <p className="text-signal-red text-xs mb-4">{error}</p>}

      {/* Results */}
      {result?.status === 'ready' && result.fund_a && result.fund_b && (
        <>
          {/* Fund headers */}
          <div className="grid grid-cols-2 gap-4 mb-4">
            {[result.fund_a, result.fund_b].map((f: any, i) => (
              <div key={i} className="glass-card intel-glow p-4">
                <p className="text-sm font-bold leading-tight">{f.scheme_name}</p>
                <p className="text-xs text-muted-fg mt-1">{f.fund_house}</p>
                <div className="mt-3">
                  <ConvictionBadge conviction={f.conviction} size="compact" />
                </div>
              </div>
            ))}
          </div>

          {/* Comparison table */}
          <div className="glass-card mb-4">
            <div className="grid grid-cols-4 gap-2 px-4 py-2 border-b border-white/10
                            text-[10px] text-muted-fg uppercase tracking-wide">
              <span>Metric</span>
              <span className="text-right">{(result.fund_a as any).scheme_name?.slice(0,20)}</span>
              <span className="text-right">{(result.fund_b as any).scheme_name?.slice(0,20)}</span>
              <span className="text-center">Winner</span>
            </div>
            {METRICS.map(({ key, label, fmt: fmtFn, better }) => {
              const va = (result.fund_a as any)[key]
              const vb = (result.fund_b as any)[key]
              const aWins = va != null && vb != null && (
                better === 'higher' ? va > vb : better === 'lower' ? va < vb : false
              )
              const bWins = va != null && vb != null && (
                better === 'higher' ? vb > va : better === 'lower' ? vb < va : false
              )
              return (
                <div key={key} className="grid grid-cols-4 gap-2 px-4 py-3 border-b border-white/5 last:border-0">
                  <span className="text-xs text-muted-fg">{label}</span>
                  <span className={`font-mono-data text-sm text-right font-bold
                    ${aWins ? 'text-neon-green' : 'text-foreground'}`}>
                    {fmtFn(va)}
                  </span>
                  <span className={`font-mono-data text-sm text-right font-bold
                    ${bWins ? 'text-neon-green' : 'text-foreground'}`}>
                    {fmtFn(vb)}
                  </span>
                  <span className="text-center">
                    {aWins && (
                      <span className="text-[9px] px-1.5 py-0.5 bg-neon-green/10 text-neon-green border border-neon-green/30 rounded">
                        A
                      </span>
                    )}
                    {bWins && (
                      <span className="text-[9px] px-1.5 py-0.5 bg-neon-green/10 text-neon-green border border-neon-green/30 rounded">
                        B
                      </span>
                    )}
                  </span>
                </div>
              )
            })}
          </div>

          {/* Overlap */}
          {overlap && (
            <div className="glass-card p-6 text-center">
              <p className="text-header mb-3">Portfolio Overlap</p>
              <p className={`font-mono-data text-6xl font-black mb-2
                ${overlap.overlap_pct < 30 ? 'text-neon-green'
                  : overlap.overlap_pct < 60 ? 'text-yellow-400'
                  : 'text-signal-red'}`}>
                {overlap.overlap_pct?.toFixed(1)}%
              </p>
              <p className={`text-xs font-medium
                ${overlap.overlap_pct < 30 ? 'text-neon-green'
                  : overlap.overlap_pct < 60 ? 'text-yellow-400'
                  : 'text-signal-red'}`}>
                {overlap.overlap_pct < 30 ? 'Low overlap — good diversification'
                  : overlap.overlap_pct < 60 ? 'Moderate overlap — some redundancy'
                  : 'High overlap — consider consolidating'}
              </p>
              {overlap.shared_stocks?.length > 0 && (
                <div className="mt-4 text-left max-w-sm mx-auto">
                  <p className="text-header mb-2">Top Shared Holdings</p>
                  {overlap.shared_stocks.slice(0,5).map((s: any, i: number) => (
                    <div key={i} className="flex justify-between py-1.5 border-b border-white/5 last:border-0">
                      <span className="text-xs truncate">{s.name}</span>
                      <span className="font-mono-data text-xs text-muted-fg ml-3 shrink-0">
                        {s.weight_a?.toFixed(1)}% / {s.weight_b?.toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <button
            onClick={() => { setResult(null); setFundA(null); setFundB(null) }}
            className="mt-4 text-xs text-muted-fg hover:text-foreground underline"
          >
            Start new comparison
          </button>
        </>
      )}

      {!fundA && !fundB && (
        <EmptyState icon="⇔" message="Select two funds to compare" sub="Search and select Fund A and Fund B above" />
      )}
    </div>
  )
}
