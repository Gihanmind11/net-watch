import type { Alert } from '../types'

function formatTime(ts: string): string {
  if (!ts) return ''
  try {
    const d = new Date(ts.includes('Z') || ts.includes('+') ? ts : ts + 'Z')
    if (isNaN(d.getTime())) return ts
    const diff = Math.floor((Date.now() - d.getTime()) / 1000)
    if (diff < 0) return 'just now'
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return d.toLocaleDateString()
  } catch {
    return ts
  }
}

const levelConfig: Record<string, { dot: string; badge: string; badgeText: string; label: string }> = {
  crit: {
    dot: 'bg-danger shadow-[0_0_8px_var(--color-danger)]',
    badge: 'bg-danger/15 border-danger/30',
    badgeText: 'text-danger',
    label: 'CRITICAL',
  },
  warn: {
    dot: 'bg-warn shadow-[0_0_8px_var(--color-warn)]',
    badge: 'bg-warn/15 border-warn/30',
    badgeText: 'text-warn',
    label: 'WARNING',
  },
  new: {
    dot: 'bg-new-device shadow-[0_0_8px_var(--color-new-device)]',
    badge: 'bg-new-device/15 border-new-device/30',
    badgeText: 'text-new-device',
    label: 'NEW',
  },
  info: {
    dot: 'bg-accent shadow-[0_0_8px_var(--color-accent)]',
    badge: 'bg-accent/15 border-accent/30',
    badgeText: 'text-accent',
    label: 'INFO',
  },
}

interface AlertItemProps {
  alert: Alert
  onDismiss?: (id: number) => void
  isNew?: boolean
}

export default function AlertItem({ alert, onDismiss, isNew }: AlertItemProps) {
  const cfg = levelConfig[alert.level] || levelConfig.info

  return (
    <div className={`flex items-start gap-3 py-3 px-3 border-b border-border-noc/40 last:border-b-0 rounded-md transition-all hover:bg-panel2 group ${isNew ? 'animate-fade-in' : ''}`}>
      <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${cfg.dot}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-[9px] font-mono-noc tracking-[1.5px] px-1.5 py-0.5 rounded border ${cfg.badge} ${cfg.badgeText}`}>
            {cfg.label}
          </span>
          <span className="font-mono-noc text-[10px] text-muted">{formatTime(alert.created_at)}</span>
        </div>
        <div className="text-[13px] leading-[1.4] text-text-noc">{alert.message}</div>
        {alert.device_ip && (
          <span className="font-mono-noc text-[10px] text-muted mt-1 inline-block">{alert.device_ip}</span>
        )}
      </div>
      {onDismiss && (
        <button
          onClick={() => onDismiss(alert.id)}
          className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1 p-1 rounded hover:bg-[#ff3355]/10 text-muted hover:text-[#ff3355]"
          title="Dismiss alert"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      )}
    </div>
  )
}
