# app/routes/upload.py
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models
import pandas as pd
import uuid
import io
from ..pipeline.queue import queue
from ..db_utils import upsert

router = APIRouter()

REQUIRED_COLUMNS = [
    "claim_id", "encounter_type", "service_date", "national_id",
    "member_id", "facility_id", "unique_id", "diagnosis_codes",
    "service_code", "paid_amount_aed", "approval_number"
]

@router.post("/upload")
async def upload_files(
    claims: UploadFile = File(...),
    technical: UploadFile = File(...),
    medical: UploadFile = File(...),
    tenant: str = Form("default"),
    db: Session = Depends(get_db)
):
    job_id = str(uuid.uuid4())
    try:
        content = await claims.read()
        try:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read claims Excel file: {e}")

        df.columns = [str(c).strip().lower() for c in df.columns]
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing_cols:
            placeholder = models.MasterClaim(
                claim_id=f"UPLOAD_SCHEMA_ERROR_{job_id}",
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
                error_explanation=[f"Missing required columns: {', '.join(missing_cols)}"],
                recommended_action=f"Add missing columns: {', '.join(missing_cols)}"
            )
            upsert(db, placeholder)
            db.commit()
            raise HTTPException(status_code=400, detail={"error": "schema_missing", "missing_columns": missing_cols})

        inserted = 0
        for _, raw_row in df.iterrows():
            # safe coercion of missing values
            row = {k: (v if not (isinstance(v, float) and pd.isna(v)) else None) for k, v in raw_row.items()}

            # Normalize: uppercase IDs & unique_id; diagnosis_codes to comma-separated uppercase string
            claim_id_val = str(row.get("claim_id") or f"auto_{uuid.uuid4()}").upper()
            national_id = (str(row.get("national_id")).strip().upper() if row.get("national_id") else None)
            member_id = (str(row.get("member_id")).strip().upper() if row.get("member_id") else None)
            facility_id = (str(row.get("facility_id")).strip().upper() if row.get("facility_id") else None)
            unique_id = (str(row.get("unique_id")).strip().upper() if row.get("unique_id") else None)
            service_code = (str(row.get("service_code")).strip().upper() if row.get("service_code") else None)
            approval_number = (str(row.get("approval_number")).strip() if row.get("approval_number") else None)
            # normalize diagnosis codes: split by ; or , and rejoin by comma
            diag_raw = row.get("diagnosis_codes") or ""
            if isinstance(diag_raw, str):
                diag_list = [d.strip().upper() for d in diag_raw.replace(";",",").split(",") if d.strip() != ""]
                diagnosis_codes_str = ",".join(diag_list)
            else:
                diagnosis_codes_str = ""

            paid = row.get("paid_amount_aed")

            claim = models.MasterClaim(
                claim_id=claim_id_val,
                encounter_type=row.get("encounter_type"),
                service_date=row.get("service_date"),
                national_id=national_id,
                member_id=member_id,
                facility_id=facility_id,
                unique_id=unique_id,
                diagnosis_codes=diagnosis_codes_str,
                service_code=service_code,
                paid_amount_aed=paid,
                approval_number=approval_number,
                status="Pending",
                error_type="",
                error_explanation=[],
                recommended_action=""
            )

            upsert(db, claim)
            db.commit()
            inserted += 1

        # save rules to disk (json if provided otherwise save pdf bytes)
        tech_bytes = await technical.read()
        med_bytes = await medical.read()

        # attempt JSON decode
        try:
            import json as _json
            t_json = _json.loads(tech_bytes.decode("utf-8"))
            with open(f"app/rules/{tenant}_technical.json", "w", encoding="utf-8") as f:
                _json.dump(t_json, f, indent=2)
        except Exception:
            with open(f"app/rules/{tenant}_technical.pdf", "wb") as f:
                f.write(tech_bytes)

        try:
            m_json = _json.loads(med_bytes.decode("utf-8"))
            with open(f"app/rules/{tenant}_medical.json", "w", encoding="utf-8") as f:
                _json.dump(m_json, f, indent=2)
        except Exception:
            with open(f"app/rules/{tenant}_medical.pdf", "wb") as f:
                f.write(med_bytes)

        # enqueue background validation job
        job = queue.enqueue("app.pipeline.worker.run_validation", job_id, tenant)
        # note: RQ can accept callable path string in some setups; if not, use queue.enqueue(run_validation, job_id, tenant)

        return {"message": "Files uploaded; validation enqueued (async)", "job_id": job.id, "inserted": inserted}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload error: {str(e)}")
