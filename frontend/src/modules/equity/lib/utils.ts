export const fmt = (v: number|null|undefined, suf='%', dp=1) =>
  v == null || isNaN(v) ? 'N/A' : `${v.toFixed(dp)}${suf}`

export const fmtCr = (v: number|null|undefined) => {
  if (v == null || isNaN(v)) return 'N/A'
  if (v >= 100000) return `₹${(v/100000).toFixed(1)}L Cr`
  if (v >= 1000)   return `₹${(v/1000).toFixed(1)}K Cr`
  return `₹${v.toFixed(0)} Cr`
}

export const fmtSign = (v: number|null|undefined, suf='%', dp=1) =>
  v == null || isNaN(v) ? 'N/A'
  : `${v >= 0 ? '+' : ''}${v.toFixed(dp)}${suf}`

export const colorVal = (v: number|null|undefined, invert=false) => {
  if (v == null || isNaN(v)) return 'text-muted-fg'
  if (invert) return v > 0 ? 'text-signal-red' : v < 0 ? 'text-neon-green' : 'text-foreground'
  return v > 0 ? 'text-neon-green' : v < 0 ? 'text-signal-red' : 'text-foreground'
}

export const convictionClass = (c?: string) => {
  if (!c) return 'conv-buy'
  const l = c.toLowerCase()
  if (l.includes('strong')) return 'conv-strong'
  if (l.includes('buy'))    return 'conv-buy'
  if (l.includes('watch'))  return 'conv-watch'
  if (l.includes('avoid'))  return 'conv-avoid'
  return 'conv-buy'
}

export const signalClass = (s?: string) => {
  const l = (s || '').toLowerCase()
  if (l === 'strength') return 'sig-strength'
  if (l === 'warning')  return 'sig-warning'
  if (l === 'normal')   return 'sig-normal'
  if (l === 'positive') return 'sig-positive'
  if (l === 'info')     return 'sig-info'
  return 'sig-neutral'
}

export const sectorColor = (s?: string) => {
  const map: Record<string,string> = {
    paints:       'text-electric-blue bg-electric-blue/10 border-electric-blue/30',
    it_services:  'text-neon-green bg-neon-green/10 border-neon-green/30',
    private_bank: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
    fmcg:         'text-orange-400 bg-orange-400/10 border-orange-400/30',
    cement:       'text-silver bg-silver/10 border-silver/30',
    pharma:       'text-purple-400 bg-purple-400/10 border-purple-400/30',
    auto_oem:     'text-cyan-400 bg-cyan-400/10 border-cyan-400/30',
    nbfc:         'text-pink-400 bg-pink-400/10 border-pink-400/30',
  }
  return map[s || ''] || 'text-muted-fg bg-secondary border-white/10'
}

export const relativeTime = (iso?: string) => {
  if (!iso) return ''
  const h = Math.floor((Date.now() - new Date(iso).getTime()) / 3600000)
  if (h < 1) return 'just now'
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h/24)}d ago`
}

export const trendColor = (cur?: number|null, prev?: number|null, lowerBetter=false) => {
  if (cur == null || prev == null) return ''
  const up = cur > prev
  if (lowerBetter) return up ? 'bg-signal-red/8' : 'bg-neon-green/8'
  return up ? 'bg-neon-green/8' : 'bg-signal-red/8'
}
