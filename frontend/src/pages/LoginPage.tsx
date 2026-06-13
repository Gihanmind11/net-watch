import { useState, useEffect, useRef } from 'react'
import type { LoginResponse } from '../types'

const API = 'http://localhost:5000/api'

interface LoginPageProps {
  onLogin: (response: LoginResponse) => void
}

interface Particle {
  x: number; y: number; vx: number; vy: number; r: number; o: number
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({})
  const [globalError, setGlobalError] = useState('')
  const [loading, setLoading] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  // Frontend validation
  const validateForm = (): boolean => {
    const newErrors: { username?: string; password?: string } = {}
    let isValid = true

    if (!username || username.trim() === '') {
      newErrors.username = 'Username is required'
      isValid = false
    }

    if (!password || password.length < 3) {
      newErrors.password = 'Password is required and must be at least 3 characters'
      isValid = false
    }

    setErrors(newErrors)
    return isValid
  }

  // 3D Particle animation
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let W = window.innerWidth
    let H = window.innerHeight
    canvas.width = W
    canvas.height = H

    const particles: Particle[] = []
    for (let i = 0; i < 80; i++) {
      particles.push({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        r: Math.random() * 2 + 1,
        o: Math.random() * 0.4 + 0.1,
      })
    }

    let animId: number
    const draw = () => {
      ctx.clearRect(0, 0, W, H)

      // Draw connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 150) {
            ctx.beginPath()
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.strokeStyle = `rgba(0,212,255,${0.08 * (1 - dist / 150)})`
            ctx.lineWidth = 0.5
            ctx.stroke()
          }
        }
      }

      // Draw particles
      for (const p of particles) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(0,212,255,${p.o})`
        ctx.fill()

        // Glow
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r * 3, 0, Math.PI * 2)
        const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 3)
        grad.addColorStop(0, `rgba(0,212,255,${p.o * 0.3})`)
        grad.addColorStop(1, 'rgba(0,212,255,0)')
        ctx.fillStyle = grad
        ctx.fill()

        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > W) p.vx *= -1
        if (p.y < 0 || p.y > H) p.vy *= -1
      }

      animId = requestAnimationFrame(draw)
    }
    draw()

    const handleResize = () => {
      W = window.innerWidth
      H = window.innerHeight
      canvas.width = W
      canvas.height = H
    }
    window.addEventListener('resize', handleResize)

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', handleResize)
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setGlobalError('')
    setErrors({})

    // Frontend validation first
    if (!validateForm()) return

    setLoading(true)

    try {
      const res = await fetch(`${API}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const data = await res.json()
      if (!res.ok) {
        setGlobalError(data.error || 'Login failed')
        setLoading(false)
        return
      }
      onLogin(data)
    } catch {
      setGlobalError('Server unreachable. Please check your connection.')
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center overflow-hidden"
      style={{ background: 'linear-gradient(135deg, #030b14 0%, #071422 40%, #0a1e30 100%)' }}>

      {/* 3D Particle Canvas */}
      <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />

      {/* Animated grid background */}
      <div className="absolute inset-0 opacity-[0.03]"
        style={{ backgroundImage: 'linear-gradient(rgba(0,212,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.3) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />

      {/* Scan line */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute w-full h-[2px] bg-gradient-to-r from-transparent via-accent/25 to-transparent"
          style={{ animation: 'scanline 5s ease-in-out infinite', boxShadow: '0 0 15px rgba(0,212,255,0.2), 0 0 40px rgba(0,212,255,0.05)' }} />
      </div>

      {/* Glow orbs */}
      <div className="absolute top-1/4 left-1/4 w-[300px] h-[300px] rounded-full opacity-[0.04] blur-[80px]"
        style={{ background: 'radial-gradient(circle, #00d4ff, transparent)' }} />
      <div className="absolute bottom-1/4 right-1/4 w-[200px] h-[200px] rounded-full opacity-[0.04] blur-[60px]"
        style={{ background: 'radial-gradient(circle, #00ff88, transparent)' }} />

      {/* Login Card */}
      <div className="relative w-[420px] bg-[#0b1623]/90 border border-accent/20 rounded-xl overflow-hidden backdrop-blur-md"
        style={{ boxShadow: '0 0 60px rgba(0,212,255,0.1), 0 0 120px rgba(0,212,255,0.03), inset 0 1px 0 rgba(0,212,255,0.1)' }}>

        {/* Top accent line */}
        <div className="h-[2px] bg-gradient-to-r from-transparent via-accent to-transparent" />

        <div className="p-8">
          {/* Logo / Title */}
          <div className="text-center mb-8">
            <div className="inline-block mb-4">
              {/* Outer glow ring */}
              <div className="relative w-[72px] h-[72px] mx-auto">
                <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-accent/20 to-accent2/20 animate-pulse-ring" />
                <div className="absolute inset-[3px] rounded-[13px] bg-gradient-to-br from-[#0b1623] to-[#081020] border border-accent/30"
                  style={{ boxShadow: '0 0 30px rgba(0,212,255,0.3), inset 0 0 20px rgba(0,212,255,0.05)' }}>
                  <div className="w-full h-full flex items-center justify-center">
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" className="drop-shadow-[0_0_8px_rgba(0,212,255,0.6)]">
                      {/* Globe */}
                      <circle cx="12" cy="12" r="10" stroke="#00d4ff" strokeWidth="1.5" opacity="0.8" />
                      <ellipse cx="12" cy="12" rx="4" ry="10" stroke="#00d4ff" strokeWidth="1" opacity="0.5" />
                      <line x1="2" y1="12" x2="22" y2="12" stroke="#00d4ff" strokeWidth="1" opacity="0.5" />
                      <line x1="12" y1="2" x2="12" y2="22" stroke="#00d4ff" strokeWidth="1" opacity="0.3" />
                      {/* Signal waves */}
                      <path d="M18 4c2 2 2 6 0 8" stroke="#00ff88" strokeWidth="1.5" strokeLinecap="round" fill="none" opacity="0.7" />
                      <path d="M20 2c3 3 3 9 0 12" stroke="#00ff88" strokeWidth="1" strokeLinecap="round" fill="none" opacity="0.4" />
                      {/* Center dot */}
                      <circle cx="12" cy="12" r="2" fill="#00d4ff" opacity="0.9">
                        <animate attributeName="r" values="2;2.5;2" dur="2s" repeatCount="indefinite" />
                        <animate attributeName="opacity" values="0.9;0.5;0.9" dur="2s" repeatCount="indefinite" />
                      </circle>
                      {/* Orbiting dot */}
                      <circle r="1.5" fill="#00ff88" opacity="0.8">
                        <animateMotion dur="6s" repeatCount="indefinite" path="M12,2 a10,10 0 1,1 -0.01,0z" />
                      </circle>
                    </svg>
                  </div>
                </div>
              </div>
            </div>
            <h1 className="font-display font-extrabold text-[28px] tracking-[5px] text-text-noc mb-1"
              style={{ textShadow: '0 0 40px rgba(0,212,255,0.4), 0 0 80px rgba(0,212,255,0.1)' }}>
              NET<span className="text-accent2" style={{ textShadow: '0 0 30px rgba(0,255,136,0.4)' }}>WATCH</span>
            </h1>
            <div className="flex items-center justify-center gap-2 mt-2">
              <div className="w-8 h-px bg-gradient-to-r from-transparent to-accent/50" />
              <p className="text-muted text-[11px] font-mono-noc tracking-[3px]">NETWORK MONITORING SYSTEM</p>
              <div className="w-8 h-px bg-gradient-to-l from-transparent to-accent/50" />
            </div>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex-1 h-px bg-gradient-to-r from-transparent to-border-noc" />
            <span className="text-[10px] text-accent/60 font-mono-noc tracking-[2px]">SECURE ACCESS</span>
            <div className="flex-1 h-px bg-gradient-to-l from-transparent to-border-noc" />
          </div>

          {/* Error messages */}
          {globalError && (
            <div className="mb-4 px-4 py-2.5 bg-[#ff3355]/10 border border-[#ff3355]/30 rounded-md text-[#ff3355] text-xs font-mono-noc flex items-center gap-2 animate-fade-in">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {globalError}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[11px] text-muted font-mono-noc tracking-[1px] mb-1.5 uppercase">Username</label>
              <div className="relative">
                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-accent/40">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                  </svg>
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); passwordRef.current?.focus() } }}
                  placeholder="admin"
                  className={`w-full pl-10 pr-4 py-2.5 bg-[#081020] border rounded-md text-text-noc text-sm font-mono-noc placeholder:text-[#1a3a5c] outline-none transition-all focus:shadow-[0_0_15px_rgba(0,212,255,0.1)] ${errors.username ? 'border-[#ff3355]/60 focus:border-[#ff3355]' : 'border-border-noc focus:border-accent/50'}`}
                  autoComplete="username"
                />
              </div>
              {errors.username && (
                <p className="mt-1.5 text-[#ff3355] text-[10px] font-mono-noc">{errors.username}</p>
              )}
            </div>
            <div>
              <label className="block text-[11px] text-muted font-mono-noc tracking-[1px] mb-1.5 uppercase">Password</label>
              <div className="relative">
                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-accent/40">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                </div>
                <input
                  ref={passwordRef}
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className={`w-full pl-10 pr-10 py-2.5 bg-[#081020] border rounded-md text-text-noc text-sm font-mono-noc placeholder:text-[#1a3a5c] outline-none transition-all focus:shadow-[0_0_15px_rgba(0,212,255,0.1)] ${errors.password ? 'border-[#ff3355]/60 focus:border-[#ff3355]' : 'border-border-noc focus:border-accent/50'}`}
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-accent transition-colors cursor-pointer bg-transparent border-none p-0"
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
              {errors.password && (
                <p className="mt-1.5 text-[#ff3355] text-[10px] font-mono-noc">{errors.password}</p>
              )}
            </div>
            <button
              type="submit"
              disabled={loading}
              className={`w-full py-3 mt-2 bg-gradient-to-r from-accent to-[#0088aa] border-none rounded-md text-black font-display font-bold text-[13px] tracking-[2px] uppercase cursor-pointer transition-all hover:shadow-[0_0_30px_rgba(0,212,255,0.4)] hover:-translate-y-px active:translate-y-0 ${loading ? 'opacity-70 cursor-not-allowed' : ''}`}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                  AUTHENTICATING...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                  AUTHENTICATE
                </span>
              )}
            </button>
          </form>

          {/* Footer */}
          <div className="mt-6 pt-4 border-t border-border-noc/50 text-center">
            <p className="text-[10px] text-[#1a3a5c] font-mono-noc tracking-[1px]">SECURED CONNECTION • ENCRYPTED CHANNEL</p>
          </div>
        </div>

        {/* Bottom accent line */}
        <div className="h-[2px] bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
      </div>
    </div>
  )
}
