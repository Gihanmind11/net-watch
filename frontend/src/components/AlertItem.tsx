import type { Alert } from '../types'

function formatTime(ts: string): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    if (isNaN(d.getTime())) return ts
    const diff = Math.floor((Date.now() - d.getTime()) / 1000)
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return d.toLocaleDateString()
  } catch {
    return ts
  }
}

const dotColors: Record<string, string> = {
  crit: 'bg-danger shadow-[0_0_8px_var(--color-danger)]',
  warn: 'bg-warn shadow-[0_0_8px_var(--color-warn)]',
  new: 'bg-new-device shadow-[0_0_8px_var(--color-new-device)]',
  info: 'bg-accent shadow-[0_0_8px_var(--color-accent)]',
}

interface AlertItemProps {
  alert: Alert
}

export default function AlertItem({ alert }: AlertItemProps) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border-noc/40 last:border-b-0">
      <div className={`w-2 h-2 rounded-full mt-1 shrink-0 ${dotColors[alert.level] || dotColors.info}`} />
      <div>
        <div className="text-[13px] leading-[1.4]">{alert.message}</div>
        <div className="font-mono-noc text-[10px] text-muted mt-0.5">{formatTime(alert.created_at)}</div>
      </div>
    </div>
  )
}
