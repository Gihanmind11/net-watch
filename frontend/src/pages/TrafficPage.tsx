import { useState, useEffect, useRef } from 'react'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { Protocol, Talker } from '../types'

const API = 'http://localhost:5000/api'
const fillColors = ['bg-gradient-to-r from-[#005080] to-accent', 'bg-gradient-to-r from-[#00a060] to-accent2', 'bg-gradient-to-r from-[#882200] to-accent3', 'bg-gradient-to-r from-[#005080] to-accent', 'bg-gradient-to-r from-[#00a060] to-accent2']

interface TrafficPoint { time: string; in: number; out: number }

export default function TrafficPage() {
  const [trafficData, setTrafficData] = useState<TrafficPoint[]>([])
  const [protocols, setProtocols] = useState<Protocol[]>([])
  const [talkers, setTalkers] = useState<Talker[]>([])
  const [bwIn, setBwIn] = useState('--')
  const [bwOut, setBwOut] = useState('--')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const initial: TrafficPoint[] = []
    for (let i = 59; i >= 0; i--) {
      const d = new Date(); d.setSeconds(d.getSeconds() - i)
      initial.push({ time: d.toLocaleTimeString('en-GB', { hour12: false }), in: +(Math.random() * 60 + 15).toFixed(1), out: +(Math.random() * 25 + 5).toFixed(1) })
    }
    setTrafficData(initial)
  }, [])

  useEffect(() => {
    fetch(`${API}/protocols`).then(r => r.json()).then(d => setProtocols(d.protocols || [])).catch(() => {})
    fetch(`${API}/top-talkers`).then(r => r.json()).then(d => setTalkers(d.talkers || [])).catch(() => {})
  }, [])

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      const now = new Date().toLocaleTimeString('en-GB', { hour12: false })
      const newIn = +(Math.random() * 60 + 15).toFixed(1); const newOut = +(Math.random() * 25 + 5).toFixed(1)
      setTrafficData(prev => { const next = [...prev, { time: now, in: newIn, out: newOut }]; if (next.length > 60) next.shift(); return next })
      setBwIn(String(newIn)); setBwOut(String(newOut))
    }, 2000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [])

  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u25B2'} <span className="text-accent">Traffic</span> Analysis
      </div>

      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden mb-4">
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
          <div className="font-display font-bold text-sm tracking-[1px] text-accent">Bandwidth Usage {'\u2014'} Last 60 Seconds</div>
          <div className="flex gap-4 text-xs font-mono-noc">
            <span className="text-accent">{'\u25B2'} IN: {bwIn} Mbps</span>
            <span className="text-accent2">{'\u25BC'} OUT: {bwOut} Mbps</span>
          </div>
        </div>
        <div className="p-4 h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trafficData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(26,58,92,0.2)" />
              <XAxis dataKey="time" tick={{ fill: '#2a5070', fontFamily: "'Share Tech Mono'", fontSize: 9 }} interval={9} />
              <YAxis tick={{ fill: '#4a7090', fontFamily: "'Share Tech Mono'", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: 'rgba(11,22,35,0.95)', border: '1px solid #1a3a5c', borderRadius: 6, fontFamily: "'Share Tech Mono'", fontSize: 12 }} />
              <Area type="monotone" dataKey="in" stroke="#00d4ff" fill="rgba(0,212,255,0.1)" strokeWidth={2} dot={false} name="Inbound (Mbps)" />
              <Area type="monotone" dataKey="out" stroke="#00ff88" fill="rgba(0,255,136,0.06)" strokeWidth={2} dot={false} name="Outbound (Mbps)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2"><div className="font-display font-bold text-sm tracking-[1px] text-accent">Protocol Distribution</div></div>
          <div className="p-4 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={protocols}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(26,58,92,0.3)" />
                <XAxis dataKey="protocol" tick={{ fill: '#4a7090', fontFamily: "'Share Tech Mono'", fontSize: 10 }} />
                <YAxis tick={{ fill: '#4a7090', fontFamily: "'Share Tech Mono'", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: 'rgba(11,22,35,0.95)', border: '1px solid #1a3a5c', borderRadius: 6, fontSize: 12 }} />
                <Bar dataKey="percentage" radius={[4, 4, 0, 0]}>
                  {protocols.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2"><div className="font-display font-bold text-sm tracking-[1px] text-accent">Top Talkers</div></div>
          <div className="p-4">
            {talkers.map((t, i) => (
              <div key={t.ip} className="mb-3">
                <div className="flex justify-between mb-1 text-xs"><span className="font-semibold">{t.hostname}</span><span className="font-mono-noc text-accent">{(t.sent_mb + t.recv_mb).toFixed(1)} MB</span></div>
                <div className="h-1.5 bg-accent/10 rounded-[3px] overflow-hidden"><div className={`h-full rounded-[3px] ${fillColors[i] || fillColors[0]}`} style={{ width: `${Math.min((t.sent_mb + t.recv_mb) / 300 * 100, 100)}%` }} /></div>
              </div>
            ))}
            {talkers.length === 0 && <div className="text-muted text-center p-5 text-[13px]">No data available</div>}
          </div>
        </div>
      </div>
    </>
  )
}
