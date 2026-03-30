import { useState, useEffect } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { api, pollBrief } from '../lib/api'
import { LeftPanel } from '../components/LeftPanel'
import { Tabs } from '../ui'
import { FinancialsTab, PeersTab, DCFTab, PatternsTab, WarningsTab, ScenariosTab, MacroTab, AIBriefTab } from '../components/BriefTabs'
import type { EquityBrief } from '../lib/types'

const TABS = [
  { id: 'financials', label: 'Financials' }, { id: 'dcf', label: 'Valuation' },
  { id: 'patterns', label: 'Patterns' }, { id: 'warnings', label: 'Warnings' },
  { id: 'scenarios', label: 'Scenarios' }, { id: 'peers', label: 'Peers' },
  { id: 'macro', label: 'Macro' }, { id: 'ai', label: 'AI Verdict' },
]

interface LocationState { nse_symbol?: string; company_name?: string; sector?: string }

export function CompanyBriefPage() {
  const { bseCode } = useParams<{ bseCode: string }>()
  const { state } = useLocation()
  const nav = useNavigate()
  const s = (state as LocationState) ?? {}

  const [brief, setBrief] = useState<EquityBrief | null>(null)
  const [loading, setLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [activeTab, setActiveTab] = useState('financials')

  const load = async (force = false) => {
    if (!bseCode) return
    setLoading(true); setStatusMsg('Starting analysis…')
    try {
      if (force) await api.clearCache(bseCode)
      const existing = await api.getBrief(bseCode)
      if (existing.status === 'ready') { setBrief(existing); setLoading(false); return }
      const nse = s.nse_symbol || existing.nse_symbol || ''
      const name = s.company_name || existing.company_name || bseCode
      const sector = s.sector || existing.sector || 'diversified'
      await api.analyse({ bse_code: bseCode, nse_symbol: nse, company_name: name, sector })
      const result = await pollBrief(bseCode, 2024, msg => setStatusMsg(msg))
      setBrief(result)
    } catch (e: any) {
      setBrief({ status: 'error', ...(e.message ? { error: e.message } : {}) } as any)
    } finally { setLoading(false); setStatusMsg('') }
  }

  useEffect(() => { if (bseCode) load() }, [bseCode])
  useEffect(() => { setActiveTab('financials') }, [bseCode])

  const isReady = brief?.status === 'ready'

  return (
    <div className="flex gap-4 pt-4 px-4 pb-8 max-w-[1800px] mx-auto">
      <LeftPanel brief={brief} loading={loading} statusMsg={statusMsg} onAnalyse={load} />

      <div className="flex-1 min-w-0">
        {isReady && brief ? (
          <>
            <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />
            <div className="mt-4">
              {activeTab === 'financials' && <FinancialsTab brief={brief} />}
              {activeTab === 'dcf'        && <DCFTab        brief={brief} />}
              {activeTab === 'patterns'   && <PatternsTab   brief={brief} />}
              {activeTab === 'warnings'   && <WarningsTab   brief={brief} />}
              {activeTab === 'scenarios'  && <ScenariosTab  brief={brief} />}
              {activeTab === 'peers'      && <PeersTab      brief={brief} />}
              {activeTab === 'macro'      && <MacroTab      brief={brief} />}
              {activeTab === 'ai'         && <AIBriefTab    brief={brief} loading={loading} onGenerate={() => load(true)} />}
            </div>
          </>
        ) : brief?.status === 'error' ? (
          <div className="glass-card veto-glow p-8 text-center mt-4">
            <p className="text-signal-red font-bold mb-2">Analysis Failed</p>
            <p className="text-xs text-muted-foreground mb-4">{(brief as any).error}</p>
            <button onClick={() => load(true)} className="px-4 py-2 text-xs border border-white/20 rounded-lg hover:border-electric-blue/40 text-muted-foreground">Retry</button>
          </div>
        ) : (
          <div className="mt-4">
            <div className="glass-card border border-white/10 h-10 mb-4 flex items-center px-4 gap-6">
              {TABS.map(t => <div key={t.id} className="skeleton h-3 w-16 rounded" />)}
            </div>
            <div className="space-y-4">
              {[1,2,3].map(i => (
                <div key={i} className="glass-card p-5 space-y-3">
                  <div className="skeleton h-3 w-1/4 rounded" />
                  <div className="grid grid-cols-4 gap-3">
                    {[1,2,3,4].map(j => (
                      <div key={j} className="glass-card p-4 space-y-2">
                        <div className="skeleton h-2 w-2/3 rounded" /><div className="skeleton h-8 w-full rounded" /><div className="skeleton h-2 w-1/2 rounded" />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {statusMsg && (
              <div className="flex items-center gap-2 mt-4 text-xs text-muted-foreground">
                <div className="w-3 h-3 border-2 border-electric-blue border-t-transparent rounded-full animate-spin" />
                {statusMsg}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
