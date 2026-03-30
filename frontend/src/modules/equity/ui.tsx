import React from 'react'
import { convictionClass, signalClass } from './lib/utils'

export function MetricRow({ label, value, cls='', sub }:{
  label:string; value:React.ReactNode; cls?:string; sub?:string
}) {
  return (
    <div className="flex justify-between items-baseline py-2.5 border-b border-white/5 last:border-0">
      <div>
        <span className="text-xs text-muted-fg">{label}</span>
        {sub && <span className="text-[9px] text-muted-fg ml-1 opacity-60">{sub}</span>}
      </div>
      <span className={`font-mono-data text-sm font-bold ${cls}`}>{value}</span>
    </div>
  )
}

export function SectionHeader({ title, sub, badge }:{
  title:string; sub?:string; badge?:React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div>
        <p className="text-header">{title}</p>
        {sub && <p className="text-[10px] text-muted-fg mt-0.5">{sub}</p>}
      </div>
      {badge}
    </div>
  )
}

export function ConvictionBadge({ conviction, reason, size='large' }:{
  conviction?:string; reason?:string; size?:'large'|'compact'
}) {
  const cls = convictionClass(conviction)
  if (size==='compact') return (
    <span className={`${cls} text-[10px] font-bold uppercase px-2 py-0.5 rounded border`}>
      {conviction || 'N/A'}
    </span>
  )
  return (
    <div className={`${cls} rounded-lg p-3 text-center border`}>
      <div className="text-xs font-bold tracking-widest uppercase">{conviction || 'N/A'}</div>
      {reason && <div className="text-[11px] mt-1.5 opacity-75 italic leading-snug">{reason}</div>}
    </div>
  )
}

export function SignalBadge({ signal }:{ signal?:string }) {
  return (
    <span className={`${signalClass(signal)} text-[10px] font-bold uppercase px-2 py-1 rounded border shrink-0`}>
      {signal || 'INFO'}
    </span>
  )
}

export function Skeleton({ cls='' }:{ cls?:string }) {
  return <div className={`skeleton ${cls}`} />
}

export function SkeletonCard() {
  return (
    <div className="glass-card p-5 space-y-3">
      <Skeleton cls="h-3 w-1/3" />
      <Skeleton cls="h-3 w-full" />
      <Skeleton cls="h-3 w-3/4" />
      <Skeleton cls="h-3 w-1/2" />
    </div>
  )
}

export function EmptyState({ icon='○', message, sub }:{
  icon?:string; message:string; sub?:string
}) {
  return (
    <div className="glass-card p-10 text-center">
      <div className="text-3xl text-muted-fg mb-3">{icon}</div>
      <p className="text-sm font-medium">{message}</p>
      {sub && <p className="text-xs text-muted-fg mt-1">{sub}</p>}
    </div>
  )
}

export function Tabs({ tabs, active, onChange }:{
  tabs:{id:string;label:string}[]; active:string; onChange:(id:string)=>void
}) {
  return (
    <div className="glass-card border border-white/10 flex h-10 mb-4 overflow-x-auto">
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={`px-4 h-full text-[10px] uppercase tracking-widest font-semibold
            whitespace-nowrap shrink-0 transition-colors
            ${active===t.id ? 'tab-active' : 'tab-inactive'}`}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function SearchInput({ value, onChange, onSubmit, placeholder, loading=false }:{
  value:string; onChange:(v:string)=>void; onSubmit:()=>void
  placeholder?:string; loading?:boolean
}) {
  return (
    <div className="glass-card flex items-center gap-3 px-4 h-14 intel-glow">
      {loading
        ? <div className="w-5 h-5 border-2 border-electric-blue border-t-transparent rounded-full animate-spin shrink-0"/>
        : <svg className="w-5 h-5 text-electric-blue shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
          </svg>}
      <input value={value} onChange={e=>onChange(e.target.value)}
        onKeyDown={e=>e.key==='Enter'&&onSubmit()}
        placeholder={placeholder}
        className="flex-1 bg-transparent text-base text-foreground placeholder-muted-fg outline-none"/>
      {value && <button onClick={()=>onChange('')} className="text-muted-fg hover:text-foreground text-lg">×</button>}
    </div>
  )
}

export function ProgressBar({ pct, color='bg-electric-blue', label, valLabel }:{
  pct:number|null; color?:string; label?:string; valLabel?:string
}) {
  const w = Math.min(100, Math.max(0, pct ?? 0))
  return (
    <div className="flex items-center gap-3">
      {label && <span className="text-[10px] text-muted-fg w-24 shrink-0">{label}</span>}
      <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width:`${w}%` }}/>
      </div>
      {valLabel && <span className="font-mono-data text-xs text-muted-fg w-10 text-right shrink-0">{valLabel}</span>}
    </div>
  )
}
