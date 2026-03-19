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


def docextract(file_bytes: bytes, filename: str) -> str:
    if filename.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        print("PDF Document extracted successfully.")
        return text
    elif filename.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(file_bytes))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        print("DOCX Document extracted successfully.")
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

@app.post("/analyzeDoc")
async def analyze(file: UploadFile = File(...), db: Session = Depends(get_db)):
    file_byte = await file.read()
    contract_text = docextract(file_byte, file.filename)

    if not contract_text.strip():
        return {"error": "Could not extract file. Make sure it is a PDF or DOCX file."}

    prompt = f"""
    You are a legal risk analyst and negotiation coach specializing in freelance contracts.
    Analyze the following contract and return ONLY a JSON object.
    Do not include any text outside the JSON.

    For each risk found, classify the risk_level as:
    - high: severely disadvantages the freelancer
    - medium: moderately risky, negotiable
    - low: minor concern, standard practice

    Return this exact JSON structure:
    {{
      "summary": "<2-3 sentence plain English summary of the contract>",
      "risks": [
        {{
          "type": "<payment_terms, non_compete, ip_ownership, termination, exclusivity, or liability>",
          "risk_level": "<low, medium, or high>",
          "clause": "<exact quote from the contract>",
          "explanation": "<why this specific clause is risky for the freelancer in 2 sentences>",
          "replacement_language": "<exact contract wording the freelancer should propose as a replacement>",
          "suggested_message": "<a short professional message the freelancer can send to the client>"
        }}
      ]
    }}

    Contract:
    {contract_text[:4000]}
    """

    response = client.chat.completions.create(
        model="arcee-ai/trinity-large-preview:free",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.choices[0].message.content
    clean = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(clean)

    # Override LLM score with deterministic Python calculation
    score, level = calculate_risk_score(result.get("risks", []))
    result["overall_risk_score"] = score
    result["overall_risk_level"] = level

    record = ContractAnalysis(
        filename=file.filename,
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