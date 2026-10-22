'use client'

import { useEffect, useRef, useState } from 'react'
import { FileSearch, ScanLine } from 'lucide-react'
import type { Box, DocKey } from '@/lib/locate'
import type { Documents } from '@/lib/audit-store'

export type Tone = 'critical' | 'warning' | 'info'

/** One issue drawn on the PDF: its number, colour and every box where its evidence was found. */
export type Mark = { key: string; id: string; num: number; tone: Tone; doc: DocKey; boxes: Box[]; missing: boolean }

/** The note shown on the page for the selected issue. */
export type Callout = { id: string; num: number; tone: Tone; title: string; issue: string; fix: string }

const DOC_LABEL: Record<DocKey, string> = { clinical: 'Clinical record', claim: 'Draft claim' }

export function DocumentViewer({ documents, marks, selectedId, callout, onSelect }: {
  documents: Documents
  marks: Mark[]
  selectedId: string | null
  callout: Callout | null
  onSelect: (id: string) => void
}) {
  const selectedMarks = marks.filter((m) => m.id === selectedId && m.boxes.length)
  const firstDoc = selectedMarks[0]?.doc
  const [active, setActive] = useState<DocKey>(firstDoc ?? 'claim')
  const scroller = useRef<HTMLDivElement>(null)

  // Jump to the document holding the selected issue.
  useEffect(() => {
    if (firstDoc) setActive(firstDoc)
  }, [selectedId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll its first highlight into the middle of the viewer (not the whole page).
  useEffect(() => {
    const el = scroller.current?.querySelector<HTMLElement>('.hl.is-selected')
    const box = scroller.current
    if (!el || !box) return
    const top = el.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - box.clientHeight / 3
    box.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
  }, [selectedId, active])

  const doc = documents[active]
  const shown = marks.filter((m) => m.doc === active)
  const count = (k: DocKey) => new Set(marks.filter((m) => m.doc === k && m.boxes.length).map((m) => m.id)).size
  // The callout sits next to the first box of the selected issue on this document.
  const anchor = shown.find((m) => m.id === selectedId && m.boxes.length)?.boxes[0]
  const missingHere = selectedId && !anchor && marks.some((m) => m.id === selectedId && m.missing)

  return (
    <div className="viewer">
      <div className="viewer-tabs" role="tablist">
        {(['clinical', 'claim'] as DocKey[]).map((k) => (
          <button key={k} role="tab" aria-selected={active === k} className={active === k ? 'on' : ''} onClick={() => setActive(k)}>
            {DOC_LABEL[k]}
            {count(k) > 0 && <span className="viewer-count" title={`${count(k)} issue(s) marked on this document`}>{count(k)}</span>}
          </button>
        ))}
        <span className="viewer-method" title={doc.method === 'ocr' ? 'Scanned document, read with OCR' : 'Digital PDF text layer'}>
          {doc.method === 'ocr' ? <ScanLine size={12} /> : <FileSearch size={12} />} {doc.method === 'ocr' ? 'Scanned (OCR)' : 'Digital PDF'}
        </span>
      </div>
      {missingHere && callout && (
        <div className={`viewer-note tone-${callout.tone}`}>
          <strong>#{callout.num} {callout.title}:</strong> this information is missing from the document, so there is nothing to highlight. {callout.fix}
        </div>
      )}
      <div className="viewer-pages" ref={scroller}>
        {doc.pages.map((page, p) => (
          <div className="viewer-page" key={p} style={{ aspectRatio: `${page.width} / ${page.height}` }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={page.image} alt={`${DOC_LABEL[active]} page ${p + 1}`} />
            {shown.flatMap((m) => m.boxes.filter((b) => b.page === p).map((b, bi) => {
              const selected = m.id === selectedId
              return (
                <button
                  key={`${m.key}-${bi}`}
                  className={`hl hl-${m.tone} ${selected ? 'is-selected' : selectedId ? 'is-dim' : ''}`}
                  title={`Issue #${m.num}`}
                  aria-label={`Issue ${m.num}`}
                  onClick={() => onSelect(m.id)}
                  style={{ left: `${b.x0 * 100 - 0.4}%`, top: `${b.y0 * 100 - 0.3}%`, width: `${(b.x1 - b.x0) * 100 + 0.8}%`, height: `${(b.y1 - b.y0) * 100 + 0.6}%` }}
                >
                  {bi === 0 && <span className="hl-num">{m.num}</span>}
                </button>
              )
            }))}
            {callout && anchor && anchor.page === p && (
              <div
                className={`callout tone-${callout.tone} ${anchor.y1 > 0.72 ? 'above' : ''}`}
                style={{
                  left: `${Math.min(Math.max(anchor.x0, 0.02), 0.5) * 100}%`,
                  ...(anchor.y1 > 0.72 ? { bottom: `${(1 - anchor.y0) * 100 + 1.2}%` } : { top: `${anchor.y1 * 100 + 1.2}%` }),
                }}
              >
                <p className="callout-title">#{callout.num} {callout.title}</p>
                <p><b>What&apos;s wrong:</b> {callout.issue}</p>
                <p><b>How to fix:</b> {callout.fix}</p>
              </div>
            )}
            <span className="viewer-page-no">{p + 1} / {doc.pages.length}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
