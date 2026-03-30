import { ReactNode } from 'react'
import { HudTopBar } from './HudTopBar'
import { useApp } from '@/context/AppContext'

export function Layout({ children }: { children: ReactNode }) {
  const { logout } = useApp()

  return (
    <div className="min-h-screen bg-background bg-radial-subtle">
      <HudTopBar onDisconnect={logout} />
      <main>{children}</main>
    </div>
  )
}
