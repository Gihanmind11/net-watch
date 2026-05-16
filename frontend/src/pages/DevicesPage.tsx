import { useState, useEffect } from 'react'
import type { Device } from '../types'
import StatusBadge from '../components/StatusBadge'
import PingBar from '../components/PingBar'

const API = 'http://localhost:5000/api'

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [search, setSearch] = useState('')

  useEffect(() => {
    const fetchDevices = () => {
      fetch(`${API}/devices`).then(r => r.json()).then(d => setDevices(d.devices || [])).catch(() => {})
    }
    fetchDevices()
    const id = setInterval(fetchDevices, 5000)
    return () => clearInterval(id)
  }, [])

  const filtered = devices.filter(d =>
    d.hostname.toLowerCase().includes(search.toLowerCase()) ||
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
          <div className="font-display font-bold text-sm tracking-[1px] text-accent">All Discovered Hosts</div>
          <input
            className="bg-bg-noc border border-border-noc text-text-noc px-3 py-1.5 rounded text-[13px] font-body w-[220px] focus:outline-none focus:border-accent"
            placeholder="Search hostname or IP..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="p-0">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {['#', 'HOSTNAME', 'IP ADDRESS', 'MAC ADDRESS', 'TYPE', 'STATUS', 'LATENCY', 'UPTIME'].map(h => (
                  <th key={h} className="text-[10px] tracking-[2px] text-muted text-left px-3 py-2 border-b border-border-noc font-mono-noc">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((d, i) => (
                <tr key={d.ip} className="hover:bg-accent/[0.03]">
                  <td className="px-3 py-2.5 border-b border-border-noc/40 text-[13px] text-muted font-mono-noc text-[11px]">{String(i + 1).padStart(2, '0')}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 text-[13px] font-semibold">{d.hostname}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 font-mono-noc text-xs text-muted">{d.ip}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 font-mono-noc text-xs text-muted">{d.mac}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 text-muted text-xs">{d.type}</td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40"><StatusBadge status={d.status} /></td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40"><PingBar ping={d.ping_ms} /></td>
                  <td className="px-3 py-2.5 border-b border-border-noc/40 font-mono-noc text-xs text-accent2">{d.uptime_pct}%</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={8} className="text-center text-muted p-[30px] text-[13px]">
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
