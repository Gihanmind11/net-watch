import { useState, useEffect, useRef } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const API = 'http://localhost:5000/api'

interface TrafficPoint { time: string; in: number; out: number }
interface InterfaceData {
  interface: string
  mbps_in: number
  mbps_out: number
  speed_mbps: number
  utilization: number
  total_in: number
  total_out: number
  packets_in: number
  packets_out: number
  errors_in: number
  errors_out: number
  drops_in: number
  drops_out: number
}
interface HistoryPoint { recorded_at: string; bytes_in: number; bytes_out: number }

type TimeRange = '5m' | '15m' | '1h' | '6h'

const TIME_RANGES: Record<TimeRange, { label: string; minutes: number }> = {
  '5m': { label: '5 Min', minutes: 5 },
  '15m': { label: '15 Min', minutes: 15 },
  '1h': { label: '1 Hour', minutes: 60 },
  '6h': { label: '6 Hours', minutes: 360 },
}

export default function TrafficPage() {
  const [trafficData, setTrafficData] = useState<TrafficPoint[]>([])
  const [interfaces, setInterfaces] = useState<InterfaceData[]>([])
  const [bwIn, setBwIn] = useState('--')
  const [bwOut, setBwOut] = useState('--')
  const [timeRange, setTimeRange] = useState<TimeRange>('5m')
  const [historyData, setHistoryData] = useState<TrafficPoint[]>([])
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const headers = { 'Authorization': `Bearer ${localStorage.getItem('nw_token') || ''}` }

  // Fetch live bandwidth data
  useEffect(() => {
    const fetchBandwidth = () => {
      fetch(`${API}/bandwidth`, { headers })
        .then(r => r.json())
        .then(data => {
          const current = data.current || {}
          const ifaces = Object.values(current) as InterfaceData[]
          setInterfaces(ifaces)

          let totalIn = 0
          let totalOut = 0
          for (const iface of ifaces) {
            totalIn += iface.mbps_in || 0
            totalOut += iface.mbps_out || 0
          }
          const now = new Date().toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
          setTrafficData(prev => {
            const next = [...prev, { time: now, in: +totalIn.toFixed(1), out: +totalOut.toFixed(1) }]
            if (next.length > 60) next.shift()
            return next
          })
          setBwIn(totalIn.toFixed(1))
          setBwOut(totalOut.toFixed(1))
        })
        .catch(() => {})
    }
    fetchBandwidth()
    intervalRef.current = setInterval(fetchBandwidth, 2000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [])

  // Fetch historical data when time range changes
  useEffect(() => {
    const minutes = TIME_RANGES[timeRange].minutes
    fetch(`${API}/bandwidth`, { headers })
      .then(r => r.json())
      .then(data => {
        const history: HistoryPoint[] = data.history || []
        // Aggregate by timestamp
        const aggregated: Record<string, { in: number; out: number }> = {}
        for (const row of history) {
          const time = new Date(row.recorded_at).toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit' })
          if (!aggregated[time]) aggregated[time] = { in: 0, out: 0 }
          aggregated[time].in += (row.bytes_in * 8 / 1_000_000)
          aggregated[time].out += (row.bytes_out * 8 / 1_000_000)
        }
        const points = Object.entries(aggregated).map(([time, v]) => ({
          time,
          in: +v.in.toFixed(2),
          out: +v.out.toFixed(2),
        }))
        setHistoryData(points)
      })
      .catch(() => {})
  }, [timeRange])

  const getUtilColor = (util: number) => {
    if (util >= 80) return 'text-danger'
    if (util >= 50) return 'text-accent3'
    return 'text-accent2'
  }

  const getUtilBarColor = (util: number) => {
    if (util >= 80) return 'bg-danger'
    if (util >= 50) return 'bg-accent3'
    return 'bg-accent2'
  }

  const formatBytes = (bytes: number) => {
    if (bytes >= 1e12) return (bytes / 1e12).toFixed(1) + ' TB'
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB'
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB'
    if (bytes >= 1e3) return (bytes / 1e3).toFixed(1) + ' KB'
    return bytes + ' B'
  }

  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u25B2'} <span className="text-accent">Traffic</span> Analysis
      </div>

      {/* Live Bandwidth Chart */}
      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden mb-4">
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
          <div className="font-display font-bold text-sm tracking-[1px] text-accent">Live Bandwidth {'\u2014'} Last 60 Seconds</div>
          <div className="flex gap-4 text-xs font-mono-noc">
            <span className="text-accent">{'\u25B2'} IN: {bwIn} Mbps</span>
            <span className="text-accent2">{'\u25BC'} OUT: {bwOut} Mbps</span>
          </div>
        </div>
        <div className="p-4 h-[220px]">
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

      {/* Historical Traffic Chart */}
      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden mb-4">
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
          <div className="font-display font-bold text-sm tracking-[1px] text-accent">Historical Traffic</div>
          <div className="flex gap-1">
            {Object.entries(TIME_RANGES).map(([key, { label }]) => (
              <button
                key={key}
                onClick={() => setTimeRange(key as TimeRange)}
                className={`px-3 py-1 text-[11px] font-mono-noc tracking-[1px] rounded border cursor-pointer transition-all ${
                  timeRange === key
                    ? 'bg-accent/20 border-accent/50 text-accent'
                    : 'bg-transparent border-border-noc text-muted hover:border-accent/30 hover:text-text-noc'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="p-4 h-[220px]">
          {historyData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={historyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(26,58,92,0.2)" />
                <XAxis dataKey="time" tick={{ fill: '#2a5070', fontFamily: "'Share Tech Mono'", fontSize: 9 }} interval={Math.max(0, Math.floor(historyData.length / 8))} />
                <YAxis tick={{ fill: '#4a7090', fontFamily: "'Share Tech Mono'", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: 'rgba(11,22,35,0.95)', border: '1px solid #1a3a5c', borderRadius: 6, fontFamily: "'Share Tech Mono'", fontSize: 12 }} />
                <Area type="monotone" dataKey="in" stroke="#00d4ff" fill="rgba(0,212,255,0.08)" strokeWidth={1.5} dot={false} name="Inbound (Mbps)" />
                <Area type="monotone" dataKey="out" stroke="#00ff88" fill="rgba(0,255,136,0.05)" strokeWidth={1.5} dot={false} name="Outbound (Mbps)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-muted text-sm font-mono-noc">No historical data yet</div>
          )}
        </div>
      </div>

      {/* Interface Stats */}
      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
        <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2">
          <div className="font-display font-bold text-sm tracking-[1px] text-accent">Interface Statistics</div>
        </div>
        <div className="p-4">
          {interfaces.length === 0 ? (
            <div className="text-muted text-center p-5 text-[13px]">No interfaces detected</div>
          ) : (
            <div className="space-y-3">
              {interfaces.map(iface => (
                <div key={iface.interface} className="bg-[#081020] border border-border-noc rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-accent2 animate-pulse" />
                      <span className="font-display font-bold text-sm text-text-noc">{iface.interface}</span>
                      {iface.speed_mbps > 0 && (
                        <span className="text-[10px] text-muted font-mono-noc px-2 py-0.5 bg-[#0b1623] rounded">{iface.speed_mbps} Mbps</span>
                      )}
                    </div>
                    <span className={`font-mono-noc text-sm font-bold ${getUtilColor(iface.utilization)}`}>
                      {iface.utilization}% utilization
                    </span>
                  </div>

                  {/* Utilization bar */}
                  <div className="h-1.5 bg-accent/10 rounded-full overflow-hidden mb-3">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${getUtilBarColor(iface.utilization)}`}
                      style={{ width: `${Math.min(iface.utilization, 100)}%` }}
                    />
                  </div>

                  {/* Stats grid */}
                  <div className="grid grid-cols-4 gap-3 text-xs">
                    <div>
                      <div className="text-muted mb-0.5">IN</div>
                      <div className="font-mono-noc text-accent font-bold">{iface.mbps_in} Mbps</div>
                    </div>
                    <div>
                      <div className="text-muted mb-0.5">OUT</div>
                      <div className="font-mono-noc text-accent2 font-bold">{iface.mbps_out} Mbps</div>
                    </div>
                    <div>
                      <div className="text-muted mb-0.5">Total IN</div>
                      <div className="font-mono-noc text-text-noc">{formatBytes(iface.total_in)}</div>
                    </div>
                    <div>
                      <div className="text-muted mb-0.5">Total OUT</div>
                      <div className="font-mono-noc text-text-noc">{formatBytes(iface.total_out)}</div>
                    </div>
                    <div>
                      <div className="text-muted mb-0.5">Packets IN</div>
                      <div className="font-mono-noc text-text-noc">{iface.packets_in?.toLocaleString() || 0}</div>
                    </div>
                    <div>
                      <div className="text-muted mb-0.5">Packets OUT</div>
                      <div className="font-mono-noc text-text-noc">{iface.packets_out?.toLocaleString() || 0}</div>
                    </div>
                    <div>
                      <div className="text-muted mb-0.5">Errors</div>
                      <div className={`font-mono-noc ${(iface.errors_in + iface.errors_out) > 0 ? 'text-danger' : 'text-text-noc'}`}>
                        {iface.errors_in + iface.errors_out}
                      </div>
                    </div>
                    <div>
                      <div className="text-muted mb-0.5">Drops</div>
                      <div className={`font-mono-noc ${(iface.drops_in + iface.drops_out) > 0 ? 'text-accent3' : 'text-text-noc'}`}>
                        {iface.drops_in + iface.drops_out}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
