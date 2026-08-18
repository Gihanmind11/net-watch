import { useState, useEffect, useCallback } from 'react'
import type { PageId, AlertResponse, ScanResult, LoginResponse } from './types'
import { getAlerts, logout, scanNetwork } from './api'
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

  const [activePage, setActivePage] = useState<PageId>('dashboard')
  const [alertStats, setAlertStats] = useState({ critical: 0, warning: 0 })
  const [scanning, setScanning] = useState(false)
  const [scanVersion, setScanVersion] = useState(0)
  const [toast, setToast] = useState<string | null>(null)

  const handleLogout = useCallback(async () => {
    try {
      await logout()
    } catch {
      // Ignore logout errors
    } finally {
      // Clear all stored auth data
      localStorage.removeItem('nw_access_token')
      localStorage.removeItem('nw_refresh_token')
      localStorage.removeItem('nw_user')
      setAccessToken(null)
    }
  }, [])

  useEffect(() => {
    if (!accessToken) return
    const fetchStats = async () => {
      const d: AlertResponse | null = await getAlerts()
      if (d) setAlertStats({ critical: d.critical || 0, warning: (d.warning || 0) + (d.new_devices || 0) })
    }
    fetchStats()
    const id = setInterval(fetchStats, 5000)
    return () => clearInterval(id)
  }, [accessToken])

  const handleScan = useCallback(async () => {
    if (scanning || !accessToken) return
    setScanning(true)

    const result: ScanResult | null = await scanNetwork()
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
