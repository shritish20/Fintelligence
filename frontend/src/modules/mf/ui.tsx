import React from 'react'
import { convictionClass, convictionLabel, convictionStars } from './lib/utils'

// ── MetricRow ─────────────────────────────────────────────────────────────────
interface MetricRowProps {
  label: string
  value: React.ReactNode
  className?: string
  sublabel?: string
}
export function MetricRow({ label, value, className = '', sublabel }: MetricRowProps) {
  return (
    <div className="flex justify-between items-baseline py-2.5 border-b border-white/5 last:border-0">
      <div>
        <span className="text-xs text-muted-fg">{label}</span>
        {sublabel && <span className="text-[10px] text-muted-fg ml-1 opacity-60">{sublabel}</span>}
      </div>
      <span className={`font-mono-data text-sm font-bold ${className}`}>{value}</span>
    </div>
  )
}

// ── SectionHeader ─────────────────────────────────────────────────────────────
export function SectionHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-3">
      <p className="text-header">{title}</p>
      {sub && <p className="text-[10px] text-muted-fg mt-0.5">{sub}</p>}
    </div>
  )
}

// ── ConvictionBadge ───────────────────────────────────────────────────────────
export function ConvictionBadge({
  conviction,
  reason,
  size = 'large'
}: {
  conviction?: string
  reason?: string
  size?: 'large' | 'compact'
}) {
  const cls = convictionClass(conviction)
  const lbl = convictionLabel(conviction)
  const stars = convictionStars(conviction)

  if (size === 'compact') {
    return (
      <span className={`${cls} text-[10px] font-bold uppercase px-2 py-0.5 rounded border`}>
        {lbl}
      </span>
    )
  }

  return (
    <div className={`${cls} rounded-lg p-3 text-center border`}>
      <div className="text-xs font-bold tracking-widest uppercase">{lbl}</div>
      {stars && <div className="font-mono-data text-lg mt-0.5">{stars}</div>}
      {reason && <div className="text-[11px] mt-2 opacity-75 italic leading-snug">{reason}</div>}
    </div>
  )
}

// ── Skeleton ──────────────────────────────────────────────────────────────────
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} />
}

export function SkeletonCard() {
  return (
    <div className="glass-card p-5 space-y-3">
      <Skeleton className="h-3 w-2/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-3/4" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  )
}

// ── EmptyState ────────────────────────────────────────────────────────────────
export function EmptyState({ icon = '○', message, sub, action }: {
  icon?: string
  message: string
  sub?: string
  action?: React.ReactNode
}) {
  return (
    <div className="glass-card p-10 text-center">
      <div className="text-3xl text-muted-fg mb-3">{icon}</div>
      <div className="text-sm font-medium text-foreground">{message}</div>
      {sub && <div className="text-xs text-muted-fg mt-1">{sub}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

// ── StatCard ──────────────────────────────────────────────────────────────────
export function StatCard({
  label, value, sub, valueClass = 'text-foreground', glow = false
}: {
  label: string
  value: React.ReactNode
  sub?: string
  valueClass?: string
  glow?: boolean
}) {
  return (
    <div className={`glass-card p-4 ${glow ? 'intel-glow' : ''}`}>
      <p className="text-header mb-2">{label}</p>
      <p className={`font-mono-data text-3xl font-black ${valueClass}`}>{value}</p>
      {sub && <p className="text-[10px] text-muted-fg mt-1">{sub}</p>}
    </div>
  )
}

// ── ProgressBar ───────────────────────────────────────────────────────────────
export function ProgressBar({
  pct, color = 'bg-electric-blue', label, valueLabel
}: {
  pct: number | null
  color?: string
  label?: string
  valueLabel?: string
}) {
  const width = Math.min(100, Math.max(0, pct ?? 0))
  return (
    <div className="flex items-center gap-3">
      {label && <span className="text-[10px] text-muted-fg w-20 shrink-0">{label}</span>}
      <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${width}%` }}
        />
      </div>
      {valueLabel && (
        <span className="font-mono-data text-xs text-muted-fg w-10 text-right shrink-0">
          {valueLabel}
        </span>
      )}
    </div>
  )
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
interface TabItem { id: string; label: string }
export function Tabs({
  tabs, active, onChange
}: {
  tabs: TabItem[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className="glass-card border border-white/10 flex h-10 mb-4 overflow-x-auto">
      {tabs.map(t => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`px-4 h-full text-[10px] uppercase tracking-widest font-semibold whitespace-nowrap shrink-0 transition-colors
            ${active === t.id ? 'tab-active' : 'tab-inactive'}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

// ── FlagList ──────────────────────────────────────────────────────────────────
export function FlagList({ flags }: { flags?: { green: string[]; amber: string[]; red: string[] } }) {
  if (!flags) return null
  return (
    <div className="space-y-2">
      {flags.green?.length > 0 && (
        <div>
          <p className="text-[10px] text-neon-green uppercase tracking-wide font-semibold mb-1">POSITIVE</p>
          {flags.green.map((f, i) => (
            <div key={i} className="text-[12px] text-foreground flex gap-2 py-0.5">
              <span className="text-neon-green shrink-0">✓</span>{f}
            </div>
          ))}
        </div>
      )}
      {flags.amber?.length > 0 && (
        <div>
          <p className="text-[10px] text-yellow-400 uppercase tracking-wide font-semibold mb-1">WATCH</p>
          {flags.amber.map((f, i) => (
            <div key={i} className="text-[12px] text-foreground flex gap-2 py-0.5">
              <span className="text-yellow-400 shrink-0">⚠</span>{f}
            </div>
          ))}
        </div>
      )}
      {flags.red?.length > 0 && (
        <div>
          <p className="text-[10px] text-signal-red uppercase tracking-wide font-semibold mb-1">FLAGS</p>
          {flags.red.map((f, i) => (
            <div key={i} className="text-[12px] text-foreground flex gap-2 py-0.5">
              <span className="text-signal-red shrink-0">✗</span>{f}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── SearchInput ───────────────────────────────────────────────────────────────
export function SearchInput({
  value, onChange, onSubmit, placeholder, loading = false
}: {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  placeholder?: string
  loading?: boolean
}) {
  return (
    <div className="glass-card flex items-center gap-3 px-4 h-14 intel-glow">
      {loading ? (
        <div className="w-5 h-5 border-2 border-electric-blue border-t-transparent rounded-full animate-spin shrink-0" />
      ) : (
        <svg className="w-5 h-5 text-electric-blue shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      )}
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && onSubmit()}
        placeholder={placeholder}
        className="flex-1 bg-transparent text-base text-foreground placeholder-muted-fg outline-none"
      />
      {value && (
        <button onClick={() => onChange('')} className="text-muted-fg hover:text-foreground text-lg">×</button>
      )}
    </div>
  )
}
