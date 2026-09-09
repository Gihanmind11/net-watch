import { useState, useEffect, useRef } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import type { Device, Alert, Stats, WifiInfo } from '../types'
import { getAlerts, getBandwidth, getDevices, getStats, getWifi } from '../api'
import KpiCard from '../components/KpiCard'
import StatusBadge from '../components/StatusBadge'
import PingBar from '../components/PingBar'
import AlertItem from '../components/AlertItem'

interface TrafficPoint { time: string; in: number; out: number }

const DEFAULT_WIFI: WifiInfo = {
  connected: false, state: 'disconnected', ssid: '', bssid: '', signal: 0,
  channel: '—', radio_type: '—', authentication: '—', rx_rate: '—', tx_rate: '—',
  visible_networks: 0, hotspot_active: false, hotspot_clients: 0,
}

/** Signal bars 1-4 lit from a 0-100 % strength. */
function SignalBars({ pct }: { pct: number }) {
  const lit = pct >= 80 ? 4 : pct >= 60 ? 3 : pct >= 40 ? 2 : pct >= 20 ? 1 : 0
  return (
    <span className="inline-flex items-end gap-[3px]">
      {[8, 12, 16, 20].map((h, i) => (
        <span
          key={h}
          className={`w-[5px] rounded-[1px] ${i < lit ? 'bg-accent2' : 'bg-border-noc/50'}`}
          style={{ height: h, boxShadow: i < lit ? '0 0 6px var(--color-accent2)' : 'none' }}
        />
      ))}
    </span>
  )
}

function UsageBar({ label, value, pct, gradient }: { label: string; value: string; pct: number; gradient: string }) {
  return (
    <div className="mb-[18px] last:mb-0">
      <div className="flex justify-between mb-2 text-xs">
        <span className="text-text-noc font-semibold">{label}</span>
        <span className="font-mono-noc text-accent">{value}</span>
      </div>
      <div className="h-2 bg-accent/10 rounded-[3px] overflow-hidden">
        <div className={`h-full rounded-[3px] bg-gradient-to-r transition-all duration-700 ${gradient}`} style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }} />
      </div>
    </div>
  )
}

export default function DashboardPage({ scanVersion, token }: { scanVersion?: number; token?: string }) {
  const [stats, setStats] = useState<Stats>({ total_devices: 0, online: 0, offline: 0, avg_latency: 0, new_devices: 0, warning: 0 })
  const [wifi, setWifi] = useState<WifiInfo>(DEFAULT_WIFI)
  const [clock, setClock] = useState(() => new Date().toLocaleTimeString('en-GB', { hour12: false }))
  const [devices, setDevices] = useState<Device[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [trafficData, setTrafficData] = useState<TrafficPoint[]>([])
  const [netLoad, setNetLoad] = useState(0)
  const [bwPct, setBwPct] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const fetchAll = () => {
      getStats().then(setStats).catch(() => {})
      getDevices().then(d => setDevices(d.devices || [])).catch(() => {})
      getAlerts().then(d => setAlerts((d.alerts || []).slice(0, 4))).catch(() => {})
      getWifi().then(setWifi).catch(() => {})
    }
    fetchAll()
    const id = setInterval(fetchAll, 5000)
    return () => clearInterval(id)
  }, [token])

  useEffect(() => {
    if (scanVersion && scanVersion > 0) {
      getStats().then(setStats).catch(() => {})
      getDevices().then(d => setDevices(d.devices || [])).catch(() => {})
      getAlerts().then(d => setAlerts((d.alerts || []).slice(0, 4))).catch(() => {})
    }
  }, [scanVersion])

  useEffect(() => {
    const id = setInterval(() => setClock(new Date().toLocaleTimeString('en-GB', { hour12: false })), 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const fetchBandwidth = () => {
      getBandwidth()
        .then(data => {
          const current = data.current || {}
          let totalIn = 0
          let totalOut = 0
          let totalSpeed = 0
          let maxUtil = 0
          for (const iface of Object.values(current) as Array<{ mbps_in?: number; mbps_out?: number; speed_mbps?: number; utilization?: number }>) {
            totalIn += iface.mbps_in || 0
            totalOut += iface.mbps_out || 0
            totalSpeed += iface.speed_mbps || 0
            maxUtil = Math.max(maxUtil, iface.utilization || 0)
          }
          const now = new Date().toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
          setTrafficData(prev => {
            const next = [...prev, { time: now, in: +totalIn.toFixed(1), out: +totalOut.toFixed(1) }]
            if (next.length > 30) next.shift()
            return next
          })
          const netLoadPct = totalSpeed > 0 ? (totalIn + totalOut) / totalSpeed * 100 : 0
          setNetLoad(Math.round(Math.min(Math.max(netLoadPct, 0), 100)))
          setBwPct(Math.round(Math.min(Math.max(maxUtil, 0), 100)))
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

      <div className="grid grid-cols-4 gap-4 mb-6">
        <KpiCard label="WiFi Signal" value={`${wifi.signal}%`} sub={wifi.ssid || (wifi.connection_type === 'ethernet' ? 'Wired connection' : 'No wireless adapter')} color="green" icon={'\u25B2'} />
        <KpiCard label="Current SSID" value={wifi.ssid || (wifi.connection_type === 'ethernet' ? 'Ethernet' : '\u2014')} sub={wifi.connection_type === 'ethernet' ? 'Wired connection' : wifi.radio_type !== '\u2014' ? wifi.radio_type : wifi.note ? 'Limited by Windows' : 'Not connected'} color="blue" icon={'\u25C9'} />
        <KpiCard label="Hotspot" value={wifi.hotspot_active ? 'ON' : 'OFF'} sub={`${wifi.hotspot_clients} clients connected`} color={wifi.hotspot_active ? 'orange' : 'red'} icon={'\u25CE'} />
        <KpiCard label="Connected Clients" value={stats.total_devices} sub={`${wifi.visible_networks} visible WiFi networks`} color="blue" icon={'\u2B21'} />
      </div>

      <div className="grid grid-cols-[2fr_1fr] gap-4 mb-4">
        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent flex items-center gap-2">{'\u26A0'} Current Network Details</div>
            <div className="flex items-center gap-2.5">
              <span className="flex items-center gap-1.5 text-[10px] font-mono-noc tracking-[1px] text-accent2 border border-accent2/40 rounded-[3px] px-2 py-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-accent2 animate-blink" style={{ boxShadow: '0 0 6px var(--color-accent2)' }} />LIVE
              </span>
              <span className="text-[11px] text-muted font-mono-noc">{clock}</span>
            </div>
          </div>
          {wifi.note && (
            <div className="mx-5 mt-4 flex items-center gap-2.5 rounded-[6px] border border-[#ffb020]/40 bg-[#ffb020]/10 px-3.5 py-2.5">
              <span className="text-[#ffb020] text-sm leading-none">{'\u26A0'}</span>
              <span className="text-[12px] text-[#ffd27a] leading-snug">{wifi.note}</span>
            </div>
          )}
          <div className="p-5 grid grid-cols-2 gap-x-8">
            <div>
              <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">USING NOW</div>
              <div className="font-display text-[26px] font-bold text-accent leading-tight" style={{ textShadow: '0 0 20px rgba(0,212,255,0.3)' }}>{wifi.ssid || (wifi.connection_type === 'ethernet' ? 'Ethernet' : '\u2014')}</div>
              <div className="text-xs text-muted mt-0.5">{wifi.authentication !== '\u2014' ? `Authentication \u00B7 ${wifi.authentication}` : wifi.connection_type === 'ethernet' ? 'Wired Ethernet connection' : 'No active Wi-Fi connection'}</div>

              <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mt-5 mb-2">SIGNAL</div>
              <div className="flex items-center gap-2.5">
                <SignalBars pct={wifi.signal} />
                <span className="font-mono-noc text-sm text-accent2">{wifi.signal}%</span>
              </div>

              <div className="grid grid-cols-2 gap-4 mt-5">
                <div>
                  <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">BSSID</div>
                  <div className="font-mono-noc text-[13px] text-text-noc">{wifi.bssid || '\u2014'}</div>
                </div>
                <div>
                  <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">CHANNEL</div>
                  <div className="font-mono-noc text-[13px] text-text-noc">{wifi.channel}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 mt-5">
                <div>
                  <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">RX</div>
                  <div className="font-mono-noc text-[13px] text-accent">{wifi.rx_rate} Mbps</div>
                </div>
                <div>
                  <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">TX</div>
                  <div className="font-mono-noc text-[13px] text-accent">{wifi.tx_rate} Mbps</div>
                </div>
              </div>
            </div>

            <div>
              <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">HOTSPOT</div>
              <div className={`font-display text-[26px] font-bold leading-tight ${wifi.hotspot_active ? 'text-accent3' : 'text-muted'}`}>{wifi.hotspot_active ? 'Active' : 'Inactive'}</div>
              <div className="text-xs text-muted mt-0.5">{wifi.hotspot_clients} clients connected</div>

              <div className="grid grid-cols-2 gap-4 mt-5">
                <div>
                  <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">STATUS</div>
                  <div className={`text-[13px] font-semibold ${wifi.connected ? 'text-accent2' : 'text-muted'}`}>{wifi.connected ? 'Allowed' : 'Down'}</div>
                </div>
                <div>
                  <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">SECURITY</div>
                  <div className={`text-[13px] font-semibold ${wifi.connected ? 'text-accent2' : 'text-muted'}`}>{wifi.connected ? 'Checked' : '\u2014'}</div>
                </div>
              </div>

              <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mt-5 mb-1">RADIO TYPE</div>
              <div className="font-mono-noc text-[13px] text-text-noc">{wifi.radio_type}</div>

              <div className="mt-5 bg-accent/[0.04] border border-border-noc rounded-[6px] px-3.5 py-3">
                <div className="text-[10px] tracking-[2px] text-muted font-mono-noc mb-1">NETWORK SUMMARY</div>
                <div className="text-xs text-text-noc leading-relaxed">
                  {stats.total_devices} clients on your network, {wifi.visible_networks} visible APs, {wifi.connected ? (wifi.connection_type === 'ethernet' ? 'Ethernet connected' : 'WiFi connected') : 'disconnected'}.
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent flex items-center gap-2">{'\u25C9'} Network Usage</div>
          </div>
          <div className="p-5">
            <UsageBar label="Visible Wi-Fi Networks" value={String(wifi.visible_networks)} pct={Math.min(wifi.visible_networks * 5, 100)} gradient="from-[#005080] to-accent" />
            <UsageBar label="WiFi Signal" value={`${wifi.signal}%`} pct={wifi.signal} gradient="from-[#00a060] to-accent2" />
            <UsageBar label="Hotspot Clients" value={String(wifi.hotspot_clients)} pct={Math.min(wifi.hotspot_clients * 20, 100)} gradient="from-[#804010] to-accent3" />
            <UsageBar label="Known Clients" value={String(stats.total_devices)} pct={Math.min(stats.total_devices * 4, 100)} gradient="from-[#00a060] to-accent2" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-[2fr_1fr] gap-4 mb-4">
        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent flex items-center gap-2">{'\u25B2'} Network Traffic (Mbps)</div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-4 text-[11px] font-mono-noc tracking-[1px]">
                <span className="flex items-center gap-1.5 text-text-noc"><span className="w-2.5 h-2.5 rounded-[3px] bg-accent" style={{ boxShadow: '0 0 6px var(--color-accent)' }} />INBOUND</span>
                <span className="flex items-center gap-1.5 text-text-noc"><span className="w-2.5 h-2.5 rounded-[3px] bg-accent2" style={{ boxShadow: '0 0 6px var(--color-accent2)' }} />OUTBOUND</span>
              </div>
              <div className="text-[11px] text-muted font-mono-noc">LIVE</div>
            </div>
          </div>
          <div className="p-4 relative">
            <div className="absolute left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-accent to-transparent animate-scan-sweep pointer-events-none" style={{ boxShadow: '0 0 12px var(--color-accent)' }} />
            <div className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trafficData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(26,58,92,0.3)" />
                  <XAxis dataKey="time" tick={false} />
                  <YAxis tick={{ fill: '#4a7090', fontFamily: "'Share Tech Mono'", fontSize: 10 }} label={{ value: 'Mbps', angle: -90, position: 'insideLeft', style: { fill: '#4a7090', fontFamily: "'Share Tech Mono'", fontSize: 10, letterSpacing: '1px' } }} />
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
                  <tr><td colSpan={4} className="text-center text-muted p-5 text-[13px]">No devices discovered yet. The scanner runs every 30s — results appear automatically.</td></tr>
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
