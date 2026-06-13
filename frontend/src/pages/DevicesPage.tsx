import { useState, useEffect } from 'react'
import type { Device } from '../types'
import StatusBadge from '../components/StatusBadge'
import PingBar from '../components/PingBar'

const API = 'http://localhost:5000/api'

export default function DevicesPage({ scanVersion, token }: { scanVersion?: number; token?: string }) {
  const [devices, setDevices] = useState<Device[]>([])
  const [search, setSearch] = useState('')

  const headers = token ? { 'Authorization': `Bearer ${token}` } : {}

  useEffect(() => {
    const fetchDevices = () => {
      fetch(`${API}/devices`, { headers }).then(r => r.json()).then(d => setDevices(d.devices || [])).catch(() => {})
    }
    fetchDevices()
    const id = setInterval(fetchDevices, 5000)
    return () => clearInterval(id)
  }, [token])

  useEffect(() => {
    if (scanVersion && scanVersion > 0) {
      fetch(`${API}/devices`, { headers }).then(r => r.json()).then(d => setDevices(d.devices || [])).catch(() => {})
    }
  }, [scanVersion])

  const [resetting, setResetting] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const r = await fetch(`${API}/devices`, { headers })
      const d = await r.json()
      setDevices(d.devices || [])
    } catch {}
    setRefreshing(false)
  }

  const handleReset = async () => {
    if (!confirm('Clear all discovered devices?')) return
    setResetting(true)
    try {
      await fetch(`${API}/devices/reset`, { method: 'POST', headers })
      setDevices([])
    } catch {}
    setResetting(false)
  }

  const filtered = devices.filter(d =>
    d.device_name.toLowerCase().includes(search.toLowerCase()) ||
    d.ip.includes(search) ||
    d.mac.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u25C8'} <span className="text-accent">Device</span> Inventory
      </div>

      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden mb-4">
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
          <div className="flex items-center gap-3">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent">All Discovered Hosts</div>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className={`flex items-center gap-1.5 px-3 py-1.5 bg-accent/10 border border-accent/30 rounded-md text-accent text-[11px] font-mono-noc tracking-[1px] cursor-pointer transition-all hover:bg-accent/20 hover:border-accent/50 ${refreshing ? 'opacity-60' : ''}`}
              title="Refresh device list"
            >
              <svg className={refreshing ? 'animate-spin' : ''} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              REFRESH
            </button>
            <button
              onClick={handleReset}
              disabled={resetting || devices.length === 0}
              className={`flex items-center gap-1.5 px-3 py-1.5 bg-[#ff3355]/10 border border-[#ff3355]/30 rounded-md text-[#ff3355] text-[11px] font-mono-noc tracking-[1px] cursor-pointer transition-all hover:bg-[#ff3355]/20 hover:border-[#ff3355]/50 ${(resetting || devices.length === 0) ? 'opacity-40 cursor-not-allowed' : ''}`}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
              RESET
            </button>
          </div>
          <input
            className="bg-bg-noc border border-border-noc text-text-noc px-3 py-1.5 rounded text-[13px] font-body w-[220px] focus:outline-none focus:border-accent"
            placeholder="Search device name or IP..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="p-0">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {['#', 'DEVICE NAME', 'IP ADDRESS', 'MAC ADDRESS', 'TYPE', 'OS', 'STATUS', 'OPEN PORTS', 'LATENCY', 'UPTIME', 'FIRST CONNECTED'].map(h => (
                  <th key={h} className="text-[10px] tracking-[2px] text-muted text-left px-3 py-2 border-b border-border-noc font-mono-noc">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((d, i) => (
                <tr key={d.ip} className="hover:bg-accent/[0.03]">
                  <td className="px-3 py-2.5 border-b border-border-noc/40 text-[13px] text-muted font-mono-noc text-[11px]">{String(i + 1).padStart(2, '0')}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 text-[13px] font-semibold">{d.device_name}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 font-mono-noc text-xs text-muted">{d.ip}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 font-mono-noc text-xs text-muted">{d.mac}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 text-muted text-xs">{d.type}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 text-xs">{d.os}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40"><StatusBadge status={d.status} /></td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40">
                    {d.open_ports ? (
                      <div className="flex flex-wrap gap-1">
                        {d.open_ports.split(',').map(p => (
                          <span key={p} className="inline-block px-1.5 py-0.5 bg-accent/10 border border-accent/20 rounded text-[10px] font-mono-noc text-accent">{p}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted text-[11px]">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40"><PingBar ping={d.ping_ms} /></td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 font-mono-noc text-xs text-accent2">{d.uptime_pct}%</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 font-mono-noc text-[11px] text-muted">{d.first_seen ? new Date(d.first_seen + (d.first_seen.includes('Z') || d.first_seen.includes('+') ? '' : 'Z')).toLocaleString('en-LK', { timeZone: 'Asia/Colombo', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) : '—'}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={11} className="text-center text-muted p-[30px] text-[13px]">
                  {devices.length === 0 ? 'No devices discovered yet. Click SCAN NETWORK.' : 'No devices match your search.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
