from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAi 
from enum import Enum 
import os

Client=OpenAi(
    base_url="",
    api_key=os.getenv("")
)
app=FastAPI()

class Document_riskLevel(str,Enum):
    Low="low"
    medium="medium"
    High="high"

class DocAnalysis(BaseModel):
    Document_riskScore: int
    Document_risklevel:Document_riskLevel
    risks:list[RiskItem]

class RiskItem(BaseModel):
    type: str
    risk_level: Document_riskLevel
    clause: str
    explanation: str
    suggestion: str

