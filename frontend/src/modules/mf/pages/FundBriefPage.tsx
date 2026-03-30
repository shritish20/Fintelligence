import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api, pollBrief } from '../lib/api'
import { LeftPanel } from '../components/LeftPanel'
import { Tabs } from '../ui'
import {
  ReturnsTab, RiskTab, BenchmarkTab,
  DrawdownTab, HoldingsTab, AIBriefTab
} from '../components/BriefTabs'
import type { FundBrief } from '../lib/types'

const EQUITY_TABS = [
  { id: 'returns',   label: 'Returns'   },
  { id: 'risk',      label: 'Risk'      },
  { id: 'benchmark', label: 'Benchmark' },
  { id: 'drawdown',  label: 'Drawdown'  },
  { id: 'holdings',  label: 'Holdings'  },
  { id: 'ai',        label: 'AI Brief'  },
]

const DEBT_TABS = [
  { id: 'returns',  label: 'Returns'  },
  { id: 'risk',     label: 'Risk'     },
  { id: 'drawdown', label: 'Drawdown' },
  { id: 'holdings', label: 'Holdings' },
  { id: 'ai',       label: 'AI Brief' },
]

export function FundBriefPage() {
  const { schemeCode } = useParams<{ schemeCode: string }>()
  const nav = useNavigate()
  const code = parseInt(schemeCode || '0')

  const [brief,     setBrief]     = useState<FundBrief | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [activeTab, setActiveTab] = useState('returns')

  const load = async (withRegime = false, forceRefresh = false) => {
    if (!code) return
    setLoading(true)
    setStatusMsg('Starting analysis...')

    try {
      // If force refresh, clear cache first
      if (forceRefresh) await api.clearCache(code)

      // Check if result already in cache
      const existing = await api.getBrief(code, withRegime)
      if (existing.status === 'ready') {
        setBrief(existing)
        setLoading(false)
        return
      }

      // Trigger analysis
      await api.analyse(code, withRegime)

      // Poll until ready
      const result = await pollBrief(code, withRegime, msg => setStatusMsg(msg))
      setBrief(result)
    } catch (e: any) {
      setBrief({ status: 'error', error: e.message })
    } finally {
      setLoading(false)
      setStatusMsg('')
    }
  }

  // Auto-load on mount
  useEffect(() => {
    if (code) load()
  }, [code])

  // Reset tab when fund changes
  useEffect(() => {
    setActiveTab('returns')
  }, [code])

  const tabs = brief?.fund_type === 'debt' ? DEBT_TABS : EQUITY_TABS
  const isReady = brief?.status === 'ready'

  return (
    <div className="flex gap-4 pt-16 px-4 pb-8 max-w-[1800px] mx-auto">

      {/* Left panel */}
      <LeftPanel
        brief={brief}
        loading={loading}
        statusMsg={statusMsg}
        onAnalyse={(withRegime) => load(withRegime, true)}
        onCompare={() => nav(`/mf/compare?a=${code}`)}
        onClear={async () => { await api.clearCache(code); load() }}
      />

      {/* Right panel */}
      <div className="flex-1 min-w-0">
        {isReady && brief ? (
          <>
            <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

            <div>
              {activeTab === 'returns'   && <ReturnsTab   brief={brief} />}
              {activeTab === 'risk'      && <RiskTab      brief={brief} />}
              {activeTab === 'benchmark' && brief.fund_type !== 'debt' && <BenchmarkTab brief={brief} />}
              {activeTab === 'drawdown'  && <DrawdownTab  brief={brief} />}
              {activeTab === 'holdings'  && <HoldingsTab  brief={brief} />}
              {activeTab === 'ai'        && (
                <AIBriefTab
                  brief={brief}
                  loading={loading}
                  onGenerate={() => load(false, true)}
                />
              )}
            </div>
          </>
        ) : brief?.status === 'error' ? (
          <div className="glass-card veto-glow p-8 text-center mt-4">
            <p className="text-signal-red font-medium mb-2">Analysis Failed</p>
            <p className="text-xs text-muted-fg">{brief.error}</p>
            <button
              onClick={() => load(false, true)}
              className="mt-4 px-4 py-2 text-xs border border-white/20 rounded-lg hover:border-electric-blue/40 text-muted-fg"
            >
              Retry
            </button>
          </div>
        ) : (
          /* Loading skeleton tabs */
          <div>
            <div className="glass-card border border-white/10 h-10 mb-4 flex items-center px-4 gap-6">
              {EQUITY_TABS.map(t => (
                <div key={t.id} className="skeleton h-3 w-16 rounded" />
              ))}
            </div>
            <div className="space-y-4">
              {[1,2,3].map(i => (
                <div key={i} className="glass-card p-5 space-y-3">
                  <div className="skeleton h-3 w-1/4" />
                  <div className="grid grid-cols-4 gap-3">
                    {[1,2,3,4].map(j => (
                      <div key={j} className="glass-card p-4 space-y-2">
                        <div className="skeleton h-2 w-2/3" />
                        <div className="skeleton h-8 w-full" />
                        <div className="skeleton h-2 w-1/2" />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {statusMsg && (
              <div className="flex items-center gap-2 mt-4 text-xs text-muted-fg">
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
