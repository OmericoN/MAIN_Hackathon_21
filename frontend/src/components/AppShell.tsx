import { Camera, CalendarDays, Home, PackageOpen, UserRound } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const items = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/plan/new', label: 'Plan', icon: CalendarDays },
  { to: '/scan', label: 'Scan', icon: Camera, featured: true },
  { to: '/pantry', label: 'Pantry', icon: PackageOpen },
  { to: '/profile', label: 'Profile', icon: UserRound },
]

export function AppShell() {
  const { isDemo } = useAuth()
  return <div className="app-frame">
    {isDemo ? <div className="demo-ribbon">Demo mode · connect Supabase for live data</div> : null}
    <main className="app-content"><Outlet /></main>
    <nav className="bottom-nav" aria-label="Primary navigation">
      {items.map(({ to, label, icon: Icon, end, featured }) => <NavLink key={to} to={to} end={end} className={({ isActive }) => `${isActive ? 'is-active' : ''} ${featured ? 'is-featured' : ''}`}><span><Icon aria-hidden="true" /></span><small>{label}</small></NavLink>)}
    </nav>
  </div>
}
