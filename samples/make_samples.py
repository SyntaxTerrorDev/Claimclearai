"""Generate synthetic demo documents (fictional patient, no real data).

    python samples/make_samples.py

Writes into this samples/ folder; upload them on the website to try ClaimClear:
  discharge_summary.pdf       digital PDF (text layer)
  claim_form_part_b.pdf       digital PDF with deliberate errors for the demo
  claim_form_part_b_scan.pdf  the same claim as an image-only "scan" (exercises OCR)

Deliberate errors in the claim, each caught by a rule:
  - patient name spelled "Ramesh Kumaar"       -> RULE_05 name mismatch
  - ICD-10 J18.9 for acute appendicitis        -> RULE_03 + RULE_20 (suggests K35.80)
  - ROHINI ID left blank                        -> RULE_08
  - line items add up to 71,000, total 75,000   -> RULE_16
  - "Room charges (3 days)" as one lump sum     -> RULE_11
  - OT notes not ticked in the checklist        -> RULE_15
"""
from datetime import date, timedelta
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parent
OUTPUTS = [OUT]
FONT, BOLD = "helv", "hebo"

# Dates relative to today so the demo never trips the filing-deadline rule by accident.
_T = date.today()
ADM, DIS, FUP = (( _T + timedelta(days=d)).strftime("%d/%m/%Y") for d in (-8, -5, 2))
PHARM = (_T - timedelta(days=7)).strftime("%d/%m/%Y")


class Doc:
    def __init__(self):
        self.doc = pymupdf.open()
        self.page = self.doc.new_page(width=595, height=842)
        self.y = 60

    def title(self, text, size=15):
        self.page.insert_text((50, self.y), text, fontname=BOLD, fontsize=size)
        self.y += size + 10

    def heading(self, text):
        self.y += 6
        self.page.draw_line((50, self.y - 11), (545, self.y - 11), color=(0.7, 0.7, 0.7), width=0.5)
        self.page.insert_text((50, self.y + 2), text.upper(), fontname=BOLD, fontsize=9.5, color=(0.1, 0.35, 0.33))
        self.y += 18

    def row(self, *pairs):
        x = 50
        width = 495 / len(pairs)
        for label, value in pairs:
            self.page.insert_text((x, self.y), f"{label}:", fontname=BOLD, fontsize=9.5)
            self.page.insert_text((x + 6 + pymupdf.get_text_length(f"{label}:", BOLD, 9.5), self.y), str(value), fontname=FONT, fontsize=9.5)
            x += width
        self.y += 16

    def line(self, text, size=9.5):
        self.page.insert_text((50, self.y), text, fontname=FONT, fontsize=size)
        self.y += size + 6

    def save(self, name):
        for folder in OUTPUTS:
            self.doc.save(folder / name)
        return self.doc


def discharge_summary():
    d = Doc()
    d.title("CITY CARE MULTISPECIALITY HOSPITAL")
    d.line("12, Sector 18, Noida, Uttar Pradesh · Ph 0120-4000000")
    d.title("DISCHARGE SUMMARY", 12)
    d.heading("Patient details")
    d.row(("Patient Name", "Mr. Ramesh Kumar"), ("Age", "45 Years"))
    d.row(("Sex", "Male"), ("Blood group", "B+"))
    d.row(("UHID", "CC-2026-00917"), ("IPD No", "4471"), ("Contact", "98765 43210"))
    d.heading("Admission")
    d.row(("Date of Admission", ADM), ("Time", "10:30"))
    d.row(("Date of Discharge", DIS), ("Time", "12:00"))
    d.row(("Type of Admission", "Emergency"), ("Department", "General Surgery"))
    d.heading("Clinical summary")
    d.row(("Chief Complaints", "Pain in right lower abdomen, fever, vomiting x 2 days"))
    d.row(("Provisional Diagnosis", "Acute appendicitis"))
    d.row(("Final Diagnosis", "Acute appendicitis"), ("ICD-10", "K35.80"))
    d.heading("Procedure")
    d.row(("Procedure", "Laparoscopic appendicectomy"), ("Code", "0DTJ4ZZ"))
    d.row(("Date", ADM), ("Anaesthesia", "General"))
    d.row(("Operating Surgeon", "Dr. Anil Mehta"), ("Histopathology", "Sent"))
    d.row(("Implant used", "No"))
    d.heading("Course in hospital")
    d.line("Patient underwent laparoscopic appendicectomy under GA on " + ADM + ". Post-operative period uneventful.")
    d.line("IV antibiotics given for 48 hours. Tolerating oral diet. Wound healthy.")
    d.heading("Condition at discharge")
    d.row(("Condition", "Stable"), ("Follow-up", FUP))
    d.heading("Treating doctor")
    d.row(("Name", "Dr. Anil Mehta"), ("Qualification", "MS (General Surgery)"))
    d.row(("Reg No", "DMC/45821"), ("Council", "Delhi Medical Council"))
    return d.save("discharge_summary.pdf")


def claim_form():
    d = Doc()
    d.title("HEALTH INSURANCE CLAIM FORM - PART B")
    d.line("To be filled in by the hospital · Insurance claim for reimbursement / cashless settlement")
    d.heading("Section A - Hospital details")
    d.row(("Name of Hospital", "City Care Multispeciality Hospital"), ("Type", "Network"))
    d.row(("Hospital ID (ROHINI)", ""), ("Phone", "0120-4000000"))
    d.row(("Treating Doctor", "Dr. Anil Mehta"), ("Qualification", "MS (General Surgery)"))
    d.row(("Registration No", "DMC/45821"))
    d.heading("Section B - Patient admitted")
    d.row(("Name of the Patient", "Ramesh Kumaar"), ("Age", "45"))
    d.row(("Gender", "Male"), ("Relationship to insured", "Self"))
    d.row(("IP Registration Number", "4471"), ("Policy No", "SH/2026/778812"))
    d.row(("Date of Admission", ADM), ("Time", "10:30"))
    d.row(("Date of Discharge", DIS), ("Time", "12:00"))
    d.row(("Type of Admission", "Emergency"), ("Status at Discharge", "Discharged home"))
    d.heading("Section C - Ailment details")
    d.row(("Primary Diagnosis", "Acute appendicitis"), ("ICD-10 Code", "J18.9"))
    d.row(("Procedure", "Laparoscopic appendicectomy"), ("ICD-10 PCS", "0DTJ4ZZ"))
    d.row(("Pre-Authorization obtained", "Yes"), ("Pre-Auth ID", "PA-2026-5541"))
    d.row(("System of Medicine", "Allopathy"))
    d.heading("Section D - Documents submitted")
    d.line("[x] Discharge summary   [x] Investigation reports   [ ] Operation theatre notes   [x] Pre-auth approval")
    d.line("[x] Itemized hospital bill   [x] Pharmacy bills   [ ] Implant invoice / stickers")
    d.heading("Section E - Billing summary (Rs.)")
    d.row(("Room & nursing charges", "12,000"), ("ICU charges", "0"))
    d.row(("OT charges", "25,000"), ("Surgeon / consultation fees", "18,000"))
    d.row(("Investigation charges", "6,500"), ("Medicines & consumables", "9,500"))
    d.row(("Total claimed amount", "75,000"))
    d.heading("Itemized bill")
    for line in (f"{ADM}   Room charges (3 days)                  12,000",
                 f"{ADM}   OT charges - laparoscopic appendicectomy  25,000",
                 f"{ADM}   CBC, CRP, USG abdomen                    6,500",
                 f"{ADM}   Surgeon & anaesthetist fees              18,000",
                 f"{PHARM}   Pharmacy & consumables                   9,500"):
        d.line(line)
    d.heading("Section F - Bank details of insured")
    d.row(("Account holder", "Ramesh Kumar"), ("Bank", "State Bank of India"))
    d.row(("Bank A/c No", "123456789012"), ("IFSC", "SBIN0001234"))
    return d.save("claim_form_part_b.pdf")


def scanned_copy(doc, name, dpi=170):
    scan = pymupdf.open()
    for page in doc:
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        p = scan.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=pix.tobytes(output="jpeg", jpg_quality=80))
    for folder in OUTPUTS:
        scan.save(folder / name)


if __name__ == "__main__":
    discharge_summary()
    scanned_copy(claim_form(), "claim_form_part_b_scan.pdf")
    print("Wrote samples to", OUT)
