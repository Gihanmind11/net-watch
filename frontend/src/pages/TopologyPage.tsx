import { useState, useEffect, useRef, useCallback } from 'react'
import type { TopologyData, TopologyNode } from '../types'

const API = 'http://localhost:5000/api'

export default function TopologyPage() {
  const [topoData, setTopoData] = useState<TopologyData>({ nodes: [], edges: [] })
  const [selected, setSelected] = useState<TopologyNode | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const headers = { 'Authorization': `Bearer ${localStorage.getItem('nw_token') || ''}` }

  useEffect(() => {
    fetch(`${API}/topology`, { headers }).then(r => r.json()).then(setTopoData).catch(() => {})
  }, [])

  const drawTopology = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || topoData.nodes.length === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const W = canvas.width; const H = canvas.height
    ctx.clearRect(0, 0, W, H)

    ctx.strokeStyle = 'rgba(26,58,92,0.2)'; ctx.lineWidth = 1
    for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke() }
    for (let y = 0; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke() }

    const nodeMap: Record<string, TopologyNode> = {}
    topoData.nodes.forEach(n => { nodeMap[n.id] = n })

    topoData.edges.forEach(([a, b]) => {
      const nA = nodeMap[a]; const nB = nodeMap[b]
      if (!nA || !nB) return
      ctx.beginPath(); ctx.moveTo(nA.x, nA.y); ctx.lineTo(nB.x, nB.y)
      ctx.strokeStyle = 'rgba(0,212,255,0.25)'; ctx.lineWidth = 1.5; ctx.stroke()
    })

    topoData.nodes.forEach(n => {
      const color = n.status === 'up' ? '#00ff88' : n.status === 'warn' ? '#ffcc00' : '#ff3355'
      const isCore = n.type === 'router' || n.type === 'switch' || n.type === 'firewall'
      const r = isCore ? 14 : 10
      const rgbaMap: Record<string, string> = { '#00ff88': '0,255,136', '#ffcc00': '255,204,0', '#ff3355': '255,51,85' }
      const rgb = rgbaMap[color] || '0,212,255'

      const grd = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 2.5)
      grd.addColorStop(0, `rgba(${rgb},0.3)`); grd.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = grd; ctx.beginPath(); ctx.arc(n.x, n.y, r * 2.5, 0, Math.PI * 2); ctx.fill()

      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke()

      ctx.beginPath(); ctx.arc(n.x, n.y, r - 2, 0, Math.PI * 2)
      ctx.fillStyle = isCore ? 'rgba(0,212,255,0.2)' : 'rgba(0,20,40,0.8)'; ctx.fill()

      ctx.fillStyle = color; ctx.font = `${isCore ? 12 : 9}px Share Tech Mono`
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
      const iconMap: Record<string, string> = { router: 'R', switch: 'S', server: 'SV', ap: 'AP', firewall: 'FW' }
      ctx.fillText(iconMap[n.type] || '\u2B21', n.x, n.y)

      ctx.fillStyle = 'rgba(200,224,244,0.8)'; ctx.font = '9px Rajdhani'
      ctx.fillText(n.label, n.x, n.y + r + 10)
    })
  }, [topoData])

  useEffect(() => { drawTopology() }, [drawTopology])

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left; const my = e.clientY - rect.top
    const scaleX = canvas.width / rect.width; const scaleY = canvas.height / rect.height
    const cx = mx * scaleX; const cy = my * scaleY
    for (const n of topoData.nodes) {
      const dx = cx - n.x; const dy = cy - n.y
      if (Math.sqrt(dx * dx + dy * dy) < 18) { setSelected(n); return }
    }
  }

  const statusColor = (s: string) => s === 'up' ? 'bg-accent2/12 text-accent2 border-accent2/30' : s === 'warn' ? 'bg-warn/12 text-warn border-warn/30' : 'bg-danger/12 text-danger border-danger/30'

  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u25C9'} <span className="text-accent">Network</span> Topology
      </div>

      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden mb-4">
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-border-noc bg-panel2">
          <div className="font-display font-bold text-sm tracking-[1px] text-accent">Live Network Map</div>
          <div className="text-[11px] text-muted font-mono-noc">CLICK NODES TO INSPECT</div>
        </div>
        <div className="p-0 relative">
          <canvas ref={canvasRef} width={900} height={340} className="w-full h-[340px] cursor-grab active:cursor-grabbing" onClick={handleCanvasClick} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2"><div className="font-display font-bold text-sm tracking-[1px] text-accent">Legend</div></div>
          <div className="p-4">
            <div className="flex flex-wrap gap-4">
              {[{ color: 'bg-accent2', label: 'Online Host' }, { color: 'bg-danger', label: 'Offline Host' }, { color: 'bg-accent', label: 'Router / Switch' }, { color: 'bg-warn', label: 'Warning' }].map(item => (
                <div key={item.label} className="flex items-center gap-2 text-[13px]">
                  <span className={`w-3 h-3 rounded-full ${item.color} inline-block`} />{item.label}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2">
            <div className="font-display font-bold text-sm tracking-[1px] text-accent">{selected ? selected.label : 'Select a Node'}</div>
          </div>
          <div className={`p-4 text-[13px] ${selected ? 'text-text-noc' : 'text-muted'}`}>
            {selected ? (
              <div className="grid gap-2">
                <div>IP: <b className="text-accent font-mono-noc">{selected.ip}</b></div>
                <div>Type: <b>{(selected.type || '').charAt(0).toUpperCase() + (selected.type || '').slice(1)}</b></div>
                <div>Status: <span className={`inline-flex items-center gap-[5px] px-2.5 py-[3px] rounded-[12px] text-[11px] font-semibold border ${statusColor(selected.status)}`}>{selected.status.toUpperCase()}</span></div>
              </div>
            ) : 'Click on any device node to view details.'}
          </div>
        </div>
      </div>
    </>
  )
}
