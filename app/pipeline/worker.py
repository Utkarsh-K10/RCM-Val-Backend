# app/pipeline/worker.py
from sqlalchemy.orm import Session
from ..db import SessionLocal
from .. import models
from .static_eval import load_rules, evaluate_claim
from .llm_client import explain_with_llm
from ..db_utils import upsert
import os
import json

def run_validation(job_id: str, tenant: str):
    """
    RQ worker entrypoint: validates pending claims for tenant using static rules and LLM enrichment.
    """
    print(f"[Worker] Starting validation job {job_id} for tenant {tenant}")
    db: Session = SessionLocal()
    try:
        # load tenant rules (or default)
        rules = load_rules(tenant)

        # fetch claims inserted as Pending (worker handles all tenants but we use tenant-naming via rules files)
        pending = db.query(models.MasterClaim).filter(models.MasterClaim.status == "Pending").all()

        # clear claim_errors for these claims so re-run idempotent
        for c in pending:
            db.query(models.ClaimError).filter(models.ClaimError.claim_id == c.claim_id).delete()
        db.commit()

        for c in pending:
            # Build claim dict for static evaluation
            claim_dict = {
                "claim_id": c.claim_id,
                "encounter_type": c.encounter_type,
                "service_date": c.service_date,
                "national_id": c.national_id,
                "member_id": c.member_id,
                "facility_id": c.facility_id,
                "unique_id": c.unique_id,
                "diagnosis_codes": c.diagnosis_codes,
                "service_code": c.service_code,
                "paid_amount_aed": c.paid_amount_aed,
                "approval_number": c.approval_number
            }

            # Evaluate static rules
            errors = evaluate_claim(claim_dict, rules)

            if errors:
                # Determine error_type: technical / medical / both
                cats = {e.get("category") for e in errors}
                err_type = "Both" if len(cats) > 1 else (f"{list(cats)[0].capitalize()} error" if len(cats)==1 else "Technical error")
                c.status = "Not validated"
                c.error_type = err_type

                # insert ClaimError rows
                for e in errors:
                    ce = models.ClaimError(
                        claim_id=c.claim_id,
                        rule_id=e.get("rule_id"),
                        message=e.get("message"),
                        recommendation=e.get("recommendation")
                    )
                    db.add(ce)

                # LLM enrichment (optional)
                llm_out = explain_with_llm(claim_dict, errors)
                c.error_explanation = llm_out.get("bullets", [e["message"] for e in errors])
                c.recommended_action = llm_out.get("recommendation", "; ".join({e["recommendation"] for e in errors}))

            else:
                c.status = "Validated"
                c.error_type = "No error"
                c.error_explanation = []
                c.recommended_action = "No action needed."

            upsert(db, c)
            db.commit()

        # Recompute metrics table
        _compute_metrics(db)

        print(f"[Worker] Validation job {job_id} complete.")
    except Exception as ex:
        print("[Worker] ERROR:", ex)
    finally:
        db.close()

def _compute_metrics(db: Session):
    # Clear metrics table and aggregate counts and paid sums by error_type
    db.query(models.ClaimMetrics).delete()
    db.commit()

    rows = db.query(models.MasterClaim.error_type, models.MasterClaim.paid_amount_aed).all()
    metrics = {}
    for err_type, paid in rows:
        cat = err_type or "No error"
        if cat not in metrics:
            metrics[cat] = {"count": 0, "paid": 0.0}
        metrics[cat]["count"] += 1
        metrics[cat]["paid"] += (paid or 0.0)

    for cat, values in metrics.items():
        m = models.ClaimMetrics(category=cat, count=values["count"], paid=values["paid"])
        db.add(m)
    db.commit()
