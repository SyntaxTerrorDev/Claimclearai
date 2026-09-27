# ClaimClear

**AI-powered pre-submission insurance claim auditor for small clinics, diagnostic labs, and nursing homes.**

Built at byteBuilt 1.0 (byteXL × Chandigarh University) by Team Syntax Terror.

 · [Report Bug](../../issues) · [Request Feature](../../issues)

---

## The Problem

Small clinics and nursing homes lose time and money to avoidable claim rejections  missing pre-authorizations, mismatched codes, incomplete fields that only surface *after* submission, triggering manual investigation, correction, resubmission, and delayed payment.

## What ClaimClear Does

Upload a clinical document and a draft insurance claim. ClaimClear extracts the structured claim data, runs it through a deterministic rules engine built on IRDAI guidelines, insurer/TPA documentation, and healthcare coding standards, and returns:

- A **Readiness Score** (0–100)
- A ranked list of **findings** — what's wrong and how severe
- **Suggested fixes** for each finding
- A downloadable **PDF audit report**

All before the claim ever reaches the insurer.

```
Clinical Docs + Draft Claim  →  AI Extraction  →  Rules Engine  →  Readiness Score + Fixes
```

## Features

- 📄 Upload clinical + claim PDFs (typed or scanned)
- 🤖 AI-powered structured data extraction (Gemini API)
- ✅ 15-point deterministic rules engine (coding mismatches, missing fields, date/amount anomalies, and more)
- 📊 Readiness Score with severity-weighted findings
- 🛠️ Actionable, per-finding suggested fixes
- 📥 Exportable PDF audit report

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS,|
| Backend | Node.js (Next.js API routes) |
| Extraction Service | Python, FastAPI, PyMuPDF, OCR |
| AI | Gemini API |
| Database & Auth | Supabase (PostgreSQL) |
| Storage | Supabase Storage |
| Deployment | Vercel (web), Render/Railway (extraction service) |


## Architecture

```
      Client (Browser)
            |
          HTTPS
            |
            v
+-----------------------------+
|   Next.js App — Vercel      |
|                             |
|  Frontend (React)           |
|   /upload                   |
|   /results/[id]             |
|                             |
|  API Routes (Node.js)       |
|   POST /api/claims/upload   |
|   GET  /api/claims/[id]     |
|   POST /api/claims/[id]/    |
|        extract              |
|   POST /api/claims/[id]/    |
|        audit                |
|   GET  /api/claims/[id]/    |
|        report               |
+--------------+--------------+
               |
          HTTP (PDF passed
          through, nothing
          stored)
               |
               v
+------------------------------+
|   Extraction Service         |
|   (Python/FastAPI, Render)   |
|                              |
|  1. Receive PDF              |
|  2. PyMuPDF text extraction  |
|  3. OCR fallback (scanned)   |
|  4. Gemini/Groq -> JSON      |
|  5. Return structured result |
+------------------------------+
```


## Getting Started

### Prerequisites
- Node.js ≥ 18
- Python ≥ 3.10
- A Supabase project
- Gemini API key, Groq API key

### 1. Clone and install
```bash
git clone https://github.com/<org>/claimclear.git
cd claimclear

# Frontend
cd apps/web
npm install

# Extraction service
cd ../extraction-service
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example    # in apps/web
cp .env.example     # in apps/extraction-service
```
Fill in:
```
GEMINI_API_KEY=
GROQ_API_KEY=
DISCORD_WEBHOOK_URL=
```


### 3. Run locally
```bash
# Terminal 1 — extraction service
cd apps/extraction-service
uvicorn main:app --reload --port 8000

# Terminal 2 — web app
cd apps/web
npm run dev
```
Visit `http://localhost:3000`.

## Project Structure

```
claimclear/
├── apps/
│   ├── web/                      # Next.js frontend
│   │   ├── ...                   # pages/components/app router, etc.
│   │   └── package.json
│   │
│   └── extraction-service/       # Python/FastAPI extraction backend
│       ├── main.py               # FastAPI entrypoint
│       ├── pdf_parser.py         # PyMuPDF text extraction
│       ├── ocr.py                # OCR fallback for scanned PDFs
│       ├── llm_extract.py        # Gemini/Groq calls → structured JSON
│       ├── rules_engine.py       # Domain rules applied to extracted data
│       ├── rules_config.json     # Rule definitions
│       ├── requirements.txt
│       ├── Dockerfile
│       ├── .env.example
│       └── .env                  # local only — gitignored, never committed
│
├── docs/
│   ├── ARCHITECTURE.md           # data flow, schema, API contracts
│   └── schema.sql                # Supabase/Postgres schema
│
├── .github/
│   └── pull_request_template.md
│
├── .gitignore
├── package.json
├── package-lock.json
├── README.md
└── LICENSE

```

## Team — Syntax Terror

| Name | Role |
|---|---|
| Atharv Rawal | AI/Data Pipeline, Domain Logic |
| Swastik | Frontend, Backend, AI Integration |
| Stalin | Product Development, Presentation |

## License

MIT — see [`LICENSE`](LICENSE).

## Disclaimer

Prototype rules are derived from publicly available IRDAI/ABDM/WHO documentation and are not presented as insurer-specific rejection guarantees. Built and tested on synthetic claim data only.
