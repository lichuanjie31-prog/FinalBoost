import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import { Home } from '../features/landing/Home'
import { AuthPage } from '../features/auth/AuthPage'
import type { ReactNode } from 'react'
import { Workspace, WorkspaceLayout } from '../features/exams/Workspace'
import { ExamDetail } from '../features/exams/ExamDetail'
import { PrivatePapersPage } from '../features/question-bank/PrivatePapersPage'
import { PrivatePaperDetailPage } from '../features/question-bank/PrivatePaperDetailPage'
import { UploadPaperPage } from '../features/question-bank/UploadPaperPage'
import { PublicPapersPage } from '../features/question-bank/PublicPapersPage'
import { AdminPapersPage } from '../features/question-bank/AdminPapersPage'
import { AdminUploadPage } from '../features/question-bank/AdminUploadPage'
import { Trainings } from '../features/training/Trainings'
import { TrainingDetail } from '../features/training/TrainingDetail'


export function Protected({ children }: { children?: ReactNode }) {
  const auth = useAuth(), location = useLocation()
  if (auth.loading) return <main className="loading-screen" role="status">正在恢复登录状态…</main>
  if (!auth.user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
  return children || <Outlet />
}
function AdminRoute() {
  const { user } = useAuth()
  return user?.role === 'admin' ? <Outlet /> : <Navigate to="/app/question-bank" replace />
}
export function App() {
  return <AuthProvider><a className="skip-link" href="#main">跳到主要内容</a><Routes><Route path="/" element={<Home />} /><Route path="/login" element={<AuthPage key="login" />} /><Route path="/register" element={<AuthPage key="register" register />} /><Route element={<Protected />}><Route path="/app" element={<WorkspaceLayout />}><Route index element={<Workspace />} /><Route path="exams/:id" element={<ExamDetail />} /><Route path="ai" element={<Navigate to="/app" replace />} /><Route path="trainings" element={<Trainings />} /><Route path="trainings/:id" element={<TrainingDetail />} /><Route path="question-bank" element={<PrivatePapersPage />} /><Route path="question-bank/upload" element={<UploadPaperPage />} /><Route path="question-bank/public" element={<PublicPapersPage />} /><Route path="question-bank/papers/:id" element={<PrivatePaperDetailPage />} /><Route element={<AdminRoute />}><Route path="admin/question-bank" element={<AdminPapersPage />} /><Route path="admin/question-bank/upload" element={<AdminUploadPage />} /></Route></Route></Route><Route path="*" element={<Navigate to="/" replace />} /></Routes></AuthProvider>

}
