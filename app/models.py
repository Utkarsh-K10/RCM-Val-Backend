from sqlalchemy import Column, Integer, String, Float, Date, Text, JSON, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class MasterClaim(Base):
    __tablename__ = "master_claims"
    claim_id = Column(String, primary_key=True, index=True)
    encounter_type = Column(String)
    service_date = Column(Date)
    national_id = Column(String)
    member_id = Column(String)
    facility_id = Column(String)
    unique_id = Column(String)
    diagnosis_codes = Column(String)
    service_code = Column(String)
    paid_amount_aed = Column(Float)
    approval_number = Column(String, nullable=True)
    status = Column(String)
    error_type = Column(String)
    error_explanation = Column(JSON, default=list)
    recommended_action = Column(Text)

class ClaimError(Base):
    __tablename__ = "claim_errors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String, ForeignKey("master_claims.claim_id"))
    rule_id = Column(String)
    message = Column(Text)
    recommendation = Column(Text)

class ClaimMetrics(Base):
    __tablename__ = "claim_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String)
    count = Column(Integer)
    paid = Column(Float)
