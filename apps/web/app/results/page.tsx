'use client'

import { useState, useEffect, useMemo, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowDownToLine, ChevronDown, CircleAlert, CircleCheck, Crosshair, Info, Loader2, LockKeyhole, ShieldAlert, Sparkles } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { SiteFooter } from '@/components/site-footer'
import { getState, subscribe, AuditFinding } from '@/lib/audit-store'
import { locate } from '@/lib/locate'
import { DocumentViewer, type Callout, type Mark, type Tone } from '@/components/document-viewer'
import { Logo } from '@/components/logo'


const RING_RADIUS = 52
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS

function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3)
}

// Map your backend's severity strings to the tone classes the CSS expects.
function toneFor(severity: string): Tone {
  const s = severity.toUpperCase()
  if (s === 'CRITICAL' || s === 'MAJOR') return 'critical'
  if (s === 'WARNING' || s === 'MODERATE') return 'warning'
  return 'info'
}

const icons = { critical: CircleAlert, warning: ShieldAlert, info: Info }

export default function ResultsPage() {
  const router = useRouter()
  const [audit, setAudit] = useState(getState())
  // undefined = default to the top finding; null = user collapsed everything
  const [openRule, setOpenRule] = useState<string | null | undefined>(undefined)
  const [animatedScore, setAnimatedScore] = useState(0)
  const [isDownloading, setIsDownloading] = useState(false)
  const shownScore = useRef(0)

  useEffect(() => {
    const unsubscribe = subscribe(() => setAudit(getState()))
    return unsubscribe
  }, [])

  useEffect(() => {
    if (audit.status !== 'done' || !audit.result) {
      if (audit.status === 'idle' || audit.status === 'error') router.replace('/upload')
      return
    }
  }, [audit.status, audit.result, router])

  const result = audit.result
  const documents = audit.documents
  const score = result?.readiness_score ?? 0
  const findings = useMemo(() => result?.findings ?? [], [result])

  useEffect(() => {
    if (!result) return
    const from = shownScore.current
    const duration = 1400
    let startTime: number | null = null
    let raf: number
    function tick(timestamp: number) {
      if (startTime === null) startTime = timestamp
      const progress = Math.min((timestamp - startTime) / duration, 1)
      const v = Math.round(from + easeOutCubic(progress) * (score - from))
      shownScore.current = v
      setAnimatedScore(v)
      if (progress < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    // Background tabs throttle rAF; make sure the ring still lands on the real score.
    const settle = window.setTimeout(() => { shownScore.current = score; setAnimatedScore(score) }, duration + 150)
    return () => { cancelAnimationFrame(raf); window.clearTimeout(settle) }
  }, [result, score])

  // Every finding's evidence, located in the PDFs once, numbered in list order.
  const marks: Mark[] = useMemo(() => {
    if (!documents) return []
    return findings.flatMap((f, i) => (f.evidence ?? []).map((e, ei) => ({
      key: `${f.rule_id}-${ei}`, id: f.rule_id, num: i + 1, tone: toneFor(f.severity), doc: e.doc,
      boxes: locate(documents[e.doc]?.pages, e.text, e.kind)?.boxes ?? [],
      missing: e.kind === 'label',
    })))
  }, [findings, documents])

  const selected = openRule === undefined ? findings[0] : findings.find((f) => f.rule_id === openRule)
  const selectedNum = selected ? findings.indexOf(selected) + 1 : 0
  const callout: Callout | null = selected
    ? { id: selected.rule_id, num: selectedNum, tone: toneFor(selected.severity), title: selected.title, issue: selected.detected_issue, fix: selected.suggested_fix }
    : null

  if (!result) return null // redirect effect above handles navigation

  const dashOffset = RING_CIRCUMFERENCE - (animatedScore / 100) * RING_CIRCUMFERENCE
  const counts = findings.reduce(
    (acc, f) => {
      acc[toneFor(f.severity)] += 1
      return acc
    },
    { critical: 0, warning: 0, info: 0 } as Record<Tone, number>,
  )
  const statusLabel = result.status.replace(/_/g, ' ')
  const hidden = audit.privacy?.enabled ? audit.privacy.masked_total : 0

  const handleDownload = async () => {
    setIsDownloading(true)
    try {
      const res = await fetch('/api/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(result),
      })
      if (!res.ok) {
        alert('Failed to generate report. Please try again.')
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'ClaimClear_Audit_Report.pdf'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Download failed:', err)
      alert('Something went wrong generating the report.')
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <main className="report-page">
      <header className="site-header shell">
        <Logo />
        <div className="header-actions">
          <ThemeToggle />
          <button className="button button-small" onClick={handleDownload} disabled={isDownloading}>
            {isDownloading ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <ArrowDownToLine size={15} aria-hidden="true" />}
            {isDownloading ? 'Generating…' : 'Download report'}
          </button>
        </div>
      </header>

      <section className="report-shell shell report-wide" aria-labelledby="report-title">
        <div className="report-summary">
          <div className="score-ring" aria-label={`Claim readiness score ${score} out of 100`}>
            <svg className="score-ring-svg" viewBox="0 0 120 120">
              <circle className="score-ring-track" cx="60" cy="60" r={RING_RADIUS} />
              <circle className="score-ring-progress" cx="60" cy="60" r={RING_RADIUS} style={{ strokeDasharray: RING_CIRCUMFERENCE, strokeDashoffset: dashOffset }} />
            </svg>
            <div className="score-ring-inner"><strong>{animatedScore}</strong><span>READINESS</span></div>
          </div>
          <div className="score-copy">
            <p className="mono-label">CLAIM READINESS SCORE</p>
            <h1 id="report-title">{statusLabel}</h1>
            <p>{result.total_violations} issue{result.total_violations === 1 ? '' : 's'} found. Each one is marked on the document. Fix the red ones before you submit.</p>
            <div className="severity-counts">
              <span className="count-critical"><i />{counts.critical} Critical</span>
              <span className="count-warning"><i />{counts.warning} Warning</span>
              <span className="count-info"><i />{counts.info} Info</span>
            </div>
            {hidden > 0 && (
              <div className="report-pills">
                <span className="pill pill-teal" title="Before the documents were sent to the AI, the patient's name, phone, policy number and similar IDs were replaced with placeholders. The AI never saw them; they were put back on this computer afterwards.">
                  <LockKeyhole size={12} /> {hidden} personal detail{hidden === 1 ? '' : 's'} hidden from the AI
                </span>
              </div>
            )}
          </div>
        </div>

        <div className={`report-body ${documents ? 'has-viewer' : ''}`}>
          <section className="report-main report-findings" aria-label="Issues ranked by impact">
            <p className="mono-label report-list-label">ISSUES · CLICK ONE TO SEE IT ON THE DOCUMENT</p>
            <div className="report-finding-list">
              {findings.map((finding: AuditFinding, index: number) => {
                const tone = toneFor(finding.severity)
                const Icon = icons[tone]
                const isOpen = selected?.rule_id === finding.rule_id
                const onPage = marks.some((m) => m.id === finding.rule_id && m.boxes.length)
                return (
                  <article className={`report-finding ${tone} ${isOpen ? 'is-open' : ''}`} key={finding.rule_id}>
                    <button className="report-finding-trigger" onClick={() => setOpenRule(isOpen ? null : finding.rule_id)} aria-expanded={isOpen}>
                      <span className="finding-num">{index + 1}</span>
                      <span className="finding-title">
                        <strong>{finding.title}</strong>
                        <span className="mono"><span className="severity-badge"><Icon size={11} aria-hidden="true" /> {finding.severity}</span> −{finding.deduction} pts {onPage && <><Crosshair size={10} /> marked on PDF</>}</span>
                      </span>
                      <ChevronDown className="finding-chevron" size={16} aria-hidden="true" />
                    </button>
                    {isOpen && (
                      <div className="finding-details">
                        <div>
                          <p className="detail-label">WHAT&apos;S WRONG</p>
                          <p>{finding.detected_issue}</p>
                        </div>
                        {finding.suggestions && finding.suggestions.length > 0 && (
                          <div className="suggest-panel">
                            <p className="detail-label"><Sparkles size={11} /> CORRECT CODE IS PROBABLY</p>
                            {finding.suggestions.map((s) => (
                              <div className="suggest-row" key={s.code}><span><strong className="mono">{s.code}</strong> {s.description}</span></div>
                            ))}
                          </div>
                        )}
                        <div className="fix-panel">
                          <p className="detail-label">HOW TO FIX</p>
                          <p>{finding.suggested_fix}</p>
                          {finding.regulatory_source && <p className="source-line">Based on: {finding.regulatory_source}</p>}
                        </div>
                      </div>
                    )}
                  </article>
                )
              })}
              {findings.length === 0 && <p className="all-clear"><CircleCheck size={16} /> No issues found. This claim looks ready to submit.</p>}
            </div>
          </section>

          {documents && (
            <aside className="report-viewer" aria-label="Source documents">
              <DocumentViewer documents={documents} marks={marks} selectedId={selected?.rule_id ?? null} callout={callout} onSelect={(id) => setOpenRule(id)} />
            </aside>
          )}
        </div>
      </section>
      <SiteFooter />
    </main>
  )
}
