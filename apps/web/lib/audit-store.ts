'use client'

// Simple module-level store. Next.js keeps this module alive across
// client-side navigations (router.push), so state set on /upload is
// still readable on /processing and /results without any backend
// session or database. It resets on a hard refresh — that's fine,
// since a hard refresh means the user re-uploads anyway.

import type { DocKey, Page } from './locate'

export type Evidence = { doc: DocKey; text: string; kind: 'value' | 'label' }

export type AuditFinding = {
  rule_id: string
  title: string
  category: string
  severity: string // "CRITICAL" | "MAJOR" | "MINOR" (whatever rules_config.json defines)
  deduction: number
  regulatory_source: string
  detected_issue: string
  suggested_fix: string
  evidence?: Evidence[]
  suggestions?: { code: string; description: string }[]
}

export type PatientDetails = {
  name?: string
  member_id?: string
  dob?: string
  date_of_service?: string
  principal_diagnosis?: string
  discharge_status?: string
}

export type CheckStatus = 'passed' | 'failed' | 'not_applicable'

export type AuditResult = {
  readiness_score: number
  status: string
  total_violations: number
  patient_details?: PatientDetails
  findings: AuditFinding[]
  checks?: { rule_id: string; title: string; status: CheckStatus; note: string }[]
  checks_summary?: Record<CheckStatus, number>
}

export type Documents = Record<DocKey, { method: 'direct' | 'ocr'; pages: Page[] }>
export type Privacy = { enabled: boolean; masked_total: number; by_type: Record<string, number> }

export type AuditStatus = 'idle' | 'processing' | 'done' | 'error'

// Real pipeline stages reported by the extraction service (see main.py audit_pipeline).
export const STAGES = [
  { key: 'read', label: 'Reading documents' },
  { key: 'mask', label: 'Masking patient identifiers' },
  { key: 'extract', label: 'Extracting claim data with AI' },
  { key: 'audit', label: 'Running rule checks' },
  { key: 'previews', label: 'Preparing document previews' },
] as const
export type StageKey = (typeof STAGES)[number]['key']
export type Progress = {
  active: StageKey | null
  done: StageKey[]
  details: Partial<Record<StageKey, string>>
  notes: Partial<Record<StageKey, string>>
  startedAt: Partial<Record<StageKey, number>>
  finishedAt: Partial<Record<StageKey, number>>
}
const emptyProgress: Progress = { active: null, done: [], details: {}, notes: {}, startedAt: {}, finishedAt: {} }

type State = {
  status: AuditStatus
  result: AuditResult | null
  error: string | null
  // v2: page images + word boxes for evidence highlighting, privacy summary, real progress
  documents: Documents | null
  privacy: Privacy | null
  version: string | null
  progress: Progress
}

const initial: State = {
  status: 'idle', result: null, error: null, documents: null, privacy: null, version: null,
  progress: emptyProgress,
}
let state: State = initial
const listeners = new Set<() => void>()

function setState(next: Partial<State>) {
  state = { ...state, ...next }
  listeners.forEach((l) => l())
}

export function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getState() {
  return state
}

// FastAPI's `detail` can be a plain string OR (for our document-type
// validation) an object like { message, reasons: [...] }. Normalize
// either shape into one readable string for the UI.
function extractErrorMessage(detail: unknown, fallback: string): string {
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail !== null) {
    const d = detail as { message?: string; reasons?: string[] }
    if (d.message) {
      return d.reasons?.length ? `${d.message} ${d.reasons.join(' ')}` : d.message
    }
  }
  return fallback
}

type StreamEvent =
  | { type: 'stage'; stage: StageKey; status: 'active' | 'done'; detail?: string }
  | { type: 'note'; stage: StageKey; detail: string }
  | { type: 'result'; data: any } // eslint-disable-line @typescript-eslint/no-explicit-any
  | { type: 'error'; status: number; detail: unknown }

function applyProgress(e: StreamEvent) {
  if (e.type !== 'stage' && e.type !== 'note') return
  const p = state.progress
  const now = Date.now()
  if (e.type === 'note') {
    setState({ progress: { ...p, notes: { ...p.notes, [e.stage]: e.detail } } })
  } else if (e.status === 'active') {
    setState({ progress: { ...p, active: e.stage, startedAt: { ...p.startedAt, [e.stage]: p.startedAt[e.stage] ?? now } } })
  } else {
    setState({ progress: {
      ...p,
      active: p.active === e.stage ? null : p.active,
      done: [...new Set([...p.done, e.stage])],
      details: e.detail ? { ...p.details, [e.stage]: e.detail } : p.details,
      startedAt: { ...p.startedAt, [e.stage]: p.startedAt[e.stage] ?? now },
      finishedAt: { ...p.finishedAt, [e.stage]: now },
    } })
  }
}

export async function startAudit(clinicalDoc: File, draftClaim: File) {
  setState({ ...initial, status: 'processing', progress: { ...emptyProgress, active: 'read', startedAt: { read: Date.now() } } })

  const formData = new FormData()
  formData.append('clinical_doc', clinicalDoc)
  formData.append('draft_claim', draftClaim)

  try {
    const res = await fetch('/api/extract', { method: 'POST', body: formData })

    if (!res.ok || !res.body) {
      const body = await res.json().catch(() => ({}))
      throw new Error(extractErrorMessage(body.detail, `Extraction failed (${res.status})`))
    }

    // NDJSON: one progress event per line; the final line is the result or an error.
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
    let buffer = ''
    let data: any = null // eslint-disable-line @typescript-eslint/no-explicit-any
    for (;;) {
      const { value, done } = await reader.read()
      if (value) buffer += value
      const lines = buffer.split('\n')
      buffer = done ? '' : lines.pop() ?? ''
      for (const line of lines) {
        if (!line.trim()) continue
        const event = JSON.parse(line) as StreamEvent
        if (event.type === 'error') throw new Error(extractErrorMessage(event.detail, `Audit failed (${event.status})`))
        if (event.type === 'result') data = event.data
        else applyProgress(event)
      }
      if (done) break
    }
    if (!data) throw new Error('The audit stopped before it finished. Check the extraction service window.')

    const audit = data.audit as AuditResult
    setState({
      status: 'done',
      result: audit,
      documents: data.documents ?? null,
      privacy: data.privacy ?? null,
      version: data.version ?? null,
    })
  } catch (err) {
    setState({
      status: 'error',
      error: err instanceof Error ? err.message : 'Something went wrong during the audit.',
    })
  }
}

export function resetAudit() {
  setState(initial)
}
