'use client'

import { useState } from 'react'
import { ChevronDown, CircleCheck, CircleDashed, CircleX, FileText, TriangleAlert } from 'lucide-react'
import type { Checklist, ChecklistItem, UploadedFile } from '@/lib/audit-store'

/** Which claim documents were uploaded, which are still missing and why, and every file we read. */
export function DocumentsChecklist({ checklist, files }: { checklist: Checklist; files: UploadedFile[] | null }) {
  const { summary } = checklist
  const [open, setOpen] = useState(summary.missing > 0 || summary.form_mismatch > 0)
  // Hide documents this claim does not need and nobody uploaded; they only add noise.
  const items = checklist.items.filter((i) => i.status !== 'not_needed')
  const unrecognised = (files ?? []).filter((f) => f.type === 'other')
  const allThere = summary.missing === 0

  return (
    <section className={`doc-checklist ${allThere ? 'is-complete' : ''}`} aria-label="Documents checklist">
      <button className="doc-checklist-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="doc-checklist-icon">{allThere ? <CircleCheck size={18} /> : <CircleX size={18} />}</span>
        <span className="doc-checklist-title">
          <strong>Documents: {summary.have} of {summary.required} required</strong>
          <span className="mono">
            {allThere ? 'Everything the insurer needs is here' : `${summary.missing} missing`}
            {summary.form_mismatch > 0 && ` · ${summary.form_mismatch} ticked on the form but not uploaded`}
          </span>
        </span>
        <ChevronDown className="finding-chevron" size={16} aria-hidden="true" />
      </button>
      {open && (
        <div className="doc-checklist-body">
          <ul className="doc-items">
            {items.map((item) => <DocItem key={item.type} item={item} />)}
          </ul>
          {unrecognised.length > 0 && (
            <p className="doc-unrecognised">
              <TriangleAlert size={13} aria-hidden="true" /> We couldn&apos;t tell what {unrecognised.length === 1 ? 'this file is' : 'these files are'}: {unrecognised.map((f) => f.name).join(', ')}
            </p>
          )}
        </div>
      )}
    </section>
  )
}

function DocItem({ item }: { item: ChecklistItem }) {
  const Icon = item.status === 'uploaded' ? CircleCheck : item.status === 'missing' ? CircleX : CircleDashed
  return (
    <li className={`doc-item doc-${item.status}`}>
      <Icon className="doc-item-icon" size={15} aria-hidden="true" />
      <div>
        <p className="doc-item-label">
          {item.label}
          {item.status === 'missing' && <span className="doc-tag">Missing</span>}
          {item.status === 'recommended' && <span className="doc-tag">Recommended</span>}
        </p>
        {item.status === 'uploaded'
          ? <p className="doc-item-files">{item.files.map((f) => <span key={f}><FileText size={11} aria-hidden="true" /> {f}</span>)}</p>
          : <p className="doc-item-reason">{item.reason}</p>}
        {item.form_mismatch && <p className="doc-item-warn">Ticked as attached on the claim form, but it wasn&apos;t in your upload.</p>}
      </div>
    </li>
  )
}
