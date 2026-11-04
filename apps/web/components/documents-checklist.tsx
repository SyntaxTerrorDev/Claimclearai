'use client'

import { useState } from 'react'
import { ChevronDown, CircleCheck, CircleDashed, CircleX, FileText, TriangleAlert } from 'lucide-react'
import type { Checklist, ChecklistItem, UploadedFile } from '@/lib/audit-store'

/** Which claim documents were uploaded, which are still missing and why, and every file we read. */
export function DocumentsChecklist({ checklist, files }: { checklist: Checklist; files: UploadedFile[] | null }) {
  const { summary } = checklist
  const [open, setOpen] = useState(summary.missing > 0 || summary.form_mismatch > 0)
  // Hide documents this claim does not need and nobody uploaded; they only add noise.
  const items = checklist.items.filter((i) => i.status !== 'not_needed' || i.form_mismatch)
  const unrecognised = (files ?? []).filter((f) => f.type === 'other')
  const allThere = summary.missing === 0
  const byName = new Map((files ?? []).map((f) => [f.name, f]))
  // One merged upload: name the file once, then list only page numbers per document.
  const sources = new Set((files ?? []).map((f) => f.merged_from ?? f.name))
  const singleSource = sources.size === 1 && (files ?? []).some((f) => f.merged_from) ? [...sources][0] : null

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
          {singleSource && <p className="doc-source"><FileText size={12} aria-hidden="true" /> All found in your file <span title={singleSource}>{singleSource}</span></p>}
          <ul className="doc-items">
            {items.map((item) => <DocItem key={item.type} item={item} where={item.files.map((name) => whereLabel(byName.get(name), name))} />)}
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

/** "Pages 10–20" for part of a merged PDF, otherwise the file name. */
function whereLabel(file: UploadedFile | undefined, name: string): string {
  if (!file?.page_range) return name
  const [first, last] = file.page_range
  return first === last ? `Page ${first}` : `Pages ${first}\u2013${last}`
}

function DocItem({ item, where }: { item: ChecklistItem; where: string[] }) {
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
          ? <p className="doc-item-files">{where.map((w, i) => <span key={i} title={item.files[i]}>{w}</span>)}</p>
          : <p className="doc-item-reason">{item.reason}</p>}
        {item.form_mismatch && <p className="doc-item-warn">The claim form says this is attached, but we didn&apos;t find it in your upload.</p>}
      </div>
    </li>
  )
}
