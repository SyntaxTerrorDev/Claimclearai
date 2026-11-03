'use client'

import { ArrowRight, FileText, LockKeyhole, UploadCloud, X } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { SiteFooter } from '@/components/site-footer'
import { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { startAudit } from '@/lib/audit-store'
import { Logo } from '@/components/logo'

const MAX_FILES = 10 // keep in sync with MAX_FILES in apps/extraction-service/main.py
const MAX_MB = 10

const isPdf = (file: File) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')

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

  const ready = files.length >= 2
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
    <section className="page-main shell">
      <div className="page-intro">
        <p className="mono-label">STEP 01 / DOCUMENTS</p>
        <h1>Audit a claim</h1>
        <p>Upload every document you have for this claim. We work out which is which and tell you what&apos;s missing.</p>
      </div>
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
          <h2>Claim documents</h2>
          <p>Drop PDFs here or <span className="browse">browse files</span><br />
            <small>Needed: discharge summary and claim form. Also add the hospital bill, pharmacy bills, test reports and pre-auth letter if you have them. PDF only, up to {MAX_MB}MB each.</small></p>
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
      <div className="upload-note"><LockKeyhole size={16} aria-hidden="true" /><span>Encrypted in transit · PDFs are used only to create this report · only the claim form and discharge summary are read by the AI</span></div>
      <div className="actions">
        {!ready && files.length > 0 && <span className="actions-hint">Add at least the discharge summary and the claim form</span>}
        <button className="button" disabled={!ready} onClick={runAudit}>Run Audit <ArrowRight size={17} aria-hidden="true" /></button>
      </div>
    </section>
    <SiteFooter />
  </main>
}
