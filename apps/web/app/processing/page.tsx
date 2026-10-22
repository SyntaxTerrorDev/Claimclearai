'use client'

import Link from 'next/link'
import { ArrowRight, Check, CircleDashed, TriangleAlert } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { SiteFooter } from '@/components/site-footer'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getState, subscribe, STAGES } from '@/lib/audit-store'
import { Logo } from '@/components/logo'

// Every step below is driven by real events streamed from the extraction service:
// a step turns "current" when the backend starts it and "complete" when it finishes.

function seconds(from?: number, to?: number) {
  if (!from) return ''
  return `${(((to ?? Date.now()) - from) / 1000).toFixed(1)}s`
}

export default function ProcessingPage() {
  const router = useRouter()
  const [audit, setAudit] = useState(getState())
  const [, setTick] = useState(0)

  useEffect(() => {
    // If someone lands here directly without uploading, send them back.
    if (audit.status === 'idle') {
      router.replace('/upload')
    }
  }, [audit.status, router])

  useEffect(() => {
    const unsubscribe = subscribe(() => setAudit(getState()))
    return unsubscribe
  }, [])

  // Re-render every 100ms so the running step's timer counts up.
  useEffect(() => {
    if (audit.status !== 'processing') return
    const timer = window.setInterval(() => setTick((t) => t + 1), 100)
    return () => window.clearInterval(timer)
  }, [audit.status])

  useEffect(() => {
    if (audit.status === 'done') {
      // brief pause so the last step reads as "complete" before navigating
      const t = window.setTimeout(() => router.push('/results'), 700)
      return () => window.clearTimeout(t)
    }
  }, [audit.status, router])

  const p = audit.progress
  const firstStart = p.startedAt.read

  return (
    <main>
      <header className="site-header shell">
        <Logo />
        <div className="header-actions"><ThemeToggle /><span className="mono">Processing</span></div>
      </header>
      <section className="center-page">
        <div className="processing">
          <p className="mono-label">STEP 02 / ANALYSIS</p>
          <h1>{audit.status === 'error' ? 'Something went wrong.' : audit.status === 'done' ? 'Audit complete.' : 'Auditing your claim.'}</h1>

          {audit.status === 'error' && (
            <p className="process-error"><TriangleAlert size={17} aria-hidden="true" /> {audit.error}</p>
          )}

          <ol className="process-list">
            {STAGES.map(({ key, label }) => {
              const done = p.done.includes(key)
              const current = p.active === key && audit.status === 'processing'
              const failed = p.active === key && audit.status === 'error'
              const note = done ? p.details[key] : p.notes[key]
              return (
                <li key={key} className={done ? 'complete' : current ? 'current' : failed ? 'failed' : ''}>
                  <span className="process-mark">{done ? <Check size={17} /> : current ? <CircleDashed size={17} className="spin-slow" /> : failed ? <TriangleAlert size={17} /> : '—'}</span>
                  <span className="process-text">
                    <span>{label}</span>
                    {note && <small>{note}</small>}
                  </span>
                  <span className="process-time mono">{done || current ? seconds(p.startedAt[key], p.finishedAt[key]) : ''}</span>
                </li>
              )
            })}
          </ol>

          {firstStart && <p className="process-total mono">Total {seconds(firstStart, audit.status === 'processing' ? undefined : p.finishedAt.previews ?? Date.now())}</p>}

          {audit.status === 'error' && <Link className="button" href="/upload" style={{ marginTop: 28 }}>Try again</Link>}
          {audit.status === 'done' && (
            <Link className="button" href="/results" style={{ marginTop: 28 }}>
              View Report <ArrowRight size={17} aria-hidden="true" />
            </Link>
          )}
        </div>
      </section>
      <SiteFooter />
    </main>
  )
}
