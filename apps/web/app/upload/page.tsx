'use client'

import { ArrowRight, ClipboardList, FileHeart, FileText, Files, FlaskConical, IdCard, LockKeyhole, Package, Pill, Receipt, Scissors, ShieldCheck, UploadCloud, X, type LucideIcon } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { SiteFooter } from '@/components/site-footer'
import { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { startAudit } from '@/lib/audit-store'
import { Logo } from '@/components/logo'

const MAX_FILES = 10 // keep in sync with MAX_FILES in apps/extraction-service/main.py
const MAX_MB = 25 // keep in sync with MAX_FILE_BYTES in apps/extraction-service/main.py

const isPdf = (file: File) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')

type GuideItem = { icon: LucideIcon; label: string; hint: string }

// What the side panel asks for. Matches the document types detected by doc_classifier.py.
const REQUIRED: GuideItem[] = [
  { icon: FileHeart, label: 'Discharge summary', hint: 'From the hospital, at discharge' },
  { icon: ClipboardList, label: 'Claim form', hint: 'Part B, filled in by the hospital' },
]
const OPTIONAL: GuideItem[] = [
  { icon: Receipt, label: 'Final hospital bill', hint: 'The itemised bill' },
  { icon: Pill, label: 'Pharmacy bills', hint: 'If medicines were bought' },
  { icon: FlaskConical, label: 'Test reports', hint: 'Lab, X-ray, scans' },
  { icon: ShieldCheck, label: 'Pre-auth approval', hint: 'For cashless or planned stays' },
  { icon: Scissors, label: 'OT notes', hint: 'If there was a surgery' },
  { icon: Package, label: 'Implant invoice', hint: 'If a stent or implant was used' },
  { icon: IdCard, label: 'Policy card / ID', hint: 'TPA card and an ID proof' },
]

function GuideList({ items, columns = 1 }: { items: GuideItem[]; columns?: 1 | 2 }) {
  return <ul className={`guide-list ${columns === 2 ? 'guide-list-2col' : ''}`}>
    {items.map(({ icon: Icon, label, hint }) => <li key={label}>
      <span className="guide-icon"><Icon size={16} aria-hidden="true" /></span>
      <span><strong>{label}</strong><small>{hint}</small></span>
    </li>)}
  </ul>
}

export default function UploadPage() {
  const router = useRouter()
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)

  // Add PDFs to the list, skipping duplicates and explaining anything that was left out.
  const addFiles = (incoming: FileList | null | undefined) => {
    if (!incoming?.length) return
    const problems: string[] = []
    const next = [...files]
    for (const file of Array.from(incoming)) {
      if (!isPdf(file)) { problems.push(`${file.name} is not a PDF.`); continue }
      if (file.size > MAX_MB * 1024 * 1024) { problems.push(`${file.name} is larger than ${MAX_MB}MB.`); continue }
      if (next.some((f) => f.name === file.name && f.size === file.size)) continue
      if (next.length >= MAX_FILES) { problems.push(`You can upload up to ${MAX_FILES} files.`); break }
      next.push(file)
    }
    setFiles(next)
    setError(problems.join(' '))
  }

  const removeFile = (index: number) => {
    setFiles((current) => current.filter((_, i) => i !== index))
    setError('')
  }

  // One merged PDF with everything is enough; the service splits it into its documents.
  const ready = files.length >= 1
  const runAudit = () => {
    if (!ready) return
    // Fire the request; DON'T await it here. The processing page
    // subscribes to the same store and reacts when it finishes.
    startAudit(files)
    router.push('/processing')
  }

  const openPicker = () => inputRef.current?.click()

  return <main>
    <header className="site-header shell"><Logo /><div className="header-actions"><ThemeToggle /><span className="mono">Audit intake</span></div></header>
    <section className="page-main shell upload-page">
      <div className="page-intro">
        <p className="mono-label">STEP 01 / DOCUMENTS</p>
        <h1>Audit a claim</h1>
        <p>Upload every document you have for this claim. We work out which is which and tell you what&apos;s missing.</p>
      </div>
      <div className="upload-layout">
        <div className="upload-main">
          <div
            className={`dropzone dropzone-multi ${files.length ? 'has-file' : ''} ${error ? 'error' : ''} ${dragging ? 'is-dragging' : ''}`}
            onClick={openPicker}
            onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files) }}
            role="button" tabIndex={0}
            onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') openPicker() }}
          >
            <div className="dropzone-top"><div className="upload-icon"><UploadCloud size={22} aria-hidden="true" /></div><span className="mono">{files.length} / {MAX_FILES}</span></div>
            <div>
              <h2>{files.length ? 'Add more documents' : 'Drop your claim documents'}</h2>
              <p>Drop PDFs here or <span className="browse">browse files</span><br />
                <small>Select several at once, or one merged PDF with everything. PDF only, up to {MAX_MB}MB each.</small></p>
              {error && <p className="error-text" role="alert">{error}</p>}
            </div>
            <input ref={inputRef} type="file" multiple accept="application/pdf,.pdf" onChange={(event) => { addFiles(event.target.files); event.target.value = '' }} aria-label="Upload claim documents" />
          </div>
          {files.length > 0 && <ul className="file-list" aria-label="Selected files">
            {files.map((file, index) => <li className="file-row" key={`${file.name}-${file.size}`}>
              <span className="file-name mono"><FileText size={15} aria-hidden="true" />{file.name} <small>{(file.size / 1024 / 1024).toFixed(2)} MB</small></span>
              <button className="remove-file" onClick={() => removeFile(index)} aria-label={`Remove ${file.name}`}><X size={17} /></button>
            </li>)}
          </ul>}
          <div className="actions">
            {!ready && <span className="actions-hint">Add the discharge summary and the claim form, or one merged PDF</span>}
            <button className="button" disabled={!ready} onClick={runAudit}>Run Audit <ArrowRight size={17} aria-hidden="true" /></button>
          </div>
          <div className="upload-note"><LockKeyhole size={16} aria-hidden="true" /><span>Encrypted in transit. PDFs are used only to create this report and are not stored.</span></div>
        </div>
        <aside className="upload-guide" aria-label="What to upload">
          <p className="mono-label">WHAT TO UPLOAD</p>
          <p className="guide-group">Required</p>
          <GuideList items={REQUIRED} />
          <p className="guide-merged"><Files size={14} aria-hidden="true" /> One merged PDF with everything? Upload just that, we split it.</p>
          <p className="guide-group">Add if you have them</p>
          <GuideList items={OPTIONAL} columns={2} />
        </aside>
      </div>
    </section>
    <SiteFooter />
  </main>
}
