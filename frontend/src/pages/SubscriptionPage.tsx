import { useState, useEffect } from 'react'
import { useApp } from '@/context/AppContext'

const STORAGE_KEY = 'fintelligence_user'
function getJWT(): string | null {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')?.accessToken ?? null } catch { return null }
}

interface Plan {
  tier: string
  label: string
  amount_inr: number
  amount_paise: number
  months: number
}

interface SubscriptionStatus {
  tier: string
  expires_at: string | null
  is_active: boolean
}

declare global {
  interface Window { Razorpay: any }
}

export function SubscriptionPage() {
  const { user } = useApp()
  const [plans, setPlans]   = useState<Plan[]>([])
  const [status, setStatus] = useState<SubscriptionStatus | null>(null)
  const [rzpKey, setRzpKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [paying, setPaying]   = useState<string | null>(null)
  const [msg, setMsg]         = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    loadData()
    // Inject Razorpay.js script
    if (!document.getElementById('rzp-script')) {
      const s = document.createElement('script')
      s.id  = 'rzp-script'
      s.src = 'https://checkout.razorpay.com/v1/checkout.js'
      document.head.appendChild(s)
    }
  }, [])

  async function loadData() {
    setLoading(true)
    try {
      const jwt = getJWT()
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (jwt) headers['Authorization'] = `Bearer ${jwt}`

      const [plansRes, statusRes] = await Promise.allSettled([
        fetch('/api/subscription/plans').then(r => r.json()),
        fetch('/api/subscription/status', { headers }).then(r => r.json()),
      ])

      if (plansRes.status === 'fulfilled') {
        setPlans(plansRes.value.plans ?? [])
        setRzpKey(plansRes.value.razorpay_key_id ?? '')
      }
      if (statusRes.status === 'fulfilled' && !statusRes.value.detail) {
        setStatus(statusRes.value)
      }
    } catch {}
    finally { setLoading(false) }
  }

  async function handleSubscribe(plan: Plan) {
    if (!user) return
    setPaying(plan.tier)
    setMsg(null)
    try {
      const jwt = getJWT()
      const headers = { 'Content-Type': 'application/json', ...(jwt ? { Authorization: `Bearer ${jwt}` } : {}) }

      // 1. Create Razorpay order
      const orderRes = await fetch('/api/subscription/create-order', {
        method: 'POST', headers,
        body: JSON.stringify({ tier: plan.tier }),
      })
      const order = await orderRes.json()
      if (!orderRes.ok) { setMsg({ type: 'error', text: order.detail || 'Failed to create order' }); return }

      // 2. Open Razorpay checkout
      const rzp = new window.Razorpay({
        key:         rzpKey || order.key_id,
        amount:      order.amount_paise,
        currency:    'INR',
        name:        'Fintelligence',
        description: plan.label,
        order_id:    order.order_id,
        prefill: {
          email: user.email,
        },
        theme: { color: '#00d4ff' },
        handler: async (response: any) => {
          // 3. Verify payment server-side
          const verifyRes = await fetch('/api/subscription/verify-payment', {
            method: 'POST', headers,
            body: JSON.stringify({
              razorpay_order_id:   response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature:  response.razorpay_signature,
            }),
          })
          const result = await verifyRes.json()
          if (verifyRes.ok) {
            setMsg({ type: 'success', text: result.message || `Welcome to ${plan.tier.toUpperCase()}!` })
            await loadData()
          } else {
            setMsg({ type: 'error', text: result.detail || 'Payment verification failed — contact support' })
          }
        },
        modal: {
          ondismiss: () => setPaying(null),
        },
      })
      rzp.open()
    } catch (e: any) {
      setMsg({ type: 'error', text: e.message || 'Payment failed' })
    } finally {
      setPaying(null)
    }
  }

  const FEATURES: Record<string, string[]> = {
    free: [
      'MF Intel — read cached analyses (no new triggers)',
      'Equity Intel — read cached analyses (no new triggers)',
      'Tax module — upload & analyse',
      'Intelligence layer — morning brief (read only)',
    ],
    pro: [
      'Everything in Free, plus:',
      'Volguard — full options intelligence',
      'Live positions & P&L (broker token required)',
      'Journal Coach & AI veto analysis',
      'Unlimited MF & Equity briefs',
      'Push notifications — 8:47 AM TONE alert',
      'Priority support',
    ],
    team: [
      'Everything in Pro, plus:',
      'Up to 5 user seats',
      'Shared portfolio view',
      'Team journal & strategy log',
      'Admin dashboard',
    ],
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-muted-foreground text-sm animate-pulse">Loading plans...</div>
      </div>
    )
  }

  const currentTier = status?.tier ?? 'free'
  const expiresAt   = status?.expires_at ? new Date(status.expires_at).toLocaleDateString('en-IN') : null

  return (
    <div className="max-w-4xl mx-auto px-4 py-10 space-y-8">

      {/* Header */}
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-black tracking-tight text-foreground">Fintelligence Plans</h1>
        <p className="text-sm text-muted-foreground">
          Professional-grade trading intelligence for Indian markets.
        </p>
        {status?.is_active && expiresAt && (
          <p className="text-xs text-neon-green bg-neon-green/10 border border-neon-green/20 rounded px-3 py-1 inline-block">
            {currentTier.toUpperCase()} active — renews {expiresAt}
          </p>
        )}
      </div>

      {/* Message banner */}
      {msg && (
        <div className={`rounded-lg px-4 py-3 text-sm font-medium ${
          msg.type === 'success'
            ? 'bg-neon-green/10 border border-neon-green/30 text-neon-green'
            : 'bg-signal-red/10 border border-signal-red/30 text-signal-red'
        }`}>
          {msg.text}
        </div>
      )}

      {/* Plan cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* Free tier */}
        <div className={`glass-card rounded-xl p-6 border flex flex-col gap-4 ${
          currentTier === 'free' ? 'border-white/20' : 'border-white/10'
        }`}>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Free</span>
              {currentTier === 'free' && (
                <span className="text-[10px] font-bold text-electric-blue bg-electric-blue/10 border border-electric-blue/20 rounded px-2 py-0.5">CURRENT</span>
              )}
            </div>
            <div className="text-3xl font-black text-foreground">₹0</div>
            <div className="text-xs text-muted-foreground">Forever</div>
          </div>
          <ul className="space-y-2 flex-1">
            {FEATURES.free.map(f => (
              <li key={f} className="flex items-start gap-2 text-xs text-muted-foreground">
                <span className="text-neon-green mt-0.5 shrink-0">✓</span>{f}
              </li>
            ))}
          </ul>
          <button disabled className="w-full py-2 rounded text-xs font-bold uppercase tracking-wider bg-secondary text-muted-foreground cursor-default">
            Current Plan
          </button>
        </div>

        {/* Paid plans from API */}
        {plans.map(plan => {
          const isCurrentPlan = currentTier === plan.tier
          const isPaying      = paying === plan.tier
          const features      = FEATURES[plan.tier] ?? []
          const isPro         = plan.tier === 'pro'

          return (
            <div key={plan.tier} className={`glass-card rounded-xl p-6 border flex flex-col gap-4 relative ${
              isPro
                ? 'border-electric-blue/40 bg-electric-blue/5'
                : 'border-white/10'
            }`}>
              {isPro && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-electric-blue text-black text-[10px] font-black uppercase tracking-widest px-3 py-0.5 rounded-full">
                  Most Popular
                </div>
              )}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-xs font-bold uppercase tracking-widest ${isPro ? 'text-electric-blue' : 'text-muted-foreground'}`}>
                    {plan.tier}
                  </span>
                  {isCurrentPlan && (
                    <span className="text-[10px] font-bold text-neon-green bg-neon-green/10 border border-neon-green/20 rounded px-2 py-0.5">ACTIVE</span>
                  )}
                </div>
                <div className="text-3xl font-black text-foreground">
                  ₹{plan.amount_inr.toLocaleString('en-IN')}
                </div>
                <div className="text-xs text-muted-foreground">per month</div>
              </div>

              <ul className="space-y-2 flex-1">
                {features.map(f => (
                  <li key={f} className="flex items-start gap-2 text-xs text-muted-foreground">
                    <span className={`mt-0.5 shrink-0 ${f.startsWith('Everything') ? 'text-electric-blue' : 'text-neon-green'}`}>✓</span>{f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => handleSubscribe(plan)}
                disabled={isCurrentPlan || !!paying}
                className={`w-full py-2.5 rounded text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-default ${
                  isPro
                    ? 'bg-electric-blue hover:bg-electric-blue/80 text-black'
                    : 'bg-secondary hover:bg-secondary/80 text-foreground border border-white/10'
                }`}
              >
                {isPaying ? 'Processing...' : isCurrentPlan ? 'Current Plan' : `Subscribe — ₹${plan.amount_inr.toLocaleString('en-IN')}/mo`}
              </button>
            </div>
          )
        })}
      </div>

      <p className="text-center text-xs text-muted-foreground">
        Payments secured by Razorpay · Cancel anytime · No auto-renewal
      </p>
    </div>
  )
}
