import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import Layout from './components/Layout'
import AuthPage from './pages/AuthPage'
import HomePage from './pages/HomePage'
import ProgressPage from './pages/ProgressPage'
import ReportsPage from './pages/ReportsPage'
import DocumentsPage from './pages/DocumentsPage'
import EvalsPage from './pages/EvalsPage'
import CompliancePage from './pages/CompliancePage'
import AdminPage from './pages/AdminPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div className="flex items-center justify-center min-h-screen bg-gray-950">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <div className="text-gray-400 text-sm">Loading...</div>
      </div>
    </div>
  )
  if (!user) return <Navigate to="/auth" replace />
  return <>{children}</>
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, isAdmin, loading, adminLoading } = useAuth()

  // Wait for BOTH auth and the role check to finish before deciding
  if (loading || adminLoading) return (
    <div className="flex items-center justify-center min-h-screen bg-gray-950">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
        <div className="text-gray-500 text-xs">Verifying access...</div>
      </div>
    </div>
  )
  if (!user) return <Navigate to="/auth" replace />
  if (!isAdmin) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/auth" element={<AuthPageWrapper />} />
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<HomePage />} />
        <Route path="progress/:runId" element={<ProgressPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/:runId" element={<ReportsPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="evals" element={<EvalsPage />} />
        <Route path="compliance" element={<CompliancePage />} />
        <Route path="compliance/:runId" element={<CompliancePage />} />
        <Route path="admin" element={<AdminRoute><AdminPage /></AdminRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function AuthPageWrapper() {
  const { user, loading } = useAuth()
  if (loading) return (
    <div className="flex items-center justify-center min-h-screen bg-gray-950">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <div className="text-gray-400 text-sm">Signing you in...</div>
      </div>
    </div>
  )
  if (user) return <Navigate to="/" replace />
  return <AuthPage />
}
