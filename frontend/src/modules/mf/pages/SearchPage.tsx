import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { SearchInput } from '../ui'
import { categoryColor, relativeTime, convictionClass, convictionLabel } from '../lib/utils'
import type { SearchResult, HistoryItem } from '../lib/types'

const FILTERS = ['All', 'Equity', 'Debt', 'Hybrid', 'ELSS'] as const

export function SearchPage() {
  const nav = useNavigate()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All')
  const [results, setResults] = useState<SearchResult[]>([])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const debounce = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => { api.history(8).then(r => setHistory(r.history)).catch(() => {}) }, [])

  useEffect(() => {
    clearTimeout(debounce.current)
    if (query.trim().length < 2) { setResults([]); setError(''); return }
    debounce.current = setTimeout(async () => {
      setLoading(true); setError('')
      try { const r = await api.search(query); setResults(r.results) }
      catch (e: any) { setError(e.message || 'Search failed'); setResults([]) }
      finally { setLoading(false) }
    }, 400)
    return () => clearTimeout(debounce.current)
  }, [query])

  const go = (code: number) => nav(`/mf/fund/${code}`)

  const filteredResults = filter === 'All' ? results : results.filter(r =>
    r.scheme_category?.toLowerCase().includes(filter.toLowerCase()) ||
    r.scheme_type?.toLowerCase().includes(filter.toLowerCase())
  )

  return (
    <div className="max-w-3xl mx-auto pt-10 pb-16 px-4">

      {/* Hero */}
      <div className="text-center mb-8">
        <h1 className="text-2xl font-black text-foreground tracking-tight mb-2">Mutual Fund Intelligence</h1>
        <p className="text-sm text-muted-foreground">Rolling returns · Risk-adjusted alpha · Drawdown · Holdings · AI synthesis</p>
      </div>

      {/* Search */}
      <SearchInput value={query} onChange={setQuery} onSubmit={() => filteredResults[0] && go(filteredResults[0].scheme_code)} placeholder="Search mutual fund — name, AMC, or scheme code…" loading={loading} />
      {error && <p className="text-xs text-signal-red mt-2 px-1">{error}</p>}

      {/* Filter pills */}
      <div className="flex gap-2 mt-3 flex-wrap">
        {FILTERS.map(f => (
          <button key={f} onClick={() => { setFilter(f); if (f !== 'All') setQuery(f === 'ELSS' ? 'ELSS' : f) }}
            className={`text-[10px] px-3 py-1 rounded-full border font-bold uppercase tracking-wide transition-colors
              ${filter === f ? 'bg-electric-blue/15 text-electric-blue border-electric-blue/40' : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground'}`}>
            {f}
          </button>
        ))}
      </div>

      {/* Search results */}
      {filteredResults.length > 0 && (
        <div className="mt-4 glass-card divide-y divide-white/5">
          {filteredResults.map(r => (
            <button key={r.scheme_code} onClick={() => go(r.scheme_code)}
              className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-white/[0.03] transition-colors text-left group">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate group-hover:text-electric-blue transition-colors">{r.scheme_name}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">{r.fund_house || 'Mutual Fund'}</p>
              </div>
              {r.scheme_category && (
                <span className={`text-[9px] px-2 py-0.5 rounded-full border shrink-0 font-bold uppercase tracking-wide ${categoryColor(r.scheme_category)}`}>
                  {r.scheme_category.split('-').pop()?.trim() || r.scheme_category}
                </span>
              )}
              <span className="text-muted-foreground text-xs shrink-0 group-hover:text-electric-blue transition-colors">→</span>
            </button>
          ))}
        </div>
      )}

      {query.length >= 2 && !loading && filteredResults.length === 0 && !error && (
        <div className="mt-4 glass-card p-8 text-center">
          <p className="text-sm text-muted-foreground">No funds found for "{query}"</p>
          <p className="text-xs text-muted-foreground mt-1 opacity-70">Try AMC name, fund type, or scheme code</p>
        </div>
      )}

      {/* No query: history + quick tools */}
      {!query && (
        <div className="mt-8 grid grid-cols-2 gap-4">
          <div>
            <p className="text-header text-[10px] mb-3">Recent Analyses</p>
            {history.length === 0 ? (
              <div className="glass-card p-5 text-center">
                <p className="text-xs text-muted-foreground">No analyses yet</p>
                <p className="text-[11px] text-muted-foreground mt-1 opacity-70">Search for a fund to begin</p>
              </div>
            ) : (
              <div className="glass-card divide-y divide-white/5">
                {history.map(h => (
                  <button key={h.scheme_code} onClick={() => go(parseInt(h.scheme_code))}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.03] transition-colors text-left group">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-foreground truncate group-hover:text-electric-blue transition-colors">{h.scheme_name}</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">{relativeTime(h.analysed_at)}</p>
                    </div>
                    {h.conviction && (
                      <span className={`text-[9px] px-1.5 py-0.5 rounded border font-black uppercase shrink-0 ${convictionClass(h.conviction)}`}>
                        {convictionLabel(h.conviction)}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <p className="text-header text-[10px] mb-3">Quick Tools</p>
            <div className="space-y-2">
              {[
                { label: 'Compare Two Funds', sub: 'Side-by-side analysis', path: '/mf/compare', icon: '⇔' },
                { label: 'Portfolio Overlap', sub: 'Up to 5 funds', path: '/mf/portfolio', icon: '◎' },
              ].map(({ label, sub, path, icon }) => (
                <button key={path} onClick={() => nav(path)}
                  className="w-full glass-card p-4 flex items-center gap-3 hover:border-electric-blue/30 hover:bg-electric-blue/5 transition-all text-left group">
                  <span className="text-2xl text-electric-blue shrink-0">{icon}</span>
                  <div>
                    <p className="text-sm font-medium text-foreground group-hover:text-electric-blue transition-colors">{label}</p>
                    <p className="text-[11px] text-muted-foreground">{sub}</p>
                  </div>
                  <span className="ml-auto text-muted-foreground group-hover:text-electric-blue transition-colors text-xs">→</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
