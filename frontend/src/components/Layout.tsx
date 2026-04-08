import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const NAV = [
  { to: '/app',            icon: '🏠', label: 'Home'       },
  { to: '/app/documents',  icon: '📄', label: 'Documents'  },
  { to: '/app/reports',    icon: '📋', label: 'Reports'    },
  { to: '/app/evals',      icon: '📊', label: 'Evals'      },
  { to: '/app/compliance', icon: '🇪🇺', label: 'Compliance' },
]

export default function Layout() {
  const { user, isAdmin, signOut } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleSignOut = async () => {
    await signOut()
    navigate('/auth')
  }

  const sidebarW = collapsed ? 'w-14' : 'w-56'
  const mainML  = collapsed ? 'md:ml-14' : 'md:ml-56'

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-30 z-20 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed h-full z-30 flex flex-col
          bg-white border-r border-gray-200
          transition-all duration-200
          ${sidebarW}
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
        `}
      >
        {/* Logo + collapse toggle */}
        <div className="p-3 border-b border-gray-100 flex items-center justify-between min-h-[57px]">
          {!collapsed && (
            <div className="flex items-center gap-2 overflow-hidden">
              <span className="text-2xl flex-shrink-0">🇪🇺</span>
              <div className="min-w-0">
                <div className="text-xs font-bold text-gray-900 leading-tight truncate">RegulIQ</div>
                <div className="text-xs text-gray-400 leading-tight truncate">Intelligence Agent</div>
              </div>
            </div>
          )}
          {collapsed && <span className="text-2xl mx-auto">🇪🇺</span>}
          <button
            onClick={() => setCollapsed(c => !c)}
            className="hidden md:flex ml-auto flex-shrink-0 p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? '▶' : '◀'}
          </button>
        </div>

        {/* Nav links */}
        <nav className="flex-1 p-2 space-y-0.5">
          {NAV.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/app'}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700 border border-blue-100'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                }`
              }
            >
              <span className="text-base flex-shrink-0">{icon}</span>
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          ))}

          {isAdmin && (
            <NavLink
              to="/app/admin"
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-red-50 text-red-700 border border-red-100'
                    : 'text-red-500 hover:text-red-700 hover:bg-red-50'
                }`
              }
            >
              <span className="text-base flex-shrink-0">⚙️</span>
              {!collapsed && <span className="truncate">Admin</span>}
            </NavLink>
          )}
        </nav>

        {/* User + sign out */}
        <div className="p-2 border-t border-gray-100">
          {!collapsed && (
            <div className="text-xs text-gray-400 truncate mb-2 px-1">{user?.email}</div>
          )}
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                       text-gray-500 hover:text-gray-900 hover:bg-gray-50 transition-colors"
            title="Sign out"
          >
            <span className="flex-shrink-0">→</span>
            {!collapsed && <span>Sign out</span>}
          </button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-20 bg-white border-b border-gray-200 flex items-center px-3 py-2 gap-3">
        <button
          onClick={() => setMobileOpen(o => !o)}
          className="p-2 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-colors"
        >
          ☰
        </button>
        <span className="text-sm font-bold text-gray-900">RegulIQ</span>
      </div>

      {/* Main content */}
      <main className={`flex-1 min-h-screen bg-gray-50 transition-all duration-200 ${mainML} pt-12 md:pt-0`}>
        <Outlet />
      </main>
    </div>
  )
}
