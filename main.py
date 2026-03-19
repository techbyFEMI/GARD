from fastapi import FastAPI,UploadFile,File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from enum import Enum 
from dotenv import load_dotenv
from docx import Document as DocxDocument
import os
import pdfplumber
import io
import json


load_dotenv()

client=OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)
app=FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class Document_riskLevel(str,Enum):
    Low="low"
    medium="medium"
    High="high"

class RiskItem(BaseModel):
    type: str
    risk_level: Document_riskLevel
    clause: str
    explanation: str
    suggestion: str

class DocAnalysis(BaseModel):
    Document_riskScore: int
    Document_risklevel:Document_riskLevel
    risks:list[RiskItem]
    summary:str


def docextract(file_bytes:bytes, filename: str)-> str:
    if filename.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        print("PDF D0cument extracted successfully.")
        return text

    elif filename.endswith(".docx"):
        doc=DocxDocument(io.BytesIO(file_bytes))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        print("PDF D0cument extracted successfully.")
        return text

    else: 
        return ""

   

@app.post("/analyzeDoc")
async def analyze(file: UploadFile = File(...)):
    file_byte = await file.read()
    contract_text = docextract(file_byte, file.filename)

    if not contract_text.strip():
        return {"error": "Could not extract file. Make sure it is a PDF file or Docx file."}

    prompt = f"""
    You are a legal risk analyst specializing in freelance contracts.
    Analyze the following contract and return ONLY a JSON object.
    Do not include any text outside the JSON.

    SCORING RULES — follow these exactly:

    Start with a base score of 0. Add points for each risk found:

    PAYMENT TERMS:
    - Payment beyond 30 days → +15
    - No payment timeline mentioned → +20
    - Payment on client satisfaction (subjective) → +25

    NON-COMPETE:
    - Non-compete longer than 6 months → +20
    - Non-compete longer than 12 months → +30
    - Non-compete with no geographic limit → +10

    IP OWNERSHIP:
    - Full IP transfer to client → +10
    - No IP clause mentioned → +15
    - Freelancer retains no rights → +20

    TERMINATION:
    - Client can terminate without notice → +20
    - No termination clause → +15
    - Freelancer penalized for early exit → +20

    EXCLUSIVITY:
    - Freelancer cannot work with others → +25
    - Exclusivity with no time limit → +30

    LIABILITY:
    - Freelancer liable for client losses → +25
    - No liability cap mentioned → +15

    RISK LEVELS based on final score:
    - 0 to 30 → low
    - 31 to 60 → medium
    - 61 and above → high

    Return this exact JSON structure:
    {{
      "overall_risk_score": <calculated total from rules above>,
      "overall_risk_level": "<low, medium, or high based on score>",
      "summary": "<2-3 sentence plain English summary of the contract>",
      "risks": [
        {{
          "type": "<payment_terms, non_compete, ip_ownership, termination, exclusivity, or liability>",
          "risk_level": "<low, medium, or high>",
          "clause": "<exact quote from the contract>",
          "explanation": "<why this is risky for the freelancer>",
          "suggestion": "<what the freelancer should negotiate>"
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

    return result