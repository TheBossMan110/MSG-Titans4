'use client'

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { auth as authApi, errorMessage, setAccessToken, type User } from '@/lib/api'

interface AuthCtx {
  user: User | null
  loading: boolean
  error: string | null
  /** A user, or the step token when two-step sign-in asks for a code next. */
  login: (email: string, password: string) => Promise<User | { mfaToken: string }>
  completeMfa: (mfaToken: string, code: string) => Promise<User>
  register: (email: string, fullName: string, password: string) => Promise<User>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const bootstrapped = useRef(false)

  // On first mount, rotate the session through the proxy. No cookie means no
  // session, which is a normal state and not an error.
  useEffect(() => {
    if (bootstrapped.current) return
    bootstrapped.current = true
    ;(async () => {
      try {
        const ok = await authApi.refresh()
        if (ok) setUser(await authApi.me())
      } catch {
        setUser(null)
      } finally {
        setLoading(false)
      }
    })()

    const expired = () => {
      setUser(null)
      setAccessToken(null)
      setError('Your session has expired. Please sign in again.')
    }
    window.addEventListener('auth:expired', expired)
    return () => window.removeEventListener('auth:expired', expired)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setError(null)
    try {
      const res = await authApi.login(email, password)
      if ('mfa_required' in res) return { mfaToken: res.mfa_token }
      setUser(res.user)
      return res.user
    } catch (e) {
      setError(errorMessage(e))
      throw e
    }
  }, [])

  const completeMfa = useCallback(async (mfaToken: string, code: string) => {
    setError(null)
    try {
      const res = await authApi.loginMfa(mfaToken, code)
      setUser(res.user)
      return res.user
    } catch (e) {
      setError(errorMessage(e))
      throw e
    }
  }, [])

  const register = useCallback(async (email: string, fullName: string, password: string) => {
    setError(null)
    try {
      const res = await authApi.register(email, fullName, password)
      setUser(res.user)
      return res.user
    } catch (e) {
      setError(errorMessage(e))
      throw e
    }
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout()
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    setUser(await authApi.me())
  }, [])

  return <Ctx.Provider value={{ user, loading, error, login, completeMfa, register, logout, refreshUser }}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
