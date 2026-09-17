import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import { Home } from '../features/landing/Home'
import { AuthPage } from '../features/auth/AuthPage'
import type { ReactNode } from 'react'
import { Workspace, WorkspaceLayout } from '../features/exams/Workspace'
import { ExamDetail } from '../features/exams/ExamDetail'
import { MockExam } from '../features/exams/MockExam'

export function Protected({ children }: { children: ReactNode }) {
  const auth = useAuth(), location = useLocation()
  if (auth.loading) return <main className="loading-screen" role="status">正在恢复登录状态…</main>
  if (!auth.user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  return children
}
export function App() {
  return <AuthProvider><a className="skip-link" href="#main">跳到主要内容</a><Routes><Route path="/" element={<Home />} /><Route path="/login" element={<AuthPage key="login" />} /><Route path="/register" element={<AuthPage key="register" register />} /><Route path="/app" element={<Protected><WorkspaceLayout><Workspace /></WorkspaceLayout></Protected>} /><Route path="/app/exams/:id" element={<Protected><WorkspaceLayout><ExamDetail /></WorkspaceLayout></Protected>} /><Route path="/app/exams/:id/mock" element={<Protected><WorkspaceLayout><MockExam /></WorkspaceLayout></Protected>} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></AuthProvider>
}
