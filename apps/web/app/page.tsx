'use client'

import Link from 'next/link'
import { ArrowRight, ArrowUpRight, Check, FileCheck2, FileText, Hospital, Quote, ShieldCheck, Sparkles, UserRound } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { SiteFooter } from '@/components/site-footer'
import { Logo } from '@/components/logo'

const clearSteps = [
  { icon: FileText, title: 'Add your documents', description: 'Everything from the hospital, or one merged PDF.' },
  { icon: Sparkles, title: 'Run the audit', description: 'We check 21 common reasons claims get rejected.' },
  { icon: FileCheck2, title: 'Submit with confidence', description: 'Fix what we found, in the order that matters.' },
]

const audiences = [
  {
    icon: UserRound,
    label: 'FOR PATIENTS & FAMILIES',
    title: 'Claiming the money back yourself?',
    text: 'You paid the hospital and now you are sending the claim to your insurance company, or your cashless request was not approved. Check your papers before you send them.',
    points: ['A to-do list in simple words: what to ask the hospital for', 'Finds missing papers: bills, reports, implant stickers', 'Works with the one big PDF the hospital gave you'],
    cta: 'Check my claim',
  },
  {
    icon: Hospital,
    label: 'FOR HOSPITALS & CLINICS',
    title: 'Clean claims from the billing desk.',
    text: 'For billing and TPA desks: catch the errors an insurer would query before the claim leaves the hospital.',
    points: ['Every issue marked on the scanned page', 'ICD-10 code checks with suggested codes', 'Readiness score and a PDF audit report'],
    cta: 'Audit a claim',
  },
]

// "Why not just paste it into an AI chatbot?" (general-purpose chatbots vs ClaimClear)
const comparison = [
  { topic: 'Same claim, same answer', chatbot: 'Answers can change each time you ask.', us: '21 fixed checks built on insurance rules. AI only reads the documents; the rules decide.' },
  { topic: 'Shows the proof', chatbot: 'Gives you a paragraph of text.', us: 'Marks the exact spot on your scanned page.' },
  { topic: 'Diagnosis codes', chatbot: 'Can make up a code that looks right.', us: 'Checks every code against the ICD-10 code list.' },
  { topic: 'Your privacy', chatbot: 'You paste the whole document, name and ID numbers included.', us: 'Names and ID numbers are hidden before the AI sees anything. Bills never leave the server.' },
  { topic: 'Knowing what to check', chatbot: 'You have to know what to ask.', us: 'Already knows the common rejection reasons and which papers insurers need.' },
  { topic: 'Messy files', chatbot: 'You copy the text out yourself.', us: 'Reads scans, and splits one merged PDF into its documents.' },
]

export default function Page() {
  return <main>
    <header className="site-header shell">
      <Logo />
      <div className="header-actions">
        <ThemeToggle />
        <Link className="button button-small" href="/upload">Start an audit <ArrowRight size={15} aria-hidden="true" /></Link>
      </div>
    </header>
    

    <section className="landing-hero shell">
      <div className="hero-content">
        <p className="mono-label">CLAIMS, MADE CLEAR</p>
        <h1>Know what to fix before you <span className="accent-italic">submit</span>.</h1>
        <p className="hero-copy">ClaimClear checks your claim papers before they reach the insurance company, so avoidable mistakes don&apos;t turn into rejections or delays. For patients filing their own claim, and for hospital billing desks.</p>
        <div className="hero-actions">
          <Link className="button" href="/upload">Check my claim <ArrowRight size={17} aria-hidden="true" /></Link>
          <span className="action-note">Free to try · No account needed</span>
        </div>
      </div>

      <aside className="hero-card" aria-label="Annual claim rejection statistics">
        <div className="hero-card-top">
          <span className="mono">CLAIM SNAPSHOT</span>
          <span className="status-dot">INDIA 2025</span>
        </div>

        <div className="bento-grid">
          <div className="bento-cell bento-headline">
            <strong>1 in 5</strong>
            <p>health insurance claims are rejected on first submission</p>
          </div>
          <div className="bento-cell bento-amber">
            <div><strong>₹ 30K CRORE</strong><span>denied annually</span></div>
          </div>
          <div className="bento-cell bento-stat">
            <strong>20%</strong>
            <span>Rejected initially</span>
          </div>
          <div className="bento-cell bento-stat">
            <strong>14 days</strong>
            <span>Average delay</span>
          </div>
          <div className="bento-cell bento-list">
            <div><ShieldCheck size={16} aria-hidden="true" />Catch avoidable errors before submission</div>
            <div><ShieldCheck size={16} aria-hidden="true" />Get clear, prioritized next steps</div>
          </div>
          <div className="bento-cell bento-dark">
                        <ShieldCheck size={22} aria-hidden="true" />

                        <div><strong>80%</strong><span>can be prevented</span></div>

          </div>
        </div>

        <p className="hero-card-foot">ClaimClear helps you turn claim risk into a clear action plan.</p>
      </aside>
    </section>

    <section className="audiences shell" aria-labelledby="audiences-title">
      <div className="section-heading">
        <p className="mono-label">WHO IT&apos;S FOR</p>
        <h2 id="audiences-title">One check, whichever side of the desk you&apos;re on.</h2>
      </div>
      <div className="audience-grid">
        {audiences.map(({ icon: Icon, label, title, text, points, cta }) => (
          <article className="audience-card" key={label}>
            <span className="flow-icon"><Icon size={22} aria-hidden="true" /></span>
            <p className="audience-label mono">{label}</p>
            <h3>{title}</h3>
            <p>{text}</p>
            <ul>{points.map((point) => <li key={point}><Check size={15} aria-hidden="true" />{point}</li>)}</ul>
            <Link className="button button-small" href="/upload">{cta} <ArrowRight size={15} aria-hidden="true" /></Link>
          </article>
        ))}
      </div>
    </section>

    <section className="how-it-works shell">
      <div className="section-heading">
        <p className="mono-label">THREE SIMPLE STEPS</p>
        <h2>A straight line to a cleaner claim.</h2>
      </div>
      <div className="flow-steps">
        {clearSteps.map(({ icon: Icon, title, description }, index) => (
          <div className="flow-step-wrap" key={title}>
            <article className="flow-step">
              <span className="flow-icon"><Icon size={22} aria-hidden="true" /></span>
              <span className="flow-number mono">0{index + 1}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          </div>
        ))}
      </div>
    </section>

    <section className="why-us shell" aria-labelledby="why-title">
      <div className="section-heading">
        <p className="mono-label">WHY NOT JUST ASK AN AI CHATBOT?</p>
        <h2 id="why-title">A chatbot gives you an opinion. ClaimClear gives you a checklist.</h2>
      </div>
      <div className="compare" role="table" aria-label="AI chatbot compared with ClaimClear">
        <div className="compare-row compare-head" role="row">
          <span role="columnheader" />
          <span role="columnheader">General AI chatbot</span>
          <span role="columnheader">ClaimClear</span>
        </div>
        {comparison.map(({ topic, chatbot, us }) => (
          <div className="compare-row" role="row" key={topic}>
            <strong role="rowheader">{topic}</strong>
            <span role="cell" className="compare-them"><small>General AI chatbot</small>{chatbot}</span>
            <span role="cell" className="compare-us"><small>ClaimClear</small><Check size={15} aria-hidden="true" />{us}</span>
          </div>
        ))}
      </div>
    </section>

    <figure className="reassurance shell">
      <Quote size={28} aria-hidden="true" />
      <blockquote>Clear answers, not more paperwork. Know what needs attention before an insurer does.</blockquote>
      <figcaption className="mono">BUILT FOR THE MOMENT BEFORE SUBMISSION</figcaption>
    </figure>

    <section className="final-cta shell">
      <p className="mono-label">READY WHEN YOU ARE</p>
      <h2>Make the clean claim the <span className="accent-italic">first</span> claim.</h2>
      <Link className="button button-invert" href="/upload">Audit a claim <ArrowRight size={17} aria-hidden="true" /></Link>
    </section>

    <SiteFooter />
  </main>
}
