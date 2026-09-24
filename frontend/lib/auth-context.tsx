'use client'
import { createContext, useContext, useEffect, useRef, useState, ReactNode } from 'react'
import { auth as authApi, setAccessToken, User, ApiError } from '@/lib/api'

interface AuthCtx {
  user: User | null
  loading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const bootstrapped = useRef(false)

  // On mount: attempt silent token refresh then fetch /me
  useEffect(() => {
    if (bootstrapped.current) return
    bootstrapped.current = true
    ;(async () => {
      try {
        const res = await authApi.refresh()
        setAccessToken(res.access_token)
        setUser(res.user)
      } catch {
        // Not logged in — that is fine
        setUser(null)
      } finally {
        setLoading(false)
      }
    })()

    const handleExpired = () => {
      setUser(null)
      setAccessToken(null)
      setError('Your session has expired. Please sign in again.')
    }
    window.addEventListener('auth:expired', handleExpired)
    return () => window.removeEventListener('auth:expired', handleExpired)
  }, [])

  const login = async (email: string, password: string) => {
    setError(null)
    setLoading(true)
    try {
      const res = await authApi.login(email, password)
      setAccessToken(res.access_token)
      setUser(res.user)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Login failed. Please try again.'
      setError(msg)
      throw e
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    try { await authApi.logout() } catch {}
    setAccessToken(null)
    setUser(null)
  }

  return <Ctx.Provider value={{ user, loading, error, login, logout }}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
