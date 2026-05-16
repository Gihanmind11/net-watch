import { useState, useEffect, useCallback } from 'react'
import type { PageId, AlertResponse } from './types'
import TopBar from './components/TopBar'
import Sidebar from './components/Sidebar'
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
  const [activePage, setActivePage] = useState<PageId>('dashboard')
  const [alertStats, setAlertStats] = useState({ critical: 0, warning: 0 })
  const [scanning, setScanning] = useState(false)

  useEffect(() => {
    const fetchStats = () => {
      fetch(`${API}/alerts`)
        .then(r => r.json())
        .then((d: AlertResponse) => setAlertStats({ critical: d.critical || 0, warning: (d.warning || 0) + (d.new_devices || 0) }))
        .catch(() => {})
    }
    fetchStats()
    const id = setInterval(fetchStats, 5000)
    return () => clearInterval(id)
  }, [])

  const handleScan = useCallback(() => {
    if (scanning) return
    setScanning(true)
    fetch(`${API}/scan`, { method: 'POST' })
      .catch(err => console.error('Scan failed:', err))
      .finally(() => { setTimeout(() => setScanning(false), 3000) })
  }, [scanning])

  const PageComponent = pageComponents[activePage]

  return (
    <>
      <TopBar stats={alertStats} />
      <div className="relative z-[1]">
        <Sidebar
          activePage={activePage}
          onNavigate={setActivePage}
          onScan={handleScan}
          alertCount={alertStats.critical + alertStats.warning}
        />
        <main className="ml-[220px] p-6">
          <PageComponent />
        </main>
      </div>
    </>
  )
}
