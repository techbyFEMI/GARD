from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db import get_db
from models import ContractAnalysis
from openai import OpenAI
from enum import Enum
from dotenv import load_dotenv
from docx import Document as DocxDocument

import os
import pdfplumber
import io
import json
import hashlib

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class Document_riskLevel(str, Enum):
    Low = "low"
    medium = "medium"
    High = "high"

class RiskItem(BaseModel):
    type: str
    risk_level: Document_riskLevel
    clause: str
    explanation: str
    replacement_language: str
    suggested_message: str

class DocAnalysis(BaseModel):
    Document_riskScore: int
    Document_risklevel: Document_riskLevel
    risks: list[RiskItem]
    summary: str

@app.get("/check")
async def serverStatus():
    return {"status": "ok"}

def docextract(file_bytes: bytes, filename: str) -> str:
    if filename.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        return text
    elif filename.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(file_bytes))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    else:
        return ""

def calculate_risk_score(risks: list) -> tuple:
    score = 0
    max_possible = 0
    score_map = {
        "payment_terms": {"high": 25, "medium": 15, "low": 0},
        "non_compete": {"high": 30, "medium": 20, "low": 10},
        "ip_ownership": {"high": 20, "medium": 15, "low": 10},
        "termination": {"high": 20, "medium": 15, "low": 0},
        "exclusivity": {"high": 30, "medium": 25, "low": 0},
        "liability": {"high": 25, "medium": 15, "low": 0},
    }

    for risk in risks:
        risk_type = risk.get("type", "")
        risk_level = risk.get("risk_level", "low")
        points = score_map.get(risk_type, {}).get(risk_level, 0)
        max_points = max(score_map.get(risk_type, {}).values(), default=0)
        score += points
        max_possible += max_points

    percentage = round((score / max_possible) * 100) if max_possible > 0 else 0

    if percentage >= 61:
        level = "high"
    elif percentage >= 31:
        level = "medium"
    else:
        level = "low"

    return percentage, level

def safe_parse_json(raw: str):
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception:
        return None

def validate_result(data: dict):
    if not data:
        return False
    if "summary" not in data or "risks" not in data:
        return False
    if not isinstance(data["risks"], list):
        return False
    if len(data["risks"]) != 6:
        return False
    required_types = {
        "payment_terms",
        "non_compete",
        "ip_ownership",
        "termination",
        "exclusivity",
        "liability"
    }
    found_types = {r.get("type") for r in data["risks"]}
    return required_types.issubset(found_types)

def fallback_response():
    types = [
        "payment_terms",
        "non_compete",
        "ip_ownership",
        "termination",
        "exclusivity",
        "liability"
    ]
    return {
        "summary": "Could not fully analyze contract. Defaulting to safe baseline.",
        "risks": [
            {
                "type": t,
                "risk_level": "low",
                "clause": "Unavailable",
                "explanation": "Analysis failed.",
                "replacement_language": "",
                "suggested_message": ""
            } for t in types
        ],
        "overall_risk_score": 0,
        "overall_risk_level": "low",
        "cached": False
    }

@app.post("/analyzeDoc")
async def analyze(file: UploadFile = File(...), db: Session = Depends(get_db)):
    file_byte = await file.read()
    file_hash = hashlib.sha256(file_byte).hexdigest()

    existing = db.query(ContractAnalysis).filter(
        ContractAnalysis.file_hash == file_hash
    ).first()

    if existing:
        return {
            "summary": existing.summary,
            "risks": json.loads(existing.risks),
            "overall_risk_score": existing.overall_risk_score,
            "overall_risk_level": existing.overall_risk_level,
            "cached": True
        }

    contract_text = docextract(file_byte, file.filename)

    if not contract_text.strip():
        return {"error": "Could not extract file. Make sure it is a PDF or DOCX file."}

    prompt = f"""
You are a strict legal contract risk analyzer.

Your job is to analyze the contract and produce a CONSISTENT, STRUCTURED result.

IMPORTANT RULES:
- You MUST return EXACTLY 6 risks.
- Each risk MUST correspond to ONE of these types:
  payment_terms, non_compete, ip_ownership, termination, exclusivity, liability
- Do NOT invent new types.
- If a category is NOT present in the contract, still include it with:
  - risk_level = "low"
  - clause = "Not explicitly stated"
  - explanation = "No explicit clause found for this category."
- Be consistent and conservative in classification.

RISK LEVEL DEFINITIONS:
- high → clearly harmful to freelancer
- medium → somewhat negotiable or unclear
- low → standard or safe

OUTPUT FORMAT (STRICT JSON ONLY):
{{
  "summary": "<2-3 sentence summary>",
  "risks": [
    {{"type": "payment_terms","risk_level": "low|medium|high","clause": "","explanation": "","replacement_language": "","suggested_message": ""}},
    {{"type": "non_compete","risk_level": "low|medium|high","clause": "","explanation": "","replacement_language": "","suggested_message": ""}},
    {{"type": "ip_ownership","risk_level": "low|medium|high","clause": "","explanation": "","replacement_language": "","suggested_message": ""}},
    {{"type": "termination","risk_level": "low|medium|high","clause": "","explanation": "","replacement_language": "","suggested_message": ""}},
    {{"type": "exclusivity","risk_level": "low|medium|high","clause": "","explanation": "","replacement_language": "","suggested_message": ""}},
    {{"type": "liability","risk_level": "low|medium|high","clause": "","explanation": "","replacement_language": "","suggested_message": ""}}
  ]
}}

CONTRACT:
{contract_text[:4000]}
"""

    MAX_RETRIES = 3
    result = None

    for _ in range(MAX_RETRIES):
        response = client.chat.completions.create(
            model="arcee-ai/trinity-large-preview:free",
            messages=[
                {"role": "system", "content": "Return STRICT valid JSON only. No markdown."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        raw = response.choices[0].message.content
        parsed = safe_parse_json(raw)
        if validate_result(parsed):
            result = parsed
            break

    if not result:
        return fallback_response()

    score, level = calculate_risk_score(result.get("risks", []))
    result["overall_risk_score"] = score
    result["overall_risk_level"] = level
    result["cached"] = False

    record = ContractAnalysis(
        filename=file.filename,
        file_hash=file_hash,
        overall_risk_score=score,
        overall_risk_level=level,
        summary=result.get("summary"),
        risks=json.dumps(result.get("risks", []))
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return result

@app.get("/history")
def get_history(db: Session = Depends(get_db)):
    records = db.query(ContractAnalysis).order_by(
        ContractAnalysis.created_at.desc()
    ).limit(20).all()

    return [
        {
            "id": r.id,
            "filename": r.filename,
            "overall_risk_score": r.overall_risk_score,
            "overall_risk_level": r.overall_risk_level,
            "summary": r.summary,
            "risks": json.loads(r.risks) if r.risks else [],
            "created_at": r.created_at.strftime("%b %d, %Y %H:%M") if r.created_at else ""
        }
        for r in records
    ]

@app.delete("/history/{record_id}")
def delete_history(record_id: int, db: Session = Depends(get_db)):
    record = db.query(ContractAnalysis).filter(ContractAnalysis.id == record_id).first()
    if not record:
        return {"error": "Record not found"}
    db.delete(record)
    db.commit()
    return {"message": "Deleted successfully"}