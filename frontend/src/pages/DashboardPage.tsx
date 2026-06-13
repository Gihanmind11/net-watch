import { useState, useEffect, useRef } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import type { Device, Alert, Stats } from '../types'
import KpiCard from '../components/KpiCard'
import StatusBadge from '../components/StatusBadge'
import PingBar from '../components/PingBar'
import AlertItem from '../components/AlertItem'

const API = 'http://localhost:5000/api'

interface TrafficPoint { time: string; in: number; out: number }

export default function DashboardPage({ scanVersion, token }: { scanVersion?: number; token?: string }) {
  const [stats, setStats] = useState<Stats>({ total_devices: 0, online: 0, offline: 0, avg_latency: 0, new_devices: 0, warning: 0 })
  const [devices, setDevices] = useState<Device[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [trafficData, setTrafficData] = useState<TrafficPoint[]>([])
  const [netLoad, setNetLoad] = useState(0)
  const [bwPct, setBwPct] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const headers = token ? { 'Authorization': `Bearer ${token}` } : {}

  useEffect(() => {
    const fetchAll = () => {
      fetch(`${API}/stats`, { headers }).then(r => r.json()).then(setStats).catch(() => {})
      fetch(`${API}/devices`, { headers }).then(r => r.json()).then(d => setDevices(d.devices || [])).catch(() => {})
      fetch(`${API}/alerts`, { headers }).then(r => r.json()).then(d => setAlerts((d.alerts || []).slice(0, 4))).catch(() => {})
    }
    fetchAll()
    const id = setInterval(fetchAll, 5000)
    return () => clearInterval(id)
  }, [token])

  useEffect(() => {
    if (scanVersion && scanVersion > 0) {
      fetch(`${API}/stats`, { headers }).then(r => r.json()).then(setStats).catch(() => {})
      fetch(`${API}/devices`, { headers }).then(r => r.json()).then(d => setDevices(d.devices || [])).catch(() => {})
      fetch(`${API}/alerts`, { headers }).then(r => r.json()).then(d => setAlerts((d.alerts || []).slice(0, 4))).catch(() => {})
    }
  }, [scanVersion])

  useEffect(() => {
    const fetchBandwidth = () => {
      fetch(`${API}/bandwidth`, { headers })
        .then(r => r.json())
        .then(data => {
          const current = data.current || {}
          let totalIn = 0
          let totalOut = 0
          for (const iface of Object.values(current) as Array<{ mbps_in?: number; mbps_out?: number }>) {
            totalIn += iface.mbps_in || 0
            totalOut += iface.mbps_out || 0
          }
          const now = new Date().toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
          setTrafficData(prev => {
            const next = [...prev, { time: now, in: +totalIn.toFixed(1), out: +totalOut.toFixed(1) }]
            if (next.length > 30) next.shift()
            return next
          })
          setNetLoad(Math.round(Math.min(totalIn + totalOut, 100)))
          setBwPct(Math.round(Math.min(totalIn, 100)))
        })
        .catch(() => {})
    }
    fetchBandwidth()
    intervalRef.current = setInterval(fetchBandwidth, 2000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [])

  const statusData = [
    { name: 'Online', value: stats.online || 0, color: 'rgba(0,255,136,0.7)' },
    { name: 'Warning', value: stats.warning || 0, color: 'rgba(255,204,0,0.7)' },
    { name: 'Offline', value: stats.offline || 0, color: 'rgba(255,51,85,0.7)' },
  ]

  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u2B21'} <span className="text-accent">Dashboard</span> Overview
      </div>

      <div className="grid grid-cols-4 gap-4 mb-6">
        <KpiCard label="Total Devices" value={stats.total_devices} sub="Discovered on network" color="blue" icon={'\u25C8'} />
        <KpiCard label="Online" value={stats.online} sub={`${stats.total_devices > 0 ? Math.round(stats.online / stats.total_devices * 100) : 0}% availability`} color="green" icon={'\u2713'} />
        <KpiCard label="Avg Latency" value={`${Math.round(stats.avg_latency)}ms`} sub="Across all hosts" color="orange" icon={'\u2299'} />
        <KpiCard label="Offline" value={stats.offline} sub="Require attention" color="red" icon={'\u2715'} />
      </div>

      <div className="grid grid-cols-[2fr_1fr] gap-4 mb-4">
        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent flex items-center gap-2">{'\u25B2'} Network Traffic (Mbps)</div>
            <div className="text-[11px] text-muted font-mono-noc">LIVE</div>
          </div>
          <div className="p-4 relative">
            <div className="absolute left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-accent to-transparent animate-scan-sweep pointer-events-none" style={{ boxShadow: '0 0 12px var(--color-accent)' }} />
            <div className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trafficData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(26,58,92,0.3)" />
                  <XAxis dataKey="time" tick={false} />
                  <YAxis tick={{ fill: '#4a7090', fontFamily: "'Share Tech Mono'", fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: 'rgba(11,22,35,0.95)', border: '1px solid #1a3a5c', borderRadius: 6, fontFamily: "'Share Tech Mono'", fontSize: 12 }} />
                  <Area type="monotone" dataKey="in" stroke="#00d4ff" fill="rgba(0,212,255,0.08)" strokeWidth={2} dot={false} name="Inbound" />
                  <Area type="monotone" dataKey="out" stroke="#00ff88" fill="rgba(0,255,136,0.05)" strokeWidth={2} dot={false} name="Outbound" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent flex items-center gap-2">{'\u25CE'} Device Status</div>
          </div>
          <div className="p-4">
            <div className="h-[160px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={statusData} cx="50%" cy="50%" innerRadius={45} outerRadius={65} dataKey="value" paddingAngle={2}>
                    {statusData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: 'rgba(11,22,35,0.95)', border: '1px solid #1a3a5c', borderRadius: 6, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3">
              <div className="mb-3.5">
                <div className="flex justify-between mb-1.5 text-xs"><span className="text-text-noc font-semibold">Network Load</span><span className="font-mono-noc text-accent">{netLoad}%</span></div>
                <div className="h-1.5 bg-accent/10 rounded-[3px] overflow-hidden"><div className="h-full rounded-[3px] bg-gradient-to-r from-[#005080] to-accent transition-all duration-1000" style={{ width: `${netLoad}%` }} /></div>
              </div>
              <div className="mb-3.5">
                <div className="flex justify-between mb-1.5 text-xs"><span className="text-text-noc font-semibold">Bandwidth Usage</span><span className="font-mono-noc text-accent">{bwPct}%</span></div>
                <div className="h-1.5 bg-accent/10 rounded-[3px] overflow-hidden"><div className="h-full rounded-[3px] bg-gradient-to-r from-[#00a060] to-accent2 transition-all duration-1000" style={{ width: `${bwPct}%` }} /></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent flex items-center gap-2">{'\u25C8'} Recent Device Activity</div>
          </div>
          <div className="p-0">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {['DEVICE NAME', 'IP ADDRESS', 'STATUS', 'LATENCY'].map(h => (
                    <th key={h} className="text-[10px] tracking-[2px] text-muted text-left px-3 py-2 border-b border-border-noc font-mono-noc">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {devices.slice(0, 8).map(d => (
                  <tr key={d.ip} className="hover:bg-accent/[0.03]">
                    <td className="px-3 py-2.5 border-b border-border-noc/40 text-[13px] font-semibold">{d.device_name}</td>
                    <td className="px-3 py-2.5 border-b border-border-noc/40 font-mono-noc text-xs text-muted">{d.ip}</td>
                    <td className="px-3 py-2.5 border-b border-border-noc/40"><StatusBadge status={d.status} /></td>
                    <td className="px-3 py-2.5 border-b border-border-noc/40"><PingBar ping={d.ping_ms} /></td>
                  </tr>
                ))}
                {devices.length === 0 && (
                  <tr><td colSpan={4} className="text-center text-muted p-5 text-[13px]">No devices discovered yet. Click SCAN NETWORK.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent flex items-center gap-2">{'\u26A0'} Recent Alerts</div>
            <div className="text-[11px] text-danger font-mono-noc">{alerts.length} ACTIVE</div>
          </div>
          <div className="p-4">
            {alerts.length === 0 && <div className="text-muted text-center p-5 text-[13px]">No active alerts</div>}
            {alerts.map((a, i) => <AlertItem key={a.id || i} alert={a} />)}
          </div>
        </div>
      </div>
    </>
  )
}
