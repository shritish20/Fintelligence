/**
 * useAuth — thin wrapper around AppContext for components that only
 * need auth state, not the full app context.
 */
import { useApp } from '@/context/AppContext'

export function useAuth() {
  const { isAuthenticated, user, logout } = useApp()
  return {
    isAuthenticated,
    user,
    token: user?.accessToken ?? null,
    logout,
  }
}
