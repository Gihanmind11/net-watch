import type { AlertResponse, Device, LoginResponse, NetworkInterface, ScanResult, Stats, TopologyData, WifiInfo } from './types'

const API_BASE = '/api'

let accessToken = ''
let refreshPromise: Promise<string | null> | null = null

export function setAccessToken(token: string): void {
  accessToken = token
}

/** Token is held in memory, but also persisted by App; fall back to storage
 * after a page reload so the api client stays authenticated without a round
 * trip through React state. */
function getStoredToken(): string {
  if (accessToken) return accessToken
  accessToken = localStorage.getItem('nw_access_token') || ''
  return accessToken
}

/** Swap the expired access token for a fresh one using the 7-day refresh
 * token. Returns the new token, or null when the refresh itself fails. */
async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem('nw_refresh_token')
  if (!refresh) return null
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!res.ok) return null
  const data = (await res.json()) as { access_token: string; refresh_token?: string }
  accessToken = data.access_token
  localStorage.setItem('nw_access_token', data.access_token)
  if (data.refresh_token) localStorage.setItem('nw_refresh_token', data.refresh_token)
  return accessToken
}

function authHeaders(token: string): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function http<T>(path: string, init: RequestInit = {}): Promise<T> {
  const doFetch = (token: string) =>
    fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...authHeaders(token), ...(init.headers as Record<string, string> | undefined) },
    })

  let token = getStoredToken()
  let res = await doFetch(token)

  if (res.status === 401 && token) {
    // Access token expired — silently refresh (deduplicated across parallel
    // calls), then retry the request once. On failure the caller sees the 401.
    refreshPromise ??= refreshAccessToken().finally(() => { refreshPromise = null })
    const fresh = await refreshPromise
    if (fresh) res = await doFetch(fresh)
  }

  if (!res.ok) throw new Error(`API ${res.status} on ${path}`)
  return (await res.json()) as T
}

export const login = async (username: string, password: string): Promise<LoginResponse> => {
  const data = await http<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  setAccessToken(data.access_token)
  return data
}

export const logout = async (): Promise<void> => {
  try {
    await http('/auth/logout', { method: 'POST' })
  } finally {
    setAccessToken('')
  }
}

export const getStats = () => http<Stats>('/stats')

export const getWifi = () => http<WifiInfo>('/wifi')

export const getDevices = () => http<{ devices: Device[] }>('/devices')

export const resetDevices = () => http<{ status: string }>('/devices', { method: 'DELETE' })

export const scanNetwork = () => http<ScanResult>('/scan', { method: 'POST' })

export const getAlerts = () => http<AlertResponse>('/alerts')

export const resolveAlert = (alertId: number) => http<{ status: string }>(`/alerts/${alertId}`, { method: 'DELETE' })

export const clearAlerts = () => http<{ status: string }>('/alerts', { method: 'DELETE' })

export const getBandwidth = () => http<BandwidthResponse>('/bandwidth')

export const getTopology = () => http<TopologyData>('/topology')

export const getInterfaces = () => http<{ interfaces: NetworkInterface[] }>('/bandwidth/interfaces')

export type LiveEvent = { type: string; payload: unknown }

/**
 * Subscribe to real-time push events from the backend WebSocket.
 * Returns an unsubscribe function. Automatically reconnects.
 */
export function subscribeLive(onEvent: (event: LiveEvent) => void): () => void {
  let closed = false
  let ws: WebSocket | null = null
  let retry: ReturnType<typeof setTimeout> | null = null

  const connect = () => {
    if (closed) return
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${window.location.host}/ws`)
    ws.onmessage = (e) => {
      try {
        onEvent(JSON.parse(e.data) as LiveEvent)
      } catch {
        // ignore malformed frames
      }
    }
    ws.onclose = () => {
      ws = null
      retry = setTimeout(connect, 3000)
    }
  }

  connect()
  return () => {
    closed = true
    if (ws) ws.close()
    if (retry) clearTimeout(retry)
  }
}

export interface BandwidthInterface {
  interface: string
  mbps_in: number
  mbps_out: number
  speed_mbps: number
  utilization: number
  total_in: number
  total_out: number
  packets_in: number
  packets_out: number
  errors_in: number
  errors_out: number
  drops_in: number
  drops_out: number
}

export interface LanTraffic {
  available: boolean
  source: 'snmp'
  reason?: string
  gateway?: string
  interface?: string
  interface_index?: string
  mbps_in?: number
  mbps_out?: number
  speed_mbps?: number
  utilization?: number
  warming_up?: boolean
  updated_at?: string
}

export interface BandwidthResponse {
  current: Record<string, BandwidthInterface>
  history: { recorded_at: string; bytes_in: number; bytes_out: number }[]
  protocols?: Record<string, number>
  lan?: LanTraffic | null
}