import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppProvider, useApp } from '@/context/AppContext'
import { LoginScreen }      from '@/components/LoginScreen'
import { Layout }           from '@/components/Layout'
import { HomePage }         from '@/pages/HomePage'
import { SubscriptionPage } from '@/pages/SubscriptionPage'
import { VolguardModule }   from '@/modules/volguard/VolguardModule'
import { MFModule }         from '@/modules/mf/MFModule'
import { EquityModule }     from '@/modules/equity/EquityModule'
import { TaxModule }        from '@/modules/tax/TaxModule'

function AppRoutes() {
  const { isAuthenticated } = useApp()

  if (!isAuthenticated) {
    return <LoginScreen />
  }

  return (
    <Layout>
      <Routes>
        <Route path="/"             element={<HomePage />} />
        <Route path="/home"         element={<HomePage />} />
        <Route path="/volguard"     element={<VolguardModule />} />
        <Route path="/mf/*"         element={<MFModule />} />
        <Route path="/equity/*"     element={<EquityModule />} />
        <Route path="/tax"          element={<TaxModule />} />
        <Route path="/subscription" element={<SubscriptionPage />} />
        <Route path="*"             element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <AppRoutes />
        <Toaster position="bottom-right" theme="dark" richColors />
      </BrowserRouter>
    </AppProvider>
  )
}
