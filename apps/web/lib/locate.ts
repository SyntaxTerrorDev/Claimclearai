// Finds extracted values inside the source PDFs so the UI can highlight them.
// Pages come from the extraction service as word boxes in page fractions (0–1).
// Extracted values are normalized (ISO dates, plain numbers), while documents print
// them many ways, so each value is expanded into the spellings a document might use.

export type Word = { t: string; x0: number; y0: number; x1: number; y1: number; c: number }
export type Page = { image: string; width: number; height: number; words: Word[] }
export type DocKey = 'clinical' | 'claim'
export type Box = { page: number; x0: number; y0: number; x1: number; y1: number }
export type Match = { boxes: Box[]; confidence: number }

const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
const HONORIFIC = /^(mr|mrs|ms|miss|dr|master|shri|smt|kum|baby)$/

export const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')

function groupIndian(int: string): string {
  if (int.length <= 3) return int
  const last3 = int.slice(-3)
  return int.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + last3
}

export function variants(value: unknown): string[] {
  if (value === null || value === undefined) return []
  const raw = String(value).trim()
  if (!raw) return []
  const out = new Set<string>([raw])

  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (iso) {
    const [, y, m, d] = iso
    const dn = String(+d), mn = String(+m), mon = MONTHS[+m - 1] ?? ''
    for (const sep of ['/', '-', '.']) {
      out.add(`${d}${sep}${m}${sep}${y}`).add(`${dn}${sep}${mn}${sep}${y}`).add(`${d}${sep}${m}${sep}${y.slice(2)}`)
    }
    if (mon) {
      out.add(`${d} ${mon} ${y}`).add(`${dn} ${mon} ${y}`).add(`${d} ${mon.slice(0, 3)} ${y}`).add(`${dn} ${mon.slice(0, 3)} ${y}`)
      out.add(`${mon.slice(0, 3)} ${dn}, ${y}`).add(`${d}-${mon.slice(0, 3)}-${y}`)
    }
  }

  const num = raw.replace(/,/g, '').match(/^(\d+)(?:\.(\d+))?$/)
  if (num && !iso) {
    const int = num[1]
    const frac = num[2] && +num[2] !== 0 ? num[2] : ''
    const western = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
    for (const g of new Set([int, western, groupIndian(int)])) {
      out.add(frac ? `${g}.${frac}` : g)
      if (!frac) out.add(`${g}.00`)
    }
  }

  // "Mr. Ramesh Kumar" may be printed without the title
  const words = raw.split(/\s+/)
  if (words.length > 1 && HONORIFIC.test(norm(words[0]))) out.add(words.slice(1).join(' '))
  return [...out]
}

function tokens(s: string): string[] {
  return s.split(/\s+/).map(norm).filter(Boolean)
}

function wordMatches(word: string, token: string, isLast: boolean): boolean {
  if (word === token) return true
  // "10:30am" for "10:30", "kumar's" for "kumar": allow a suffix on the last token only
  return isLast && token.length >= 4 && word.startsWith(token)
}

function mergeLine(boxes: Box[]): Box[] {
  const out: Box[] = []
  for (const b of boxes) {
    const prev = out[out.length - 1]
    if (prev && prev.page === b.page && Math.abs(prev.y0 - b.y0) < 0.01) {
      prev.x0 = Math.min(prev.x0, b.x0); prev.x1 = Math.max(prev.x1, b.x1)
      prev.y0 = Math.min(prev.y0, b.y0); prev.y1 = Math.max(prev.y1, b.y1)
    } else out.push({ ...b })
  }
  return out
}

/** Every occurrence of `value` (any spelling) in the pages.
 *  Labels ("ROHINI|Hospital ID") point at where a *missing* field belongs: each name is tried in
 *  order, words match by prefix, and only the first hit is marked. */
export function locate(pages: Page[] | undefined, value: unknown, kind: 'value' | 'label' = 'value', limit = 4): Match | null {
  if (!pages?.length) return null
  if (kind === 'label') {
    for (const name of String(value ?? '').split('|')) {
      const seq = tokens(name)
      const hit = seq.length ? search(pages, [seq], 'label', 1) : null
      if (hit) return hit
    }
    return null
  }
  const seqs = variants(value).map(tokens).filter((t) => t.length && t.join('').length >= 2)
  if (!seqs.length) return null
  return search(pages, seqs, 'value', limit)
}

function search(pages: Page[], seqs: string[][], kind: 'value' | 'label', limit: number): Match | null {

  const boxes: Box[] = []
  const confs: number[] = []
  pages.forEach((page, p) => {
    const ws = page.words.map((w) => ({ w, n: norm(w.t) })).filter((x) => x.n)
    for (let i = 0; i < ws.length && boxes.length < limit * 3; i++) {
      for (const seq of seqs) {
        if (i + seq.length > ws.length) continue
        const ok = kind === 'label'
          ? seq.every((t, k) => ws[i + k].n.startsWith(t))
          : seq.every((t, k) => wordMatches(ws[i + k].n, t, k === seq.length - 1))
        if (ok) {
          const hit = ws.slice(i, i + seq.length)
          boxes.push(...mergeLine(hit.map(({ w }) => ({ page: p, x0: w.x0, y0: w.y0, x1: w.x1, y1: w.y1 }))))
          confs.push(...hit.map(({ w }) => w.c))
          i += seq.length - 1
          break
        }
      }
    }
  })
  if (!boxes.length) return null
  return { boxes: boxes.slice(0, limit * 2), confidence: Math.min(...confs) }
}
