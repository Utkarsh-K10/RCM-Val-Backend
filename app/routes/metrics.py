from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models

router = APIRouter()

@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    return db.query(models.ClaimMetrics).all()
