# app/routes/upload.py
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models
import pandas as pd
import uuid
import io
from ..pipeline.queue import queue
from ..pipeline.worker import run_validation
from ..db_utils import upsert

router = APIRouter()

REQUIRED_COLUMNS = [
    "claim_id", "encounter_type", "service_date", "national_id",
    "member_id", "facility_id", "unique_id", "diagnosis_codes",
    "service_code", "paid_amount_aed", "approval_number"
]

INSTRUCTION_SNIPPET = (
    "Submission schema required: claim_id | encounter_type | service_date | national_id | "
    "member_id | facility_id | unique_id | diagnosis_codes | service_code | paid_amount_aed | approval_number."
)

@router.post("/upload")
async def upload_files(
    claims: UploadFile = File(...),
    technical: UploadFile = File(...),
    medical: UploadFile = File(...),
    tenant: str = Form("default"),
    db: Session = Depends(get_db)
):
    """
    Upload claims + rules, do schema validation immediately,
    then enqueue background validation (static + LLM).
    """
    job_id = str(uuid.uuid4())

    try:
        # ---- Step 1: Read claims Excel ----
        content = await claims.read()
        try:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read claims Excel file: {e}")

        df.columns = [str(c).strip().lower() for c in df.columns]

        # ---- Step 2: Handle claim_id ----
        cols = df.columns.tolist()
        if "claim_id" not in cols:
            df.insert(0, "claim_id", [f"AUTO_{i+1}" for i in range(len(df))])
            print("[Upload] claim_id missing -> auto-generated.")

        # Check for other required columns
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing_cols:
            placeholder_id = f"UPLOAD_SCHEMA_ERROR_{job_id}"
            explanation = [f"Missing required columns: {', '.join(missing_cols)}", INSTRUCTION_SNIPPET]
            placeholder = models.MasterClaim(
                claim_id=placeholder_id,
                encounter_type=None,
                service_date=None,
                national_id=None,
                member_id=None,
                facility_id=None,
                unique_id=None,
                diagnosis_codes=None,
                service_code=None,
                paid_amount_aed=None,
                approval_number=None,
                status="Not validated",
                error_type="Technical error",
                error_explanation=explanation,
                recommended_action=f"Add missing columns: {', '.join(missing_cols)}. {INSTRUCTION_SNIPPET}"
            )
            upsert(db, placeholder)
            db.commit()
            raise HTTPException(status_code=400, detail={"error": "schema_missing", "missing_columns": missing_cols})

        # ---- Step 3: Insert all claims as Pending ----
        inserted = 0
        for _, raw_row in df.iterrows():
            row = {k: (v if not (isinstance(v, float) and pd.isna(v)) else None) for k, v in raw_row.items()}
            claim_id_val = str(row.get("claim_id") or f"auto_{uuid.uuid4()}")

            claim = models.MasterClaim(
                claim_id=claim_id_val,
                encounter_type=row.get("encounter_type"),
                service_date=row.get("service_date"),
                national_id=row.get("national_id"),
                member_id=row.get("member_id"),
                facility_id=row.get("facility_id"),
                unique_id=row.get("unique_id"),
                diagnosis_codes=row.get("diagnosis_codes"),
                service_code=row.get("service_code"),
                paid_amount_aed=row.get("paid_amount_aed"),
                approval_number=row.get("approval_number"),
                status="Pending",
                error_type="",
                error_explanation=[],
                recommended_action=""
            )

            upsert(db, claim)
            inserted += 1

        # Commit once after all rows
        db.commit()

        # ---- Step 4: Save rules ----
        tech_bytes = await technical.read()
        med_bytes = await medical.read()

        try:
            import json as _json
            _decoded = _json.loads(tech_bytes.decode("utf-8"))
            with open(f"app/rules/{tenant}_technical.json", "w", encoding="utf-8") as f:
                f.write(_json.dumps(_decoded, indent=2))
        except Exception:
            with open(f"app/rules/{tenant}_technical.pdf", "wb") as f:
                f.write(tech_bytes)

        try:
            _decoded = _json.loads(med_bytes.decode("utf-8"))
            with open(f"app/rules/{tenant}_medical.json", "w", encoding="utf-8") as f:
                f.write(_json.dumps(_decoded, indent=2))
        except Exception:
            with open(f"app/rules/{tenant}_medical.pdf", "wb") as f:
                f.write(med_bytes)

        # ---- Step 5: Enqueue async validation job ----
        try:
            job = queue.enqueue(run_validation, job_id, tenant)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to enqueue job: {e}")

        return {
            "message": "Files uploaded successfully. Validation running in background.",
            "job_id": job.id if job else job_id,
            "inserted": inserted
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload error: {str(e)}")
