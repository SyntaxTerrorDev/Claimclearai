import { NextRequest, NextResponse } from 'next/server'
import { EXTRACTION_SERVICE_URL, backendHeaders } from '@/lib/server/backend'

export const runtime = 'nodejs'

// Streams the extraction service's progress events (NDJSON, one JSON object per line)
// straight through to the browser, so the processing screen shows real progress.
export async function POST(request: NextRequest) {
  try {
    const incomingForm = await request.formData()

    const clinicalDoc = incomingForm.get('clinical_doc')
    const draftClaim = incomingForm.get('draft_claim')

    if (!clinicalDoc || !draftClaim) {
      return NextResponse.json(
        { detail: 'Both clinical_doc and draft_claim files are required.' },
        { status: 400 },
      )
    }

    // Re-build the multipart form to forward to FastAPI.
    const forwardForm = new FormData()
    forwardForm.append('clinical_doc', clinicalDoc)
    forwardForm.append('draft_claim', draftClaim)

    const backendRes = await fetch(`${EXTRACTION_SERVICE_URL}/extract-stream`, {
      method: 'POST',
      body: forwardForm,
      headers: backendHeaders(),
    })

    // Auth or upload errors come back as plain JSON before any streaming starts.
    if (!backendRes.ok || !backendRes.body) {
      const data = await backendRes.json().catch(() => ({ detail: `Extraction service error (${backendRes.status})` }))
      return NextResponse.json(data, { status: backendRes.status })
    }

    return new Response(backendRes.body, {
      headers: { 'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-cache, no-transform' },
    })
  } catch (err) {
    console.error('Proxy to extraction service failed:', err)
    return NextResponse.json(
      { detail: 'Could not reach the extraction service. Is it running?' },
      { status: 502 },
    )
  }
}
