const colorMap = {
  green: {
    card: 'before:bg-gradient-to-r before:from-transparent before:via-accent2 before:to-transparent',
    value: 'text-accent2',
    shadow: '0 0 20px rgba(0,255,136,0.3)',
  },
  blue: {
    card: 'before:bg-gradient-to-r before:from-transparent before:via-accent before:to-transparent',
    value: 'text-accent',
    shadow: '0 0 20px rgba(0,212,255,0.3)',
  },
  orange: {
    card: 'before:bg-gradient-to-r before:from-transparent before:via-accent3 before:to-transparent',
    value: 'text-accent3',
    shadow: 'none',
  },
  red: {
    card: 'before:bg-gradient-to-r before:from-transparent before:via-danger before:to-transparent',
    value: 'text-danger',
    shadow: 'none',
  },
}

interface KpiCardProps {
  label: string
  value: string | number
  sub: string
  color: keyof typeof colorMap
  icon: string
}

export default function KpiCard({ label, value, sub, color, icon }: KpiCardProps) {
  const c = colorMap[color]
  return (
    <div className={`bg-panel border border-border-noc rounded-[10px] py-[18px] px-5 relative overflow-hidden transition-[border-color] hover:border-accent before:content-[''] before:absolute before:top-0 before:left-0 before:right-0 before:h-[2px] ${c.card}`}>
      <div className="text-[11px] tracking-[2px] text-muted uppercase mb-2 font-mono-noc">{label}</div>
      <div className={`font-display text-[36px] font-extrabold leading-none mb-1.5 ${c.value}`} style={{ textShadow: c.shadow }}>{value}</div>
      <div className="text-xs text-muted">{sub}</div>
      <div className="absolute right-4 top-1/2 -translate-y-1/2 text-[36px] opacity-[0.08]">{icon}</div>
    </div>
  )
}
