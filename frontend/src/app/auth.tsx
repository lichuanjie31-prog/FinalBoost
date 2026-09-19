import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { refreshSession, request, setToken } from '../api/client'

import type { components } from '../api/generated'
export type User = components['schemas']['UserOut']
const AuthContext = createContext<{ user: User | null; loading: boolean; accept: (token: string, user: User) => void; logout: () => Promise<void> }>(null!)
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    refreshSession().then(async ok => {
      if (ok) { const u = await request<User>('/auth/me'); if (alive) setUser(u) }
    }).catch(() => {}).finally(() => { if (alive) setLoading(false) })
    const expired = () => { setToken(null); setUser(null) }
    window.addEventListener('session-expired', expired)
    return () => { alive = false; window.removeEventListener('session-expired', expired) }
  }, [])
  function accept(token: string, u: User) { setToken(token); setUser(u) }
  async function logout() {
    await request('/auth/logout', { method: 'POST' })
    setToken(null); setUser(null)
  }
  return <AuthContext value={{ user, loading, accept, logout }}>{children}</AuthContext>
}
export const useAuth = () => useContext(AuthContext)
export function safeNext(value: string | null) {
  if (!value) return '/app'
  const [path] = value.split('?',1)
  const allowed = /^\/app(?:$|\/exams\/[a-zA-Z0-9_-]+$|\/question-bank(?:$|\/upload$|\/public$|\/papers\/[a-zA-Z0-9_-]+$)|\/admin\/question-bank(?:$|\/upload$))/.test(path)
  return allowed && !value.startsWith('//') ? value : '/app'
}
