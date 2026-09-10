import type { PageId } from '../types'

const navItems = [
  { id: 'dashboard' as PageId, label: 'Dashboard', icon: '\u2B21', section: 'MONITOR' },
  { id: 'devices' as PageId, label: 'Devices', icon: '\u25C8', section: 'MONITOR' },
  { id: 'topology' as PageId, label: 'Topology', icon: '\u25C9', section: 'MONITOR' },
  { id: 'traffic' as PageId, label: 'Traffic', icon: '\u25B2', section: 'ANALYTICS' },
  { id: 'performance' as PageId, label: 'Performance', icon: '\u25CE', section: 'ANALYTICS' },
  { id: 'alerts' as PageId, label: 'Alerts', icon: '\u26A0', section: 'ALERTS' },
  { id: 'about' as PageId, label: 'About', icon: '\u2139', section: 'INFO' },
]

interface SidebarProps {
  activePage: PageId
  onNavigate: (page: PageId) => void
  onScan: () => void
  alertCount: number
  scanning: boolean
}

export default function Sidebar({ activePage, onNavigate, alertCount }: SidebarProps) {
  const sections = navItems.reduce<Record<string, typeof navItems>>((acc, item) => {
    if (!acc[item.section]) acc[item.section] = []
    acc[item.section].push(item)
    return acc
  }, {})

  return (
    <nav className="fixed left-0 top-[58px] bottom-0 w-[220px] bg-panel border-r border-border-noc py-5 z-50 flex flex-col">
      {Object.entries(sections).map(([section, items]) => (
        <div key={section} className="mb-2">
          <div className="text-[10px] tracking-[2px] text-muted px-5 pt-2 pb-1 font-mono-noc">{section}</div>
          {items.map(item => (
            <div
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`flex items-center gap-2.5 px-5 py-2.5 cursor-pointer transition-all border-l-[3px] border-l-transparent font-semibold text-sm tracking-[0.5px] ${
                activePage === item.id
                  ? 'bg-accent/8 border-l-accent text-accent'
                  : 'text-muted hover:bg-accent/5 hover:text-text-noc'
              }`}
            >
              <span className="text-base w-5 text-center">{item.icon}</span> {item.label}
              {item.id === 'alerts' && alertCount > 0 && (
                <span className="ml-auto bg-danger text-white text-[10px] px-1.5 rounded-[10px] font-mono-noc">{alertCount}</span>
              )}
            </div>
          ))}
        </div>
      ))}
    </nav>
  )
}
