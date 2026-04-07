import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { supabase } from '../lib/supabase'

const NAV = [
  { to: '/',           icon: '🏠', label: 'Home'       },
  { to: '/documents',  icon: '📄', label: 'Documents'  },
  { to: '/reports',    icon: '📋', label: 'Reports'    },
  { to: '/evals',      icon: '📊', label: 'Evals'      },
  { to: '/compliance', icon: '🇪🇺', label: 'Compliance' },
]

export default function Layout() {
  const { user, signOut } = useAuth()
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
    <div className="flex min-h-screen">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-60 z-20 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed h-full z-30 flex flex-col
          bg-gray-900 border-r border-gray-800
          transition-all duration-200
          ${sidebarW}
          ${
            mobileOpen
              ? 'translate-x-0'
              : '-translate-x-full md:translate-x-0'
          }
        `}
      >
        {/* Logo + collapse toggle */}
        <div className="p-3 border-b border-gray-800 flex items-center justify-between min-h-[57px]">
          {!collapsed && (
            <div className="flex items-center gap-2 overflow-hidden">
              <span className="text-2xl flex-shrink-0">🇪🇺</span>
              <div className="min-w-0">
                <div className="text-xs font-bold text-white leading-tight truncate">EU Regulatory</div>
                <div className="text-xs text-gray-400 leading-tight truncate">Intelligence Agent</div>
              </div>
            </div>
          )}
          {collapsed && <span className="text-2xl mx-auto">🇪🇺</span>}
          <button
            onClick={() => setCollapsed(c => !c)}
            className="hidden md:flex ml-auto flex-shrink-0 p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? '▶' : '◀'}
          </button>
        </div>

        {/* Nav links */}
        <nav className="flex-1 p-2 space-y-1">
          {NAV.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`
              }
            >
              <span className="text-base flex-shrink-0">{icon}</span>
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* User + sign out */}
        <div className="p-2 border-t border-gray-800">
          {!collapsed && (
            <div className="text-xs text-gray-500 truncate mb-2 px-1">{user?.email}</div>
          )}
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                       text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            title="Sign out"
          >
            <span className="flex-shrink-0">→</span>
            {!collapsed && <span>Sign out</span>}
          </button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-20 bg-gray-900 border-b border-gray-800 flex items-center px-3 py-2 gap-3">
        <button
          onClick={() => setMobileOpen(o => !o)}
          className="p-2 rounded text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
        >
          ☰
        </button>
        <span className="text-sm font-bold text-white">EU Regulatory Intelligence Agent</span>
      </div>

      {/* Main content */}
      <main className={`flex-1 min-h-screen transition-all duration-200 ${mainML} pt-12 md:pt-0`}>
        <Outlet />
      </main>
    </div>
  )
}
