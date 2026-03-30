import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { SearchInput } from '../ui'
import { sectorColor, relativeTime, convictionClass } from '../lib/utils'
import type { EquitySearchResult, HistoryItem } from '../lib/types'

const SECTORS = [
  { key: 'paints', label: 'Paints' }, { key: 'it_services', label: 'IT Services' },
  { key: 'private_bank', label: 'Banks' }, { key: 'fmcg', label: 'FMCG' },
  { key: 'cement', label: 'Cement' }, { key: 'pharma', label: 'Pharma' },
  { key: 'auto_oem', label: 'Auto OEM' }, { key: 'nbfc', label: 'NBFC' },
]

const SECTOR_COMPANIES: Record<string, Array<{ bse: string; nse: string; name: string; sector: string }>> = {
  paints:       [{ bse:'500820', nse:'ASIANPAINT', name:'Asian Paints', sector:'paints' }, { bse:'509480', nse:'BERGEPAINT', name:'Berger Paints', sector:'paints' }],
  it_services:  [{ bse:'532540', nse:'TCS', name:'TCS', sector:'it_services' }, { bse:'500209', nse:'INFY', name:'Infosys', sector:'it_services' }, { bse:'507685', nse:'WIPRO', name:'Wipro', sector:'it_services' }],
  private_bank: [{ bse:'500180', nse:'HDFCBANK', name:'HDFC Bank', sector:'private_bank' }, { bse:'532174', nse:'ICICIBANK', name:'ICICI Bank', sector:'private_bank' }, { bse:'500247', nse:'KOTAKBANK', name:'Kotak Bank', sector:'private_bank' }],
  fmcg:         [{ bse:'500696', nse:'HINDUNILVR', name:'HUL', sector:'fmcg' }, { bse:'500790', nse:'NESTLEIND', name:'Nestle India', sector:'fmcg' }],
  cement:       [{ bse:'532538', nse:'ULTRACEMCO', name:'UltraTech', sector:'cement' }, { bse:'500387', nse:'SHREECEM', name:'Shree Cement', sector:'cement' }],
  pharma:       [{ bse:'524715', nse:'SUNPHARMA', name:'Sun Pharma', sector:'pharma' }, { bse:'500124', nse:'DRREDDY', name:"Dr Reddy's", sector:'pharma' }],
  auto_oem:     [{ bse:'532500', nse:'MARUTI', name:'Maruti Suzuki', sector:'auto_oem' }, { bse:'500520', nse:'M&M', name:'M&M', sector:'auto_oem' }],
  nbfc:         [{ bse:'500034', nse:'BAJFINANCE', name:'Bajaj Finance', sector:'nbfc' }],
}

export function SearchPage() {
  const nav = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<EquitySearchResult[]>([])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selSector, setSelSector] = useState<string | null>(null)
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
    }, 500)
    return () => clearTimeout(debounce.current)
  }, [query])

  const goCompany = (r: EquitySearchResult) => nav(`/equity/company/${r.bse_code}`, { state: { nse_symbol: r.nse_symbol, company_name: r.company_name, sector: r.sector || 'diversified' } })
  const goQuick = (c: { bse: string; nse: string; name: string; sector: string }) => nav(`/equity/company/${c.bse}`, { state: { nse_symbol: c.nse, company_name: c.name, sector: c.sector } })

  return (
    <div className="max-w-3xl mx-auto pt-10 pb-16 px-4">

      {/* Hero */}
      <div className="text-center mb-8">
        <h1 className="text-2xl font-black text-foreground tracking-tight mb-2">Equity Intelligence</h1>
        <p className="text-sm text-muted-foreground">Annual report → Screener → DCF → Sector patterns → Verdict</p>
      </div>

      <SearchInput value={query} onChange={setQuery} onSubmit={() => results[0] && goCompany(results[0])} placeholder="Search company — name or BSE code…" loading={loading} />
      {error && <p className="text-xs text-signal-red mt-2 px-1">{error}</p>}

      {/* Search results */}
      {results.length > 0 && (
        <div className="mt-4 glass-card divide-y divide-white/5">
          {results.map(r => (
            <button key={r.bse_code} onClick={() => goCompany(r)}
              className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-white/[0.03] transition-colors text-left group">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate group-hover:text-electric-blue transition-colors">{r.company_name}</p>
                <p className="text-[10px] font-mono-data text-muted-foreground mt-0.5">BSE {r.bse_code}{r.nse_symbol ? ` · NSE ${r.nse_symbol}` : ''}</p>
              </div>
              {r.sector && (
                <span className={`text-[9px] px-2 py-0.5 rounded-full border shrink-0 font-bold uppercase tracking-wide ${sectorColor(r.sector)}`}>
                  {r.sector.replace(/_/g, ' ')}
                </span>
              )}
              <span className="text-muted-foreground text-xs group-hover:text-electric-blue transition-colors">→</span>
            </button>
          ))}
        </div>
      )}

      {query.length >= 2 && !loading && results.length === 0 && !error && (
        <div className="mt-4 glass-card p-8 text-center">
          <p className="text-sm text-muted-foreground">No results for "{query}"</p>
          <p className="text-xs text-muted-foreground mt-1 opacity-70">Try company name or BSE code (e.g. 500820)</p>
        </div>
      )}

      {/* No query: history + sector explorer */}
      {!query && (
        <div className="mt-8 space-y-6">

          {history.length > 0 && (
            <div>
              <p className="text-header text-[10px] mb-3">Recent Analyses</p>
              <div className="glass-card divide-y divide-white/5">
                {history.map(h => (
                  <button key={h.bse_code} onClick={() => nav(`/equity/company/${h.bse_code}`, { state: { sector: h.sector } })}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.03] transition-colors text-left group">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-foreground truncate group-hover:text-electric-blue transition-colors">{h.company_name}</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">{relativeTime(h.analysed_at)}</p>
                    </div>
                    {h.sector && <span className={`text-[9px] px-1.5 py-0.5 rounded-full border ${sectorColor(h.sector)}`}>{h.sector.replace(/_/g, ' ')}</span>}
                    {h.conviction && <span className={`text-[9px] px-1.5 py-0.5 rounded border font-black ${convictionClass(h.conviction)}`}>{h.conviction.split(' ').slice(0, 2).join(' ')}</span>}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <p className="text-header text-[10px] mb-3">Sector Explorer</p>
            <div className="grid grid-cols-4 gap-2 mb-3">
              {SECTORS.map(s => (
                <button key={s.key} onClick={() => setSelSector(selSector === s.key ? null : s.key)}
                  className={`py-2 px-3 text-[11px] font-bold rounded-lg border transition-colors
                    ${selSector === s.key ? `${sectorColor(s.key)} border-current` : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground'}`}>
                  {s.label}
                </button>
              ))}
            </div>

            {selSector && SECTOR_COMPANIES[selSector] && (
              <div className="glass-card divide-y divide-white/5">
                {SECTOR_COMPANIES[selSector].map(c => (
                  <button key={c.bse} onClick={() => goQuick(c)}
                    className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-white/[0.03] transition-colors text-left group">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-foreground group-hover:text-electric-blue transition-colors">{c.name}</p>
                      <p className="text-[10px] font-mono-data text-muted-foreground mt-0.5">BSE {c.bse} · NSE {c.nse}</p>
                    </div>
                    <span className="text-muted-foreground text-xs group-hover:text-electric-blue transition-colors">→</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
