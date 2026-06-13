export type PageId = 'dashboard' | 'devices' | 'topology' | 'traffic' | 'performance' | 'alerts' | 'about';

export interface Device {
  id: number;
  device_name: string;
  ip: string;
  mac: string;
  type: string;
  os: string;
  status: 'up' | 'down' | 'warn' | 'unknown';
  ping_ms: number;
  uptime_pct: number;
  open_ports: string;
  last_seen: string;
  first_seen: string;
}

export interface Alert {
  id: number;
  level: 'info' | 'warn' | 'crit' | 'new';
  message: string;
  device_ip?: string;
  created_at: string;
}

export interface Stats {
  total_devices: number;
  online: number;
  offline: number;
  avg_latency: number;
}

export interface Talker {
  device_name: string;
  ip: string;
  sent_mb: number;
  recv_mb: number;
}

export interface User {
  id: number;
  username: string;
  role: string;
  permissions: string[];
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: User;
}

export interface ScanResult {
  status: string;
  devices_found: number;
  new_devices: number;
  scan_duration_ms: number;
  timestamp: string;
}

export interface AlertResponse {
  count: number;
  alerts: Alert[];
  critical?: number;
  warning?: number;
  new?: number;
}
