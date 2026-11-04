'use client'

import { useState } from 'react'
import { Check, ChevronDown, Hospital, ListTodo, PenLine, Stethoscope, type LucideIcon } from 'lucide-react'
import type { AuditFinding, Checklist } from '@/lib/audit-store'

type Who = 'hospital' | 'doctor' | 'you'
type Todo = { key: string; who: Who; text: string; urgent: boolean }

const GROUPS: { who: Who; icon: LucideIcon; title: string; hint: string }[] = [
  { who: 'hospital', icon: Hospital, title: 'Ask the hospital', hint: 'Take this list to the billing or insurance (TPA) desk' },
  { who: 'doctor', icon: Stethoscope, title: 'Ask your doctor', hint: 'The treating doctor needs to correct these' },
  { who: 'you', icon: PenLine, title: 'Do it yourself', hint: 'You can fix these on your own' },
]

const VERDICT: Record<string, { title: string; text: string }> = {
  READY_TO_SUBMIT: { title: 'This claim looks ready to send.', text: 'Fix anything left on the list below, then send it to the insurance company.' },
  ACTION_REQUIRED: { title: 'Fix a few things before you send this claim.', text: 'If you send it now, the insurance company may ask questions or delay it.' },
  HIGH_REJECTION_RISK: { title: "Don't send this claim yet.", text: 'It will probably be rejected as it is. Fix the things below first.' },
}

/** The audit as a plain-language to-do list, grouped by who can fix each item. Collapsed by default
 *  so the issues and the marked-up documents stay the main view. */
export function ActionPlan({ status, findings, checklist }: { status: string; findings: AuditFinding[]; checklist: Checklist | null }) {
  const [done, setDone] = useState<Set<string>>(new Set())
  const [open, setOpen] = useState(false)
  const todos: Todo[] = []

  for (const f of findings) {
    // Missing documents come from the checklist below, which also knows what was actually uploaded.
    if (checklist && f.rule_id === 'RULE_15_MISSING_MANDATORY_DOCS') continue
    todos.push({ key: f.rule_id, who: f.ask ?? 'hospital', text: f.patient_action || f.suggested_fix, urgent: f.severity.toUpperCase() === 'CRITICAL' })
  }
  for (const item of checklist?.items ?? []) {
    if (item.status === 'missing') {
      todos.push({ key: `doc-${item.type}`, who: 'hospital', urgent: true,
        text: `Get the ${item.label.toLowerCase()} from the hospital and attach it. ${item.reason}` })
    } else if (item.form_mismatch) {
      todos.push({ key: `doc-${item.type}`, who: 'hospital', urgent: false,
        text: `The claim form says the ${item.label.toLowerCase()} is attached, but it wasn't in your upload. Make sure you attach it.` })
    }
  }

  const verdict = VERDICT[status] ?? VERDICT.ACTION_REQUIRED
  const toggle = (key: string) => setDone((current) => {
    const next = new Set(current)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })

  return (
    <section className={`action-plan verdict-${status.toLowerCase()}`} aria-label="What to do next">
      <button className="doc-checklist-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="action-plan-icon"><ListTodo size={18} /></span>
        <span className="doc-checklist-title">
          <strong>What to do next, in simple words{todos.length ? ` · ${todos.length} thing${todos.length === 1 ? '' : 's'}` : ''}</strong>
          <span className="mono">{verdict.title}{todos.length > 0 && ` · ${done.size} of ${todos.length} done`}</span>
        </span>
        <ChevronDown className="finding-chevron" size={16} aria-hidden="true" />
      </button>
      {open && <div className="action-plan-body">
      <p className="action-verdict-text">{todos.length ? verdict.text : 'Nothing to fix. You can send this claim to the insurance company.'}</p>
      {GROUPS.map(({ who, icon: Icon, title, hint }) => {
        const items = todos.filter((t) => t.who === who)
        if (!items.length) return null
        return (
          <div className="action-group" key={who}>
            <div className="action-group-head">
              <span className="action-group-icon"><Icon size={18} aria-hidden="true" /></span>
              <div><h3>{title}</h3><p>{hint}</p></div>
            </div>
            <ul className="action-list">
              {items.map((t) => {
                const isDone = done.has(t.key)
                return (
                  <li key={t.key} className={isDone ? 'is-done' : ''}>
                    <button className="action-check" onClick={() => toggle(t.key)} aria-pressed={isDone} aria-label={isDone ? 'Mark as not done' : 'Mark as done'}>
                      {isDone && <Check size={14} aria-hidden="true" />}
                    </button>
                    <span>{t.urgent && !isDone && <span className="action-urgent">Important</span>}{t.text}</span>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
      </div>}
    </section>
  )
}
