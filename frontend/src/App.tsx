import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import AppLayout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import AgentCreate from './pages/AgentCreate'
import Settings from './pages/Settings'
import Login from './pages/Login'
import Approvals from './pages/Approvals'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const token = localStorage.getItem('token')
  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="agents" element={<Agents />} />
        <Route path="agents/create" element={<AgentCreate />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
