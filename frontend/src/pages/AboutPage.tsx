export default function AboutPage() {
  return (
    <>
      <div className="font-display font-extrabold text-2xl text-text-noc tracking-[2px] mb-5 flex items-center gap-3">
        {'\u2139'} <span className="text-accent">About</span> This Project
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2"><div className="font-display font-bold text-sm tracking-[1px] text-accent">Project Details</div></div>
          <div className="p-4">
            <table className="w-full border-collapse">
              <tbody>
                {[
                  ['Project Title', 'Network Monitoring System with Real-Time Dashboard'],
                  ['Student', 'S.W.G Mindana'],
                  ['Index Number', 'GAL/2324/IT/F/0113'],
                  ['Programme', 'Higher National Diploma \u2014 Information Technology'],
                  ['Institute', 'Advanced Technological Institute, Galle'],
                  ['Supervisor', 'Mr. Chamith Samarawickrama'],
                  ['Contact', '0769226443'],
                  ['Email', 'gihanmindana8@gmail.com'],
                  ['Version', '2.0.0'],
                  ['Date', 'August 2026'],
                ].map(([k, v]) => (
                  <tr key={k}>
                    <td className="py-2 px-3 border-b border-border-noc/30 text-muted font-semibold text-[13px] w-[140px]">{k}</td>
                    <td className="py-2 px-3 border-b border-border-noc/30 text-[13px]">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
          <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2"><div className="font-display font-bold text-sm tracking-[1px] text-accent">Technology Stack</div></div>
          <div className="p-4">
            {[
              { name: 'React 19 + TypeScript', pct: 95, color: 'bg-accent' },
              { name: 'FastAPI + Uvicorn', pct: 92, color: 'bg-accent2' },
              { name: 'Python', pct: 90, color: 'bg-accent3' },
              { name: 'SQLAlchemy 2.0', pct: 85, color: 'bg-warn' },
              { name: 'Recharts', pct: 85, color: 'bg-accent' },
              { name: 'Scapy', pct: 80, color: 'bg-[#8844ff]' },
              { name: 'PostgreSQL + TimescaleDB', pct: 78, color: 'bg-accent2' },
              { name: 'SNMPv2c + psutil', pct: 72, color: 'bg-accent3' },
              { name: 'APScheduler', pct: 70, color: 'bg-warn' },
              { name: 'Redis pub/sub', pct: 65, color: 'bg-[#8844ff]' },
            ].map(t => (
              <div key={t.name} className="flex items-center gap-2.5 mb-2.5">
                <div className="w-[100px] text-xs text-muted font-mono-noc">{t.name}</div>
                <div className="flex-1 h-2 bg-accent/10 rounded overflow-hidden">
                  <div className={`h-full rounded ${t.color}`} style={{ width: `${t.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden mb-4">
        <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2"><div className="font-display font-bold text-sm tracking-[1px] text-accent">Project Objectives</div></div>
        <div className="p-4">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))] gap-3">
            {[
              { num: '01', text: 'Detect all devices connected to the LAN using Scapy ARP scanning with an ICMP ping-sweep fallback' },
              { num: '02', text: 'Display IP address, MAC address, hostname, vendor, and OS guess per device' },
              { num: '03', text: 'Track live status (online / offline), ping latency, and uptime percentage per device' },
              { num: '04', text: 'Scan common TCP ports to surface each device\u2019s open ports' },
              { num: '05', text: 'Monitor whole-LAN traffic by polling the router/gateway over SNMPv2c, with local psutil fallback' },
              { num: '06', text: 'Detect new/unauthorized devices and alert on offline hosts, high latency, and port changes' },
              { num: '07', text: 'Push live updates to the dashboard via a Redis pub/sub event bus and WebSockets' },
              { num: '08', text: 'Secure the REST API with JWT access and refresh tokens, persisted to PostgreSQL + TimescaleDB' },
            ].map(obj => (
              <div key={obj.num} className="bg-panel2 border border-border-noc rounded-lg p-3.5 text-[13px] hover:border-accent transition-[border-color]">
                <div className="font-display text-xl font-extrabold text-accent mb-1.5">{obj.num}</div>
                {obj.text}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-panel border border-border-noc rounded-[10px] overflow-hidden">
        <div className="px-[18px] py-3.5 border-b border-border-noc bg-panel2"><div className="font-display font-bold text-sm tracking-[1px] text-accent">System Architecture</div></div>
        <div className="p-4">
          <div className="font-mono-noc text-xs leading-[1.8] text-muted text-center">
            <div className="text-accent mb-2">LAN DEVICES (PCs, Servers, Printers, Cameras, APs, IoT)</div>
            <div>{'\u2193'} ARP / ICMP / TCP / SNMP</div>
            <div className="text-accent2 my-2">PYTHON NETWORK SCANNER (Scapy ARP + ping-sweep, TCP port scan, psutil + SNMPv2c sampler)</div>
            <div>{'\u2193'} Writes to</div>
            <div className="text-warn my-2">POSTGRESQL + TIMESCALEDB (devices, ping_history, alerts, bandwidth_logs) — SQLite dev fallback</div>
            <div>{'\u2193'} Queries</div>
            <div className="text-accent3 my-2">FASTAPI + UVICORN REST API (/auth, /devices, /alerts, /bandwidth, /scan, /topology, /stats, /wifi)</div>
            <div>{'\u2193'} Redis pub/sub {'\u2192'} WS push</div>
            <div className="text-accent my-2">REACT 19 + TYPESCRIPT DASHBOARD (Recharts, Canvas Topology, JWT auth)</div>
          </div>
        </div>
      </div>
    </>
  )
}
