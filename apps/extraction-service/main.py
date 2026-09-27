from pathlib import Path
import json
import os
import json
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Security, status, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from pdf_parser import extract_text, is_text_sufficient
from ocr import extract_text_ocr
import llm_extract
import rules_engine
import pytesseract


app = FastAPI(title="ClaimClear Extraction Service")

origins = [
    "http://localhost:3000",
    "https://your-frontend-project.vercel.app", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows POST, GET, OPTIONS, etc.
    allow_headers=["*"],  # Allows all headers (including your X-Backend-Token)
)

# --- 2. API KEY SECURITY ---
API_KEY_NAME = "X-Backend-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    # Pulls the secret from your hidden ~/extraction.env file
    expected_key = os.environ.get("BACKEND_SECRET_TOKEN")
    
    # Failsafe if the environment variable is missing on the server
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Secret token not set."
        )
        
    if api_key_header == expected_key:
        return api_key_header
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

# Load rules config once at startup, not on every request
RULES_CONFIG_PATH = Path(__file__).resolve().parent / "rules_config.json"
with open(RULES_CONFIG_PATH, "r", encoding="utf-8") as f:
    RULES_CONFIG = json.load(f)


class DocumentExtractionResult(BaseModel):
    text: str
    method: str
    char_count: int


class ExtractTextResponse(BaseModel):
    clinical_doc: DocumentExtractionResult
    draft_claim: DocumentExtractionResult


def send_discord_debug_webhook(clinical_text: str, claim_text: str, extracted_data: dict):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("No DISCORD_WEBHOOK_URL found in .env. Skipping Discord notification.")
        return

    # Safely extract dictionaries
    ds = extracted_data.get("discharge_summary", {})
    cb = extracted_data.get("claim_part_b", {})
    
    ds_demo = ds.get("patient_demographics", {})
    cb_demo = cb.get("section_b_patient_details", {})
    cb_hosp = cb.get("section_a_hospital_details", {})
    cb_clin = cb.get("section_c_ailment_and_treatment", {})
    ds_clin = ds.get("clinical_assessment", {})

    # Build the Discord Embed
    embed = {
        "title": "🚨 OCR & LLM Extraction Debug Log",
        "color": 16711680, # Red color
        "fields": [
            {
                "name": "📄 RAW OCR STATS",
                "value": f"**Clinical Doc:** {len(clinical_text)} chars\n**Claim Form:** {len(claim_text)} chars",
                "inline": False
            },
            {
                "name": "1️⃣ Demographic Match Check",
                "value": f"**DS Name:** `{ds_demo.get('patient_name')}`\n**CB Name:** `{cb_demo.get('patient_name')}`",
                "inline": False
            },
            {
                "name": "2️⃣ Date Chronology Check",
                "value": f"**Admission:** `{cb_demo.get('date_of_admission')} {cb_demo.get('time_of_admission')}`\n**Discharge:** `{cb_demo.get('date_of_discharge')} {cb_demo.get('time_of_discharge')}`",
                "inline": False
            },
            {
                "name": "3️⃣ Hospital & Doctor ID Check",
                "value": f"**Hospital ROHINI ID:** `{cb_hosp.get('hospital_id_rohini')}`\n**Doctor Reg No:** `{cb_hosp.get('doctor_registration_no')}`",
                "inline": False
            }
        ]
    }

    # Prepare the payload
    data = {
        "content": "New extraction processed!",
        "embeds": [embed]
    }

    # Send to Discord
    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
        print("✅ Debug log sent to Discord successfully.")
    except Exception as e:
        print(f"❌ Failed to send Discord webhook: {e}")

def get_document_text(pdf_bytes: bytes) -> DocumentExtractionResult:
    """Try direct text extraction first; fall back to OCR if it looks empty/scanned."""
    text = extract_text(pdf_bytes)
    if is_text_sufficient(text):
        return DocumentExtractionResult(text=text, method="direct", char_count=len(text))

    ocr_text = extract_text_ocr(pdf_bytes)
    return DocumentExtractionResult(text=ocr_text, method="ocr", char_count=len(ocr_text))


def is_valid_clinical_doc(text: str) -> bool:
    """Heuristic check to ensure the document contains clinical keywords."""
    keywords = ["patient", "discharge", "diagnosis", "hospital", "admission"]
    return any(word in text.lower() for word in keywords)


def is_valid_claim_form(text: str) -> bool:
    """Heuristic check to ensure the document contains insurance claim keywords."""
    keywords = ["claim", "insurance", "policy", "billing", "charges"]
    return any(word in text.lower() for word in keywords)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/extract-text", response_model=ExtractTextResponse)
async def extract_text_endpoint(
    clinical_doc: UploadFile = File(...),
    draft_claim: UploadFile = File(...),
):

    """NOTE: this endpoint ONLY does PDF/OCR text extraction.
    It never calls Gemini and never runs the rules audit.
    Use /extract for the full pipeline."""
    clinical_bytes = await clinical_doc.read()
    claim_bytes = await draft_claim.read()

    return ExtractTextResponse(
        clinical_doc=get_document_text(clinical_bytes),
        draft_claim=get_document_text(claim_bytes),
    )


@app.post("/extract")
async def extract_endpoint(
    clinical_doc: UploadFile = File(...),
    draft_claim: UploadFile = File(...),
    api_key: str = Depends(get_api_key)
):
    """Full pipeline: PDF/OCR extraction -> Validation -> LLM structuring -> rules audit."""
    
    # 1. Read the uploaded files
    clinical_bytes = await clinical_doc.read()
    claim_bytes = await draft_claim.read()

    # 2. Extract text (These are the lines that were likely missing!)
    clinical_result = get_document_text(clinical_bytes)
    claim_result = get_document_text(claim_bytes)

    # 3. Document Validation Check
    reasons = []
    if not is_valid_clinical_doc(clinical_result.text):
        reasons.append("File 1 does not appear to be a valid clinical document.")
    if not is_valid_claim_form(claim_result.text):
        reasons.append("File 2 does not appear to be a valid insurance claim form.")

    if reasons:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Document validation failed.",
                "reasons": reasons
            }
        )

    # 4. LLM Extraction (Ollama)
    try:
        structured = llm_extract.run(clinical_result.text, claim_result.text)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM extraction failed: {e}",
        )

    # 5. Send Live Log to Discord
    send_discord_debug_webhook(clinical_result.text, claim_result.text, structured)

    # 6. Audit & Formatting
    discharge_summary = structured.get("discharge_summary", {})
    claim_part_b = structured.get("claim_part_b", {})

    try:
        audit_report = rules_engine.run_claim_audit(discharge_summary, claim_part_b, RULES_CONFIG)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rules audit failed: {e}")

    patient_details = {
        "name": claim_part_b.get("section_b_patient_details", {}).get("patient_name", "Unknown"),
        "member_id": claim_part_b.get("section_b_patient_details", {}).get("ip_registration_number", "Unknown"),
        "date_of_service": discharge_summary.get("hospitalization_timeline", {}).get("admission_date", "Unknown"),
        "principal_diagnosis": discharge_summary.get("clinical_assessment", {}).get("final_diagnosis", "Unknown"),
        "discharge_status": discharge_summary.get("discharge_status", {}).get("condition_at_discharge", "Unknown")
    }

    audit_report["patient_details"] = patient_details

    return {
        "extraction_debug": {
            "clinical_doc_method": clinical_result.method,
            "draft_claim_method": claim_result.method,
        },
        "audit": audit_report,
    }