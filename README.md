# ClaimClear

**AI-powered pre-submission insurance claim auditor for small clinics, diagnostic labs, and nursing homes.**

Built at byteBuilt 1.0 (byteXL × Chandigarh University) by Team Syntax Terror.

**v2.0.0** · [Releases](../../releases) · [Report Bug](../../issues) · [Request Feature](../../issues)

---

## The Problem

Small clinics and nursing homes lose time and money to avoidable claim rejections: missing pre-authorizations, mismatched codes, incomplete fields. These problems only surface *after* submission, triggering manual investigation, correction, resubmission and delayed payment.

## What ClaimClear Does

Upload a clinical document and a draft insurance claim. ClaimClear reads both (digital or scanned), extracts the structured claim data with AI, and runs it through a deterministic rules engine built on IRDAI guidelines, insurer/TPA documentation and healthcare coding standards. It returns:

- A **Readiness Score** (0–100) and status
- A ranked list of **findings**, each **highlighted in the original PDF**
- **Suggested fixes**, including **suggested ICD-10 codes**
- A downloadable **PDF audit report**

All before the claim ever reaches the insurer.

```
Clinical Docs + Draft Claim → Text / OCR → PHI shield → AI extraction → 20-rule engine → Score + evidence + fixes
```

## Features

### New in v2.0
- 🔍 **Evidence highlighting**: every finding points to the exact words in the source PDF, drawn on the page in a side-by-side viewer (works for scanned documents too, using OCR word positions)
- 📍 **Issues marked on the document**: every issue gets a numbered marker on the PDF, and the selected one shows *what's wrong* and *how to fix it* right next to the highlight
- ⏱️ **Real progress**: the processing screen streams each real step (reading, OCR, masking, AI, checks) with timings, including when Gemini is busy and Groq takes over
- 🗣️ **Plain-English fixes** for every rule
- 🔒 **PHI privacy shield**: patient names, phone numbers, emails, Aadhaar, PAN, policy, UHID, IP and account numbers are replaced with placeholders **before** any text is sent to Gemini/Groq, then restored locally. The same value maps to the same placeholder, so cross-document checks still work.
- 🧬 **ICD-10 intelligence**: format validation, chapter lookup, sex- and age-specific code conflicts, and code suggestions from the diagnosis text (offline)
- ✅ **All 20 rules implemented** (v1 had 9)
- 🧪 **Synthetic sample documents** with planted errors, including a scanned copy for the OCR path
- 🏷️ **Versioned releases** on GitHub

### Core
- 📄 Upload clinical + claim PDFs (typed or scanned)
- 🤖 AI structured extraction with Gemini: if one Gemini model is busy it moves to the next (all free, all schema-exact), with Groq only as the last resort
- 📊 Readiness Score with severity-weighted findings
- 📥 Exportable PDF audit report

## Rules

| ID | Check | Severity |
|---|---|---|
| RULE_01 | Surgical procedure without pre-authorization ID | Critical |
| RULE_02 | Admission/discharge chronology and cross-document date conflicts | Critical |
| RULE_03 | ICD-10 code differs between discharge summary and claim | Critical |
| RULE_04 | Inpatient stay under 24 h not marked Day Care | Critical |
| RULE_05 | Patient name mismatch across documents | Major |
| RULE_06 | ICD-10 code or procedure restricted to the other sex | Critical |
| RULE_07 | Doctor's medical council registration missing | Major |
| RULE_08 | Hospital ROHINI ID missing | Major |
| RULE_09 | Surgical procedure under a non-surgical consultant, no surgeon named | Major |
| RULE_10 | Duplicate bill line items | Major |
| RULE_11 | Multi-day room rent billed as a lump sum | Minor |
| RULE_12 | Implant used but invoice/stickers not attached | Major |
| RULE_13 | Bill items dated outside the stay | Major |
| RULE_14 | Close to / past the 15-day filing window | Minor |
| RULE_15 | Required supporting documents not attached | Major |
| RULE_16 | Line items don't add up to the claimed total | Major |
| RULE_17 | Diagnostic-only admission (mostly investigations, no treatment) | Major |
| RULE_18 | Bank account / IFSC missing for NEFT settlement | Minor |
| RULE_19 | Invalid or age-implausible ICD-10 code | Critical |
| RULE_20 | ICD-10 code doesn't match the written diagnosis (with suggestions) | Major |

Rule metadata (title, deduction, regulatory source, fix) lives in [`rules_config.json`](apps/extraction-service/rules_config.json); the logic is in [`rules_engine.py`](apps/extraction-service/rules_engine.py).

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | Node.js (Next.js API routes) |
| Extraction Service | Python, FastAPI, PyMuPDF, Tesseract OCR |
| AI | Gemini API (several models, auto-switch when busy), Groq (last resort) |
| Running | Locally: `npm run dev` (web) + Docker or uvicorn (extraction service) |

## Architecture

```
      Client (Browser)
            |
          HTTPS
            v
+--------------------------------+
|  Next.js app (localhost:3000)  |
|  /upload  /processing /results |
|                                |
|  POST /api/extract  ───────┐   |   adds X-Backend-Token
|   (streams progress)       |   |   (server-side secret)
|  POST /api/report  (PDF)   |   |
+----------------------------|---+
                             v
+--------------------------------------------+
|  Extraction Service (FastAPI, Docker)      |
|                                            |
|  POST /extract-stream  (NDJSON progress)   |
|    1. PyMuPDF text layer + word boxes      |
|       (Tesseract OCR if scanned)           |
|    2. PHI shield: mask identifiers         |
|    3. Gemini models in turn → Groq → JSON  |
|    4. Restore identifiers                  |
|    5. 20-rule audit with evidence          |
|    → audit, extracted data, page previews  |
|                                            |
|  POST /extract   same, one JSON response   |
|  GET  /health  status + version            |
+--------------------------------------------+
```

Nothing is stored: PDFs are processed in memory and the browser keeps the result for the session.

## Getting Started

### Prerequisites
- Node.js ≥ 18
- Python ≥ 3.10
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) for scanned PDFs
  (Windows: `winget install UB-Mannheim.TesseractOCR`; Debian/Ubuntu: `apt install tesseract-ocr`).
  ClaimClear finds it on `PATH`, in the default Windows install folder, or via `TESSERACT_CMD`.
- Gemini API key (Groq key optional, used as fallback)

### 1. Install
```bash
# Frontend
cd apps/web
npm install

# Extraction service
cd ../extraction-service
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp apps/web/.env.example apps/web/.env.local
cp apps/extraction-service/.env.example apps/extraction-service/.env
```
Set `GEMINI_API_KEY` (and optionally `GROQ_API_KEY`) in the service `.env`, and put the **same** random `BACKEND_SECRET_TOKEN` in both files. The web app sends it as `X-Backend-Token`; the service rejects requests without it.

### 3. Run locally
On Windows, double-click **`start.bat`** in the repo root. It checks your setup, starts both servers in their own windows and opens the app.

Or start them by hand:
```bash
# Terminal 1 — extraction service
cd apps/extraction-service
uvicorn main:app --reload --port 8000

# Terminal 2 — web app
cd apps/web
npm run dev
```
Open `http://localhost:3000/upload` and upload the PDFs from `samples/`.

### Sample documents
`samples/make_samples.py` generates a fictional discharge summary and a claim form with six planted errors, plus a scanned (image-only) copy of the claim, into `samples/`. `start.bat` regenerates them on every start; dates are relative to today. To regenerate by hand:
```bash
python samples/make_samples.py
```

### Tests
```bash
cd apps/extraction-service
pip install -r requirements-dev.txt
python -m pytest -q
```
The suite covers every rule, the PHI shield, ICD-10 helpers and the API (with the LLM stubbed, so no keys or network are needed).

## Versioning & releases

ClaimClear follows [Semantic Versioning](https://semver.org). The version lives in `apps/web/package.json` and `VERSION` in `apps/extraction-service/main.py` (reported by `/health`). To publish a release:

1. Bump both version numbers and commit.
2. Tag and push:
   ```bash
   git tag -a vX.Y.Z -m "ClaimClear vX.Y.Z"
   git push origin vX.Y.Z
   ```
3. The **Release** workflow (`.github/workflows/release.yml`) creates the GitHub Release with notes generated from the commits since the last tag.

## Project Structure

```
claimclear/
├── apps/
│   ├── web/                        # Next.js frontend
│   │   ├── app/                    # upload, processing, results pages + API routes
│   │   ├── components/             # document-viewer, fields-panel, ...
│   │   └── lib/                    # audit-store, locate (evidence finder), report template
│   │
│   └── extraction-service/         # Python/FastAPI extraction backend
│       ├── main.py                 # FastAPI entrypoint: /extract-stream, /extract, /health
│       ├── pdf_parser.py           # PyMuPDF text, word boxes, page previews
│       ├── ocr.py                  # Tesseract OCR (text + word boxes) for scans
│       ├── phi_shield.py           # mask / restore patient identifiers around the LLM
│       ├── llm_extract.py          # Gemini/Groq calls → structured JSON
│       ├── icd10.py                # ICD-10 validation, conflicts, suggestions
│       ├── rules_engine.py         # 20 rules with evidence
│       ├── rules_config.json       # rule metadata
│       ├── tests/                  # pytest suite
│       ├── dockerfile
│       └── .env.example
│
├── samples/                        # synthetic demo PDFs + make_samples.py (generator)
├── .github/workflows/              # deploy.yml, release.yml
├── start.bat                       # Windows: start everything for local testing
└── README.md
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
