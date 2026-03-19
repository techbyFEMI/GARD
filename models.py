from sqlalchemy import String, Column, Integer, Text, DateTime
from db import Base
from datetime import datetime , timezone

class ContractAnalysis(Base):
    __tablename__="contract_analysis"

    id =Column(Integer, primary_key=True, index=True)
    filename=Column(String)
    overall_risk_score=Column(Integer)
    overall_risk_level=Column(String)
    summary=Column(Text)
    risks=Column(Text)
    created_at=Column(DateTime, default=lambda: datetime.now(timezone.utc))



