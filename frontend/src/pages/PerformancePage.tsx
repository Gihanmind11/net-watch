import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { Device, NetworkInterface } from '../types'
import StatusBadge from '../components/StatusBadge'

const API = 'http://localhost:5000/api'

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

export default function PerformancePage() {
  const [interfaces, setInterfaces] = useState<NetworkInterface[]>([])
  const [devices, setDevices] = useState<Device[]>([])

  const headers = { 'Authorization': `Bearer ${localStorage.getItem('nw_token') || ''}` }

  useEffect(() => {
    fetch(`${API}/interfaces`, { headers }).then(r => r.json()).then(d => setInterfaces(d.interfaces || [])).catch(() => {})
    fetch(`${API}/devices`, { headers }).then(r => r.json()).then(d => setDevices(d.devices || [])).catch(() => {})
  }, [])

  const latencyData = devices.filter(d => d.ping_ms > 0).slice(0, 10).map(d => ({
    name: (d.device_name || '').replace('workstation', 'ws').replace('gateway', 'gw'),
    ping: d.ping_ms,
    color: d.ping_ms < 20 ? 'rgba(0,255,136,0.6)' : d.ping_ms < 50 ? 'rgba(255,204,0,0.6)' : 'rgba(255,51,85,0.6)',
  }))

  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u25CE'} <span className="text-accent">Performance</span> Metrics
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        {interfaces.map(iface => (
          <div key={iface.name} className="bg-panel2 border border-border-noc rounded-lg p-3.5 transition-[border-color] hover:border-accent">
            <div className="font-mono-noc text-[13px] text-accent mb-2">{iface.name}</div>
            <div className="text-xs text-muted my-[3px]">Speed: <b className="text-text-noc">{iface.speed}</b></div>
            <div className="text-xs text-muted my-[3px]">{'\u2191'} In: <b className="text-accent">{formatBytes(iface.total_in)}</b></div>
            <div className="text-xs text-muted my-[3px]">{'\u2193'} Out: <b className="text-accent2">{formatBytes(iface.total_out)}</b></div>
            <div className="text-xs text-muted my-[3px]">Errors: <b className={iface.errors === 0 ? 'text-accent2' : 'text-danger'}>{iface.errors}</b></div>
            <div className="mt-2"><StatusBadge status={iface.status === 'UP' ? 'up' : 'down'} /></div>
          </div>
        ))}
        {interfaces.length === 0 && (
          <div className="col-span-3 bg-panel2 border border-border-noc rounded-lg p-3.5 text-center text-muted">Loading interface data...</div>
        )}
      </div>

      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
        <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2"><div className="font-display font-bold text-sm tracking-[1px] text-accent">Latency per Device (ms)</div></div>
        <div className="p-4 h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={latencyData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(26,58,92,0.3)" />
              <XAxis type="number" tick={{ fill: '#4a7090', fontFamily: "'Share Tech Mono'", fontSize: 10 }} />
              <YAxis dataKey="name" type="category" tick={{ fill: '#c8e0f4', fontFamily: 'Rajdhani', fontSize: 11 }} width={80} />
              <Tooltip contentStyle={{ background: 'rgba(11,22,35,0.95)', border: '1px solid #1a3a5c', borderRadius: 6, fontSize: 12 }} />
              <Bar dataKey="ping" radius={[0, 4, 4, 0]}>
                {latencyData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  )
}
