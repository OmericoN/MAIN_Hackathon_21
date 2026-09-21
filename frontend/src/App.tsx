import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/UI'
import { AuthProvider, useAuth } from './context/AuthContext'
import { AuthScreen } from './screens/AuthScreen'
import { DashboardScreen } from './screens/DashboardScreen'
import { OnboardingScreen } from './screens/OnboardingScreen'
import { PantryScreen } from './screens/PantryScreen'
import { PlanBuilderScreen } from './screens/PlanBuilderScreen'
import { PlanDetailScreen } from './screens/PlanDetailScreen'
import { ProfileScreen } from './screens/ProfileScreen'
import { RecipeScreen } from './screens/RecipeScreen'
import { ScanScreen } from './screens/ScanScreen'
import { SummaryScreen } from './screens/SummaryScreen'
import './App.css'

function ProtectedRoute() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="app-frame"><LoadingState /></div>
  if (!user) return <Navigate to="/auth" replace state={{ from: location }} />
  return <AppShell />
}

function AppRoutes() {
  return <Routes>
    <Route path="/auth" element={<AuthScreen />} />
    <Route path="/onboarding" element={<OnboardingScreen />} />
    <Route element={<ProtectedRoute />}>
      <Route index element={<DashboardScreen />} />
      <Route path="plan/new" element={<PlanBuilderScreen />} />
      <Route path="plans/:id" element={<PlanDetailScreen />} />
      <Route path="recipes/:id" element={<RecipeScreen />} />
      <Route path="scan" element={<ScanScreen />} />
      <Route path="pantry" element={<PantryScreen />} />
      <Route path="summary/:week" element={<SummaryScreen />} />
      <Route path="profile" element={<ProfileScreen />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
}

export default function App() {
  return <BrowserRouter><AuthProvider><AppRoutes /></AuthProvider></BrowserRouter>
}
