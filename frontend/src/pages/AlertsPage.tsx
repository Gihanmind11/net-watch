import { useState, useEffect, useRef, useCallback } from 'react'
import type { Alert } from '../types'
import AlertItem from '../components/AlertItem'

const API = 'http://localhost:5000/api'

type Filter = 'all' | 'crit' | 'warn' | 'info'

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [counts, setCounts] = useState({ total: 0, critical: 0, warning: 0, info: 0, new_devices: 0 })
  const [filter, setFilter] = useState<Filter>('all')
  const [toast, setToast] = useState<string | null>(null)
  const [clearing, setClearing] = useState(false)
  const prevCriticalRef = useRef(0)
  const prevTotalRef = useRef(0)

  const token = localStorage.getItem('nw_token') || ''
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }

  const fetchAlerts = useCallback(() => {
    fetch(`${API}/alerts`, { headers })
      .then(r => r.json())
      .then(d => {
        const newAlerts: Alert[] = d.alerts || []
        const newCounts = {
          total: d.total || 0,
          critical: d.critical || 0,
          warning: d.warning || 0,
          info: d.info || 0,
          new_devices: d.new_devices || 0,
        }

        // Detect new critical alerts
        if (newCounts.critical > prevCriticalRef.current && prevCriticalRef.current > 0) {
          const diff = newCounts.critical - prevCriticalRef.current
          setToast(`${diff} new critical alert${diff > 1 ? 's' : ''} detected!`)
          setTimeout(() => setToast(null), 4000)
        }
        // Detect any new alerts
        else if (newCounts.total > prevTotalRef.current && prevTotalRef.current > 0) {
          const diff = newCounts.total - prevTotalRef.current
          setToast(`${diff} new alert${diff > 1 ? 's' : ''}`)
          setTimeout(() => setToast(null), 3000)
        }

        prevCriticalRef.current = newCounts.critical
        prevTotalRef.current = newCounts.total
        setAlerts(newAlerts)
        setCounts(newCounts)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchAlerts()
    const id = setInterval(fetchAlerts, 5000)
    return () => clearInterval(id)
  }, [fetchAlerts])

  const handleDismiss = async (alertId: number) => {
    try {
      await fetch(`${API}/alerts/${alertId}/resolve`, { method: 'POST', headers })
      setAlerts(prev => prev.filter(a => a.id !== alertId))
      setCounts(prev => ({ ...prev, total: Math.max(0, prev.total - 1) }))
    } catch {}
  }

  const handleClearAll = async () => {
    if (!confirm('Dismiss all alerts?')) return
    setClearing(true)
    try {
      await fetch(`${API}/alerts/clear`, { method: 'POST', headers })
      setAlerts([])
      setCounts({ total: 0, critical: 0, warning: 0, info: 0, new_devices: 0 })
    } catch {}
    setClearing(false)
  }

  const filtered = filter === 'all'
    ? alerts
    : alerts.filter(a => {
        if (filter === 'warn') return a.level === 'warn' || a.level === 'new'
        return a.level === filter
      })

  const filterButtons: { key: Filter; label: string; count: number; color: string }[] = [
    { key: 'all', label: 'ALL', count: counts.total, color: 'text-text-noc' },
    { key: 'crit', label: 'CRITICAL', count: counts.critical, color: 'text-danger' },
    { key: 'warn', label: 'WARNING', count: counts.warning + counts.new_devices, color: 'text-warn' },
    { key: 'info', label: 'INFO', count: counts.info, color: 'text-accent' },
  ]

  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u26A0'} <span className="text-accent">Alert</span> Center
        <span className="ml-auto flex items-center gap-2 text-[11px] font-mono-noc text-muted">
          <span className="w-2 h-2 rounded-full bg-accent2 animate-pulse" />
          LIVE
        </span>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-panel border border-border-noc rounded-[10px] py-[18px] px-5 relative overflow-hidden before:content-[''] before:absolute before:top-0 before:left-0 before:right-0 before:h-[2px] before:bg-gradient-to-r before:from-transparent before:via-danger before:to-transparent">
          <div className="text-[11px] tracking-[2px] text-muted uppercase mb-2 font-mono-noc">Critical</div>
          <div className="font-display text-[36px] font-extrabold leading-none mb-1.5 text-danger" style={{ textShadow: counts.critical > 0 ? '0 0 20px rgba(255,51,85,0.4)' : 'none' }}>{counts.critical}</div>
          <div className="text-xs text-muted">Immediate action required</div>
          <div className="absolute right-4 top-1/2 -translate-y-1/2 text-[36px] opacity-[0.08]">!</div>
        </div>
        <div className="bg-panel border border-border-noc rounded-[10px] py-[18px] px-5 relative overflow-hidden before:content-[''] before:absolute before:top-0 before:left-0 before:right-0 before:h-[2px] before:bg-gradient-to-r before:from-transparent before:via-accent3 before:to-transparent">
          <div className="text-[11px] tracking-[2px] text-muted uppercase mb-2 font-mono-noc">Warning</div>
          <div className="font-display text-[36px] font-extrabold leading-none mb-1.5 text-accent3">{counts.warning + counts.new_devices}</div>
          <div className="text-xs text-muted">Monitor closely</div>
          <div className="absolute right-4 top-1/2 -translate-y-1/2 text-[36px] opacity-[0.08]">{'\u26A0'}</div>
        </div>
        <div className="bg-panel border border-border-noc rounded-[10px] py-[18px] px-5 relative overflow-hidden before:content-[''] before:absolute before:top-0 before:left-0 before:right-0 before:h-[2px] before:bg-gradient-to-r before:from-transparent before:via-accent before:to-transparent">
          <div className="text-[11px] tracking-[2px] text-muted uppercase mb-2 font-mono-noc">Info</div>
          <div className="font-display text-[36px] font-extrabold leading-none mb-1.5 text-accent">{counts.info}</div>
          <div className="text-xs text-muted">Informational events</div>
          <div className="absolute right-4 top-1/2 -translate-y-1/2 text-[36px] opacity-[0.08]">i</div>
        </div>
      </div>

      {/* Alert List */}
      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
          <div className="flex items-center gap-4">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent">All Alerts</div>
            <div className="flex items-center gap-1">
              {filterButtons.map(f => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`px-2.5 py-1 rounded text-[10px] font-mono-noc tracking-[1px] transition-all border ${
                    filter === f.key
                      ? 'bg-accent/10 border-accent/40 text-accent'
                      : 'border-transparent text-muted hover:text-text-noc hover:bg-panel'
                  }`}
                >
                  {f.label}
                  <span className={`ml-1.5 ${f.color}`}>({f.count})</span>
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleClearAll}
              disabled={clearing || alerts.length === 0}
              className={`flex items-center gap-1.5 px-3 py-1.5 bg-[#ff3355]/10 border border-[#ff3355]/30 rounded-md text-[#ff3355] text-[11px] font-mono-noc tracking-[1px] cursor-pointer transition-all hover:bg-[#ff3355]/20 hover:border-[#ff3355]/50 ${(clearing || alerts.length === 0) ? 'opacity-40 cursor-not-allowed' : ''}`}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
              CLEAR ALL
            </button>
          </div>
        </div>

        <div className="p-4 max-h-[600px] overflow-y-auto">
          {filtered.length === 0 && (
            <div className="text-muted text-center p-[30px] text-[13px]">
              {counts.total === 0 ? 'No active alerts. System is healthy.' : 'No alerts match this filter.'}
            </div>
          )}
          {filtered.map((a, i) => (
            <AlertItem key={a.id || i} alert={a} onDismiss={handleDismiss} isNew={i < 3} />
          ))}
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-[100] bg-panel border border-danger/40 rounded-lg px-5 py-3 shadow-[0_0_24px_rgba(255,51,85,0.2)] animate-fade-in">
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-danger animate-pulse" />
            <span className="text-text-noc text-sm font-mono-noc">{toast}</span>
          </div>
        </div>
      )}
    </>
  )
}
