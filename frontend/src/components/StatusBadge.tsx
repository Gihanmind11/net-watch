interface StatusBadgeProps {
  status: string
}

const config: Record<string, { cls: string; dot: string; label: string }> = {
  up: { cls: 'bg-accent2/12 text-accent2 border border-accent2/30', dot: 'bg-accent2 shadow-[0_0_8px_var(--color-accent2)]', label: 'ONLINE' },
  warn: { cls: 'bg-warn/12 text-warn border border-warn/30', dot: 'bg-warn shadow-[0_0_8px_var(--color-warn)]', label: 'WARN' },
  down: { cls: 'bg-danger/12 text-danger border border-danger/30', dot: 'bg-danger shadow-[0_0_8px_var(--color-danger)]', label: 'OFFLINE' },
  unknown: { cls: 'bg-muted/12 text-muted border border-muted/30', dot: 'bg-muted', label: 'UNKNOWN' },
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const c = config[status] || config.unknown
  return (
    <span className={`inline-flex items-center gap-[5px] px-2.5 py-[3px] rounded-[12px] text-[11px] font-semibold tracking-[0.5px] ${c.cls}`}>
      <div className={`w-[7px] h-[7px] rounded-full ${c.dot}`} />
      {c.label}
    </span>
  )
}
