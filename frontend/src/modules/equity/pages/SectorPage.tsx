import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { sectorColor, fmt, fmtCr } from '../lib/utils'
import { SectionHeader, EmptyState } from '../ui'
import type { SectorProfile } from '../lib/types'

export function SectorPage() {
  const { sector } = useParams<{ sector?: string }>()
  const nav = useNavigate()
  const [profiles, setProfiles] = useState<SectorProfile[]>([])
  const [loading,  setLoading]  = useState(false)

  useEffect(() => {
    setLoading(true)
    api.getSectors()
      .then(r => setProfiles(r.sectors))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="pt-16 px-4 pb-8 max-w-[1200px] mx-auto">
      <div className="text-center py-16 text-muted-fg text-sm">Loading sectors...</div>
    </div>
  )

  return (
    <div className="pt-16 px-4 pb-8 max-w-[1200px] mx-auto">
      <div className="mb-6">
        <p className="text-header">Sector Intelligence</p>
        <h1 className="text-xl font-bold mt-1">8 Sectors — Calibrated Profiles</h1>
        <p className="text-sm text-muted-fg mt-1">
          Causal rules, early warning thresholds, break scenarios, and hidden alpha — all Python-computed
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {profiles.filter(p => p.key !== 'diversified').map(p => (
          <div key={p.key} className="glass-card p-5 hover:border-white/20 transition-colors cursor-pointer"
            onClick={() => nav(`/`)}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold">{p.key.replace('_',' ').toUpperCase()}</h2>
              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${sectorColor(p.key)}`}>
                {p.key.replace('_',' ')}
              </span>
            </div>

            <p className="text-[12px] text-muted-fg leading-relaxed mb-4 line-clamp-3">
              {p.value_driver}
            </p>

            {/* Normal ranges */}
            <div className="grid grid-cols-2 gap-3 mb-3">
              {p.normal_roce && (
                <div className="bg-secondary rounded p-2">
                  <p className="text-[9px] text-muted-fg uppercase mb-1">Normal ROCE</p>
                  <p className="font-mono-data text-xs font-bold">
                    {p.normal_roce[0]}–{p.normal_roce[1]}%
                  </p>
                </div>
              )}
              {p.normal_margin && p.normal_margin[0] != null && (
                <div className="bg-secondary rounded p-2">
                  <p className="text-[9px] text-muted-fg uppercase mb-1">Normal Margin</p>
                  <p className="font-mono-data text-xs font-bold">
                    {p.normal_margin[0]}–{p.normal_margin[1]}%
                  </p>
                </div>
              )}
            </div>

            {/* Peers */}
            {p.peers.length > 0 && (
              <div>
                <p className="text-[9px] text-muted-fg uppercase mb-1">Coverage</p>
                <p className="text-[11px] text-muted-fg">{p.peers.join(' · ')}</p>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-8 glass-card p-5 border-l-2 border-l-electric-blue">
        <SectionHeader title="About Sector Intelligence" />
        <p className="text-[13px] text-muted-fg leading-relaxed">
          Each sector profile contains domain knowledge encoded as Python rules — not LLM interpretation.
          Thresholds are calibrated from actual Indian market stress events: IL&FS (2018), COVID (2020),
          the rate cycle (2022), and sector-specific events going back to FY2009.
          Pattern recognition fires when a company's computed metrics cross these thresholds.
          The LLM only synthesises the verdict — all the intelligence work is done by Python first.
        </p>
      </div>
    </div>
  )
}
