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
                  ['Version', '1.0.0'],
                  ['Date', 'May 2026'],
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
              { name: 'React.js', pct: 95, color: 'bg-accent' },
              { name: 'Flask', pct: 85, color: 'bg-accent2' },
              { name: 'Python', pct: 90, color: 'bg-accent3' },
              { name: 'Scapy', pct: 75, color: 'bg-warn' },
              { name: 'SQLite', pct: 80, color: 'bg-[#8844ff]' },
              { name: 'Recharts', pct: 85, color: 'bg-accent' },
              { name: 'psutil', pct: 70, color: 'bg-accent2' },
              { name: 'Cisco PT', pct: 60, color: 'bg-accent3' },
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
              { num: '01', text: 'Detect all devices connected to the LAN using ARP scanning' },
              { num: '02', text: 'Display IP address, MAC address, and device name per device' },
              { num: '03', text: 'Identify and report device status (online / offline)' },
              { num: '04', text: 'Monitor basic bandwidth usage per interface' },
              { num: '05', text: 'Detect new/unauthorized devices and generate alerts' },
              { num: '06', text: 'Provide a modern, interactive dashboard using React.js' },
              { num: '07', text: 'Simulate and visualize network topology using Cisco Packet Tracer' },
              { num: '08', text: 'Basic OS detection per device' },
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
            <div className="text-accent mb-2">LAN DEVICES (PCs, Servers, Printers, Cameras, APs)</div>
            <div>{'\u2193'} ARP / ICMP</div>
            <div className="text-accent2 my-2">PYTHON NETWORK SCANNER (Scapy + psutil)</div>
            <div>{'\u2193'} Writes to</div>
            <div className="text-warn my-2">SQLITE DATABASE (devices, alerts, bandwidth_logs)</div>
            <div>{'\u2193'} Queries</div>
            <div className="text-accent3 my-2">FLASK REST API (/devices, /alerts, /bandwidth, /scan, /topology)</div>
            <div>{'\u2193'} HTTP / JSON</div>
            <div className="text-accent my-2">REACT.JS DASHBOARD (Recharts, Canvas Topology)</div>
          </div>
        </div>
      </div>
    </>
  )
}
