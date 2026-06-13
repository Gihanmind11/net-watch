import { useState, useEffect, useCallback } from 'react'
import type { PageId, AlertResponse, ScanResult, LoginResponse, User } from './types'
import TopBar from './components/TopBar'
import Sidebar from './components/Sidebar'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import DevicesPage from './pages/DevicesPage'
import TopologyPage from './pages/TopologyPage'
import TrafficPage from './pages/TrafficPage'
import PerformancePage from './pages/PerformancePage'
import AlertsPage from './pages/AlertsPage'
import AboutPage from './pages/AboutPage'

const API = 'http://localhost:5000/api'

const pageComponents: Record<PageId, React.FC> = {
  dashboard: DashboardPage,
  devices: DevicesPage,
  topology: TopologyPage,
  traffic: TrafficPage,
  performance: PerformancePage,
  alerts: AlertsPage,
  about: AboutPage,
}

export default function App() {
  // Auth state
  const [accessToken, setAccessToken] = useState<string | null>(() => localStorage.getItem('nw_access_token'))
  const [refreshToken, setRefreshToken] = useState<string | null>(() => localStorage.getItem('nw_refresh_token'))
  const [currentUser, setCurrentUser] = useState<User | null>(() => {
    const userStr = localStorage.getItem('nw_user')
    return userStr ? JSON.parse(userStr) : null
  })

  const [activePage, setActivePage] = useState<PageId>('dashboard')
  const [alertStats, setAlertStats] = useState({ critical: 0, warning: 0 })
  const [scanning, setScanning] = useState(false)
  const [scanVersion, setScanVersion] = useState(0)
  const [toast, setToast] = useState<string | null>(null)

  const authHeaders = accessToken ? { 'Authorization': `Bearer ${accessToken}`, 'Content-Type': 'application/json' } : {}

  const handleLogout = useCallback(async () => {
    try {
      if (refreshToken) {
        await fetch(`${API}/logout`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ refresh_token: refreshToken })
        })
      }
    } catch {
      // Ignore logout errors
    } finally {
      // Clear all stored auth data
      localStorage.removeItem('nw_access_token')
      localStorage.removeItem('nw_refresh_token')
      localStorage.removeItem('nw_user')
      setAccessToken(null)
      setRefreshToken(null)
      setCurrentUser(null)
    }
  }, [refreshToken])

  // Handle token refresh
  const refreshAccessToken = useCallback(async (): Promise<boolean> => {
    if (!refreshToken) return false
    try {
      const res = await fetch(`${API}/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken })
      })
      if (!res.ok) {
        handleLogout()
        return false
      }
      const data = await res.json()
      // Update stored data
      localStorage.setItem('nw_access_token', data.access_token)
      localStorage.setItem('nw_refresh_token', data.refresh_token)
      localStorage.setItem('nw_user', JSON.stringify(data.user))
      setAccessToken(data.access_token)
      setRefreshToken(data.refresh_token)
      setCurrentUser(data.user)
      return true
    } catch {
      handleLogout()
      return false
    }
  }, [refreshToken])

  // Check token validity on mount and handle 401s
  useEffect(() => {
    if (!accessToken) return
    const checkAuth = async () => {
      const res = await fetch(`${API}/alerts`, { headers: authHeaders })
      if (res.status === 401) {
        // Try to refresh
        const refreshed = await refreshAccessToken()
        if (!refreshed) handleLogout()
      }
    }
    checkAuth()
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return
    const fetchStats = async () => {
      let res = await fetch(`${API}/alerts`, { headers: authHeaders })
      if (res.status === 401) {
        const refreshed = await refreshAccessToken()
        if (!refreshed) return
        const newHeaders = { 'Authorization': `Bearer ${localStorage.getItem('nw_access_token')}`, 'Content-Type': 'application/json' }
        res = await fetch(`${API}/alerts`, { headers: newHeaders })
      }
      const d: AlertResponse | null = await res.json()
      if (d) setAlertStats({ critical: d.critical || 0, warning: (d.warning || 0) + (d.new_devices || 0) })
    }
    fetchStats()
    const id = setInterval(fetchStats, 5000)
    return () => clearInterval(id)
  }, [accessToken])

  const handleScan = useCallback(async () => {
    if (scanning || !accessToken) return
    setScanning(true)

    let res = await fetch(`${API}/scan`, { method: 'POST', headers: authHeaders })
    if (res.status === 401) {
      const refreshed = await refreshAccessToken()
      if (!refreshed) {
        setScanning(false)
        return
      }
      const newHeaders = { 'Authorization': `Bearer ${localStorage.getItem('nw_access_token')}`, 'Content-Type': 'application/json' }
      res = await fetch(`${API}/scan`, { method: 'POST', headers: newHeaders })
    }

    const result: ScanResult | null = await res.json()
    if (result) {
      setScanVersion(v => v + 1)
      const msg = `Found ${result.devices_found} device${result.devices_found !== 1 ? 's' : ''} (${result.new_devices} new) in ${result.scan_duration_ms}ms`
      setToast(msg)
      setTimeout(() => setToast(null), 5000)
    }
    setTimeout(() => setScanning(false), 3000)
  }, [scanning, accessToken])

  const handleLogin = useCallback((loginResponse: LoginResponse) => {
    // Store securely in localStorage (note: in production use HttpOnly cookies if possible)
    localStorage.setItem('nw_access_token', loginResponse.access_token)
    localStorage.setItem('nw_refresh_token', loginResponse.refresh_token)
    localStorage.setItem('nw_user', JSON.stringify(loginResponse.user))
    setAccessToken(loginResponse.access_token)
    setRefreshToken(loginResponse.refresh_token)
    setCurrentUser(loginResponse.user)
  }, [])

  if (!accessToken) {
    return <LoginPage onLogin={handleLogin} />
  }

  const PageComponent = pageComponents[activePage]

  return (
    <>
      <TopBar stats={alertStats} onLogout={handleLogout} />
      <div className="relative z-[1]">
        <Sidebar
          activePage={activePage}
          onNavigate={setActivePage}
          onScan={handleScan}
          alertCount={alertStats.critical + alertStats.warning}
          scanning={scanning}
        />
        <main className="ml-[220px] p-6">
          {activePage === 'dashboard' ? (
            <DashboardPage scanVersion={scanVersion} token={accessToken} />
          ) : activePage === 'devices' ? (
            <DevicesPage scanVersion={scanVersion} token={accessToken} />
          ) : (
            <PageComponent />
          )}
        </main>
      </div>
      {toast && (
        <div className="fixed bottom-6 right-6 z-[100] bg-panel border border-accent/30 rounded-lg px-5 py-3 shadow-[0_0_20px_rgba(0,212,255,0.15)] animate-fade-in">
          <div className="flex items-center gap-3">
            <span className="text-accent text-lg">&#10003;</span>
            <span className="text-text-noc text-sm font-mono-noc">{toast}</span>
          </div>
        </div>
      )}
    </>
  )
}
