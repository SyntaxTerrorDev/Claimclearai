'use client'

import Link from 'next/link'
import { ArrowRight, FileHeart, FileText, LockKeyhole, UploadCloud, X } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { SiteFooter } from '@/components/site-footer'
import { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { startAudit } from '@/lib/audit-store'
import { Logo } from '@/components/logo'


type UploadKind = 'clinical' | 'claim'
type SelectedFile = { file: File; name: string; size: number }

function UploadBox({ kind, label, file, error, onFile, onRemove }: { kind: UploadKind; label: string; file: SelectedFile | null; error: string; onFile: (file: File) => void; onRemove: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const handleFile = (next: File | undefined) => { if (next) onFile(next) }
  return <div className={`dropzone ${file ? 'has-file' : ''} ${error ? 'error' : ''} ${dragging ? 'is-dragging' : ''}`} onClick={() => !file && inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); handleFile(event.dataTransfer.files[0]) }} role="button" tabIndex={0} onKeyDown={(event) => { if ((event.key === 'Enter' || event.key === ' ') && !file) inputRef.current?.click() }}>
    <div className="dropzone-top"><div className="upload-icon"><UploadCloud size={22} aria-hidden="true" /></div><span className="mono">{kind === 'clinical' ? '01' : '02'}</span></div>
    <div><h2>{label}</h2>{file ? <p className="file-row"><span className="file-name mono"><FileText size={15} aria-hidden="true" />{file.name} <small>{(file.size / 1024 / 1024).toFixed(2)} MB</small></span><button className="remove-file" onClick={(event) => { event.stopPropagation(); onRemove() }} aria-label={`Remove ${label}`}><X size={17} /></button></p> : <p>Drop a PDF here or <span className="browse">browse files</span><br /><small>PDF only, up to 10MB</small></p>}{error && <p className="error-text" role="alert">{error}</p>}</div>
    <input ref={inputRef} type="file" accept="application/pdf,.pdf" onChange={(event) => handleFile(event.target.files?.[0])} aria-label={`Upload ${label}`} />
  </div>
}

export default function UploadPage() {
  const router = useRouter()
  const [files, setFiles] = useState<Record<UploadKind, SelectedFile | null>>({ clinical: null, claim: null })
  const [errors, setErrors] = useState<Record<UploadKind, string>>({ clinical: '', claim: '' })
  const [submitError, setSubmitError] = useState('')

  const selectFile = (kind: UploadKind, file: File) => {
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) { setErrors((current) => ({ ...current, [kind]: `That doesn't look like a PDF. Upload the ${kind === 'clinical' ? 'clinical record' : 'draft claim'} as a PDF.` })); return }
    if (file.size > 10 * 1024 * 1024) { setErrors((current) => ({ ...current, [kind]: 'That file is larger than 10MB. Choose a smaller PDF.' })); return }
    setErrors((current) => ({ ...current, [kind]: '' }))
    setFiles((current) => ({ ...current, [kind]: { file, name: file.name, size: file.size } }))
  }

  const ready = Boolean(files.clinical && files.claim)
  const runAudit = () => {
    if (!files.clinical || !files.claim) return
    setSubmitError('')
    // Fire the request; DON'T await it here. The processing page
    // subscribes to the same store and reacts when it finishes.
    startAudit(files.clinical.file, files.claim.file)
    router.push('/processing')
  }

  return <main><header className="site-header shell"><Logo /><div className="header-actions"><ThemeToggle /><span className="mono">Audit intake</span></div></header><section className="page-main shell"><div className="page-intro"><p className="mono-label">STEP 01 / DOCUMENTS</p><h1>Audit a claim</h1><p>Upload both documents to run your guided check.</p></div><div className="upload-grid"><UploadBox kind="clinical" label="Clinical record" file={files.clinical} error={errors.clinical} onFile={(file) => selectFile('clinical', file)} onRemove={() => setFiles((current) => ({ ...current, clinical: null }))} /><UploadBox kind="claim" label="Draft claim" file={files.claim} error={errors.claim} onFile={(file) => selectFile('claim', file)} onRemove={() => setFiles((current) => ({ ...current, claim: null }))} /></div><div className="upload-note"><LockKeyhole size={16} aria-hidden="true" /><span>Encrypted in transit · PDFs are used only to create this report</span></div>{submitError && <p className="error-text" role="alert">{submitError}</p>}<div className="actions"><button className="button" disabled={!ready} onClick={runAudit}>Run Audit <ArrowRight size={17} aria-hidden="true" /></button></div></section><SiteFooter /></main>
}
