import { useState, useEffect } from 'react'
import type { Alert } from '../types'
import KpiCard from '../components/KpiCard'
import AlertItem from '../components/AlertItem'

const API = 'http://localhost:5000/api'

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [counts, setCounts] = useState({ total: 0, critical: 0, warning: 0, info: 0, new_devices: 0 })

  useEffect(() => {
    const fetchAlerts = () => {
      fetch(`${API}/alerts`)
        .then(r => r.json())
        .then(d => {
          setAlerts(d.alerts || [])
          setCounts({ total: d.total || 0, critical: d.critical || 0, warning: d.warning || 0, info: d.info || 0, new_devices: d.new_devices || 0 })
        })
        .catch(() => {})
    }
    fetchAlerts()
    const id = setInterval(fetchAlerts, 5000)
    return () => clearInterval(id)
  }, [])

  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u26A0'} <span className="text-accent">Alert</span> Center
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <KpiCard label="Critical" value={counts.critical} sub="Immediate action required" color="red" icon="!" />
        <KpiCard label="Warning" value={counts.warning + counts.new_devices} sub="Monitor closely" color="orange" icon={'\u26A0'} />
        <KpiCard label="Info" value={counts.info} sub="Informational events" color="blue" icon="i" />
      </div>

      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
          <div className="font-display font-bold text-sm tracking-[1px] text-accent">All Alerts</div>
          <div className="text-[11px] text-muted font-mono-noc">AUTO-REFRESH: 5s</div>
        </div>
        <div className="p-4">
          {alerts.length === 0 && <div className="text-muted text-center p-[30px] text-[13px]">No active alerts</div>}
          {alerts.map((a, i) => <AlertItem key={a.id || i} alert={a} />)}
        </div>
      </div>
    </>
  )
}
