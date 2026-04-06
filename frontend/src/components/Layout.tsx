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

  const handleSignOut = async () => {
    await signOut()
    navigate('/auth')
  }

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col fixed h-full z-10">
        {/* Logo */}
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🇪🇺</span>
            <div>
              <div className="text-xs font-bold text-white leading-tight">EU Regulatory</div>
              <div className="text-xs text-gray-400 leading-tight">Intelligence Agent</div>
            </div>
          </div>
        </div>

        {/* Nav links */}
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`
              }
            >
              <span className="text-base">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User + sign out */}
        <div className="p-3 border-t border-gray-800">
          <div className="text-xs text-gray-500 truncate mb-2 px-1">{user?.email}</div>
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                       text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            <span>→</span> Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 ml-56 min-h-screen">
        <Outlet />
      </main>
    </div>
  )
}
