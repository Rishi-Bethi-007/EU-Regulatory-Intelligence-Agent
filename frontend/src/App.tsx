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

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()

  // Show loading spinner while Supabase processes the session
  // This covers the OAuth callback case where tokens arrive in the URL hash
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

export default function App() {
  // Do NOT block rendering on loading here — that prevents the OAuth
  // callback URL hash from being processed by Supabase JS before React Router
  // redirects away from /auth. Let routes render immediately and handle
  // loading state inside ProtectedRoute and AuthPage individually.
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
  </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

// Separate wrapper so AuthPage can handle its own loading/redirect logic
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

  // If user is already authenticated (including after OAuth callback),
  // redirect to home
  if (user) return <Navigate to="/" replace />

  return <AuthPage />
}
