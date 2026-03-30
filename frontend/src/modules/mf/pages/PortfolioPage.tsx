import { useState, useRef } from 'react'
import { api } from '../lib/api'
import { SearchInput, EmptyState } from '../ui'
import { fmt, fmtCr, convictionClass, convictionLabel } from '../lib/utils'
import type { SearchResult, PortfolioOverlap } from '../lib/types'

export function PortfolioPage() {
  const [selected, setSelected] = useState<SearchResult[]>([])
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [computing, setComputing] = useState(false)
  const [overlap, setOverlap]   = useState<PortfolioOverlap | null>(null)
  const [status,  setStatus]    = useState('')
  const debounce = useRef<ReturnType<typeof setTimeout>>()

  const search = (q: string) => {
    setQuery(q)
    clearTimeout(debounce.current)
    if (q.length < 2) { setResults([]); return }
    debounce.current = setTimeout(async () => {
      setLoading(true)
      try { setResults((await api.search(q)).results.slice(0,6)) }
      catch { setResults([]) }
      finally { setLoading(false) }
    }, 400)
  }

  const add = (r: SearchResult) => {
    if (selected.length >= 5) return
    if (selected.some(s => s.scheme_code === r.scheme_code)) return
    setSelected(prev => [...prev, r])
    setQuery(''); setResults([])
  }

  const remove = (code: number) => {
    setSelected(prev => prev.filter(s => s.scheme_code !== code))
    setOverlap(null)
  }

  const compute = async () => {
    if (selected.length < 2) return
    setComputing(true); setStatus('Checking analyses...')
    try {
      // Ensure all analysed
      for (const fund of selected) {
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
      }
      setStatus('Computing overlap...')
      const r = await api.portfolioOverlap(
        selected.map(s => s.scheme_code),
        selected.map(s => s.scheme_name)
      )
      setOverlap(r)
    } catch (e: any) {
      setStatus(`Error: ${e.message}`)
    } finally {
      setComputing(false); setStatus('')
    }
  }

  const matrix = overlap?.overlap_matrix
  const funds  = overlap?.funds as any[]

  const overlapColor = (pct: number | null) => {
    if (pct == null) return 'text-muted-fg'
    if (pct < 30) return 'text-neon-green'
    if (pct < 60) return 'text-yellow-400'
    return 'text-signal-red'
  }

  const overlapBg = (pct: number | null) => {
    if (pct == null) return ''
    if (pct >= 100) return ''  // diagonal
    if (pct < 30) return 'bg-neon-green/5'
    if (pct < 60) return 'bg-yellow-400/5'
    return 'bg-signal-red/8'
  }

  return (
    <div className="pt-16 px-4 pb-8 max-w-[1200px] mx-auto">
      <div className="mb-6">
        <p className="text-header">Portfolio Intelligence</p>
        <h1 className="text-xl font-bold mt-1">Overlap Detection</h1>
        <p className="text-sm text-muted-fg mt-1">Add up to 5 funds to detect true diversification</p>
      </div>

      {/* Add funds */}
      <div className="glass-card p-4 mb-4">
        <div className="flex items-center gap-3 flex-wrap mb-3">
          {selected.map(s => (
            <div key={s.scheme_code}
              className="flex items-center gap-2 bg-secondary border border-white/10 rounded-full px-3 py-1">
              <span className="text-xs font-medium max-w-[180px] truncate">{s.scheme_name}</span>
              <button onClick={() => remove(s.scheme_code)}
                className="text-muted-fg hover:text-signal-red text-base leading-none">×</button>
            </div>
          ))}
          {selected.length < 5 && (
            <span className="text-[10px] text-muted-fg">
              {selected.length === 0 ? 'Add funds below' : `${5 - selected.length} more`}
            </span>
          )}
        </div>

        {selected.length < 5 && (
          <div className="relative">
            <SearchInput
              value={query} onChange={search}
              onSubmit={() => results[0] && add(results[0])}
              placeholder="Add a fund..." loading={loading}
            />
            {results.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 glass-card z-20 divide-y divide-white/5 shadow-xl">
                {results.map(r => (
                  <button key={r.scheme_code}
                    onClick={() => add(r)}
                    disabled={selected.some(s => s.scheme_code === r.scheme_code)}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-secondary/50
                               disabled:opacity-40 disabled:cursor-not-allowed text-left"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{r.scheme_name}</p>
                      <p className="text-[10px] text-muted-fg">{r.fund_house}</p>
                    </div>
                    {selected.some(s => s.scheme_code === r.scheme_code) && (
                      <span className="text-[10px] text-neon-green">Added</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Compute button */}
      {selected.length >= 2 && !overlap && (
        <button
          onClick={compute}
          disabled={computing}
          className="mb-6 px-8 py-3 bg-electric-blue/20 border border-electric-blue/40
                     text-electric-blue text-xs font-semibold tracking-widest uppercase
                     rounded-lg hover:bg-electric-blue/30 disabled:opacity-50 transition-colors"
        >
          {computing ? (
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 border-2 border-electric-blue border-t-transparent rounded-full animate-spin" />
              {status || 'Computing...'}
            </span>
          ) : 'Analyse Overlap →'}
        </button>
      )}

      {/* Overlap matrix */}
      {overlap?.status === 'ready' && matrix && funds && (
        <>
          <div className="glass-card mb-4 overflow-x-auto">
            <div className="p-4 border-b border-white/10">
              <p className="text-header">Overlap Matrix</p>
              <p className="text-[10px] text-muted-fg mt-0.5">
                Green &lt;30% · Yellow 30-60% · Red &gt;60%
              </p>
            </div>
            <table className="w-full">
              <thead>
                <tr>
                  <th className="p-3 text-left text-[10px] text-muted-fg w-40"></th>
                  {funds.map((f: any) => (
                    <th key={f.scheme_code}
                      className="p-3 text-[10px] text-muted-fg font-medium text-center max-w-[120px]">
                      <span className="truncate block max-w-[100px] mx-auto" title={f.scheme_name}>
                        {f.scheme_name?.slice(0,18)}…
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {funds.map((rowFund: any) => (
                  <tr key={rowFund.scheme_code} className="border-t border-white/5">
                    <td className="p-3 text-xs font-medium max-w-[160px]">
                      <span className="truncate block" title={rowFund.scheme_name}>
                        {rowFund.scheme_name?.slice(0,20)}…
                      </span>
                    </td>
                    {funds.map((colFund: any) => {
                      const pct = matrix[rowFund.scheme_code]?.[colFund.scheme_code]
                      const isDiag = rowFund.scheme_code === colFund.scheme_code
                      return (
                        <td key={colFund.scheme_code}
                          className={`p-3 text-center ${overlapBg(isDiag ? null : pct)}`}>
                          <span className={`font-mono-data text-sm font-bold
                            ${isDiag ? 'text-muted-fg' : overlapColor(pct)}`}>
                            {isDiag ? '—' : pct != null ? `${pct.toFixed(1)}%` : 'N/A'}
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Fund summary */}
          <div className="grid grid-cols-3 gap-3">
            {funds.map((f: any) => (
              <div key={f.scheme_code} className="glass-card p-4">
                <p className="text-xs font-bold leading-tight line-clamp-2">{f.scheme_name}</p>
                <p className="text-[10px] text-muted-fg mt-1">{f.fund_house}</p>
                <div className="flex items-center justify-between mt-3">
                  <span className="font-mono-data text-sm font-bold text-electric-blue">
                    {fmt(f.cagr_3y)} 3Y
                  </span>
                  {f.conviction && (
                    <span className={`text-[9px] px-1.5 py-0.5 rounded border font-bold
                      ${convictionClass(f.conviction)}`}>
                      {convictionLabel(f.conviction)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={() => { setOverlap(null) }}
            className="mt-4 text-xs text-muted-fg hover:text-foreground underline"
          >
            Modify selection
          </button>
        </>
      )}

      {selected.length === 0 && (
        <EmptyState icon="◎" message="Add 2-5 funds to analyse portfolio overlap"
          sub="Funds with >60% overlap are redundant — you get the same exposure with higher cost" />
      )}
    </div>
  )
}
