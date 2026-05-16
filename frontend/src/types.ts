export interface Device {
  id: number;
  hostname: string;
  ip: string;
  mac: string;
  type: string;
  os: string;
  status: 'up' | 'down' | 'warn' | 'unknown';
  ping_ms: number;
  uptime_pct: number;
  last_seen: string;
  first_seen: string;
}

export interface Alert {
  id: number;
  level: 'crit' | 'warn' | 'new' | 'info';
  message: string;
  device_ip: string;
  created_at: string;
}

export interface AlertResponse {
  total: number;
  critical: number;
  warning: number;
  new_devices: number;
  info: number;
  alerts: Alert[];
}

export interface Stats {
  total_devices: number;
  online: number;
  offline: number;
  warning: number;
  new_devices: number;
  avg_latency: number;
}

export interface TopologyNode {
  id: string;
  label: string;
  ip: string;
  type: string;
  x: number;
  y: number;
  status: string;
}

export type TopologyEdge = [string, string];

export interface TopologyData {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface NetworkInterface {
  name: string;
  ip: string;
  speed: string;
  total_in: number;
  total_out: number;
  packets_in: number;
  packets_out: number;
  errors: number;
  drops: number;
  status: string;
}

export interface Protocol {
  protocol: string;
  percentage: number;
  color: string;
}

export interface Talker {
  hostname: string;
  ip: string;
  sent_mb: number;
  recv_mb: number;
}

export interface PduStep {
  step: number;
  action: string;
  detail: string;
  from: string;
  to: string;
}

export interface ScanResult {
  status: string;
  devices_found: number;
  new_devices: number;
  scan_duration_ms: number;
  timestamp: string;
}

export type PageId = 'dashboard' | 'devices' | 'topology' | 'traffic' | 'performance' | 'alerts' | 'about';
