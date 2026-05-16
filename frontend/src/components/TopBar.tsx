import { useState, useEffect } from 'react'

interface TopBarProps {
  stats: { critical: number; warning: number }
}

export default function TopBar({ stats }: TopBarProps) {
  const [time, setTime] = useState('')

  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('en-GB', { hour12: false }))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <header className="sticky top-0 z-[100] bg-bg-noc/95 border-b border-border-noc backdrop-blur-xl px-6 flex items-center justify-between h-[58px]">
      <div className="flex items-center gap-3 font-display font-extrabold text-[22px] tracking-[2px] text-accent" style={{ textShadow: '0 0 20px rgba(0,212,255,0.3)' }}>
        <div className="w-[34px] h-[34px] border-2 border-accent rounded-md flex items-center justify-center relative overflow-hidden" style={{ boxShadow: '0 0 20px rgba(0,212,255,0.3)' }}>
          <div className="absolute w-[60%] h-[60%] border-2 border-accent2 rounded-full animate-pulse-ring" />
        </div>
        NET<span className="text-accent2">WATCH</span>
      </div>
      <div className="flex items-center gap-5">
        <div className="flex gap-4 items-center">
          <div className="flex items-center gap-1.5 bg-accent/8 border border-accent/20 px-3 py-1 rounded-[20px] text-xs font-semibold tracking-[1px]">
            <div className="w-[7px] h-[7px] rounded-full bg-accent2 shadow-[0_0_8px_var(--color-accent2)] animate-blink" />SYSTEM ONLINE
          </div>
          {stats.warning > 0 && (
            <div className="flex items-center gap-1.5 bg-accent/8 border border-accent/20 px-3 py-1 rounded-[20px] text-xs font-semibold tracking-[1px]">
              <div className="w-[7px] h-[7px] rounded-full bg-warn shadow-[0_0_8px_var(--color-warn)]" />{stats.warning} WARNING{stats.warning > 1 ? 'S' : ''}
            </div>
          )}
          {stats.critical > 0 && (
            <div className="flex items-center gap-1.5 bg-accent/8 border border-accent/20 px-3 py-1 rounded-[20px] text-xs font-semibold tracking-[1px]">
              <div className="w-[7px] h-[7px] rounded-full bg-danger shadow-[0_0_8px_var(--color-danger)]" />{stats.critical} CRITICAL
            </div>
          )}
        </div>
        <div className="font-mono-noc text-[13px] text-muted tracking-[1px]">
          UTC+05:30 &nbsp;|&nbsp; <span className="text-accent">{time}</span>
        </div>
      </div>
    </header>
  )
}
