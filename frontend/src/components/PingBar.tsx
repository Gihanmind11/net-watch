interface PingBarProps {
  ping: number
}

export default function PingBar({ ping }: PingBarProps) {
  if (!ping || ping === 0) {
    return <span className="font-mono-noc text-xs w-[45px] text-danger">&mdash;</span>
  }

  const cls = ping < 20 ? 'text-accent2' : ping < 50 ? 'text-warn' : 'text-danger'
  const fillCls = ping < 20 ? 'bg-gradient-to-r from-[#00a060] to-accent2' : ping < 50 ? 'bg-gradient-to-r from-[#882200] to-accent3' : 'bg-gradient-to-r from-[#880022] to-danger'
  const pct = Math.min(ping, 100)

  return (
    <div className="flex items-center gap-2">
      <span className={`font-mono-noc text-xs w-[45px] ${cls}`}>{Math.round(ping)}ms</span>
      <div className="h-1 rounded-sm bg-accent/10 overflow-hidden w-[60px]">
        <div className={`h-full rounded-sm ${fillCls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
