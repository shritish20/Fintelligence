import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function fmt(v: number | null | undefined, suffix = '%', decimals = 1): string {
  if (v == null || isNaN(v)) return 'N/A'
  return `${v.toFixed(decimals)}${suffix}`
}

export function fmtCr(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return 'N/A'
  if (v >= 100000) return `₹${(v / 100000).toFixed(1)}L Cr`
  if (v >= 1000)   return `₹${(v / 1000).toFixed(1)}K Cr`
  return `₹${v.toFixed(0)} Cr`
}

export function fmtINR(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return 'N/A'
  if (Math.abs(v) >= 100_000) return `₹${(v / 100_000).toFixed(2)}L`
  if (Math.abs(v) >= 1_000)   return `₹${(v / 1_000).toFixed(1)}K`
  return `₹${v.toFixed(0)}`
}

export function fmtSign(v: number | null | undefined, suffix = '%', decimals = 1): string {
  if (v == null || isNaN(v)) return 'N/A'
  const s = v >= 0 ? '+' : ''
  return `${s}${v.toFixed(decimals)}${suffix}`
}

export function colorVal(v: number | null | undefined, invert = false): string {
  if (v == null || isNaN(v)) return 'text-muted-foreground'
  if (invert) return v > 0 ? 'text-signal-red' : v < 0 ? 'text-neon-green' : 'text-foreground'
  return v > 0 ? 'text-neon-green' : v < 0 ? 'text-signal-red' : 'text-foreground'
}

export function convictionClass(conviction: string | undefined): string {
  if (!conviction) return ''
  const c = conviction.toLowerCase()
  if (c.includes('high') || c.includes('sound'))       return 'conviction-high'
  if (c.includes('moderate') || c.includes('adequate')) return 'conviction-moderate'
  if (c.includes('low') || c.includes('review'))       return 'conviction-low'
  if (c.includes('avoid'))                             return 'conviction-avoid'
  return 'conviction-moderate'
}

export function convictionStars(conviction: string | undefined): string {
  if (!conviction) return ''
  if (conviction.includes('★★★★')) return '★★★★'
  if (conviction.includes('★★★'))  return '★★★☆'
  if (conviction.includes('★★'))   return '★★☆☆'
  if (conviction.includes('★'))    return '★☆☆☆'
  return ''
}

export function convictionLabel(conviction: string | undefined): string {
  if (!conviction) return 'N/A'
  return conviction.replace(/★.*/g, '').trim()
}

export function categoryColor(category: string | undefined): string {
  const c = (category || '').toLowerCase()
  if (c.includes('debt') || c.includes('bond') || c.includes('liquid') ||
      c.includes('duration') || c.includes('gilt') || c.includes('credit'))
    return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30'
  if (c.includes('hybrid') || c.includes('balanced'))
    return 'text-silver bg-silver/10 border-silver/30'
  return 'text-electric-blue bg-electric-blue/10 border-electric-blue/30'
}

export function relativeTime(iso: string | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  const h = Math.floor(diff / 3600000)
  if (h < 1) return 'just now'
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function colorAmt(v: number | null | undefined, invert = false): string {
  if (v == null || isNaN(v)) return 'text-muted-fg'
  if (invert) return v > 0 ? 'text-signal-red' : v < 0 ? 'text-neon-green' : 'text-foreground'
  return v > 0 ? 'text-neon-green' : v < 0 ? 'text-signal-red' : 'text-foreground'
}

export function flagColor(priority: string) {
  if (priority === 'URGENT') return 'text-signal-red'
  if (priority === 'WATCH')  return 'text-yellow-400'
  return 'text-neon-green'
}

export function flagIcon(priority: string) {
  if (priority === 'URGENT') return '🔴'
  if (priority === 'WATCH')  return '🟡'
  return '🟢'
}

export function flagClass(priority: string) {
  if (priority === 'URGENT') return 'flag-urgent'
  if (priority === 'WATCH')  return 'flag-watch'
  return 'flag-green'
}

export function fmtINRFull(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return 'N/A'
  return `₹${Math.abs(v).toLocaleString('en-IN')}`
}
