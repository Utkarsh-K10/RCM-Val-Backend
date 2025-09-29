from sqlalchemy.orm import Session
from ..db import SessionLocal
from .. import models
from .static_eval import load_rules, evaluate_claim
from .llm_client import explain_with_llm
import datetime

def run_validation(job_id: str, tenant: str):
    print(f"[Worker] Running validation job {job_id} for tenant {tenant}")

    db: Session = SessionLocal()
    try:
        # Load rules (parsed from uploaded files)
        rules = load_rules(tenant)

        # Fetch pending claims
        pending_claims = db.query(models.MasterClaim).filter(models.MasterClaim.status == "Pending").all()
        print(f"[Worker] Found {len(pending_claims)} pending claims.")

        for claim in pending_claims:
            claim_dict = {
                "claim_id": claim.claim_id,
                "encounter_type": claim.encounter_type,
                "service_date": claim.service_date,
                "national_id": claim.national_id,
                "member_id": claim.member_id,
                "facility_id": claim.facility_id,
                "unique_id": claim.unique_id,
                "diagnosis_codes": (claim.diagnosis_codes or "").split(";"),
                "service_code": claim.service_code,
                "paid_amount_aed": claim.paid_amount_aed,
                "approval_number": claim.approval_number,
            }

            # --- Run static rule evaluation ---
            errors = evaluate_claim(claim_dict, rules)

            # --- Optionally enrich with LLM ---
            if errors:
                llm_explanations = explain_with_llm(claim_dict, errors)
                # merge LLM text into explanations
                for i, err in enumerate(errors):
                    if i < len(llm_explanations):
                        err["message"] += f" | LLM says: {llm_explanations[i]}"

            # --- Update DB ---
            if errors:
                claim.status = "Not validated"
                categories = {err["category"] for err in errors}
                if len(categories) == 1:
                    claim.error_type = f"{list(categories)[0].capitalize()} error"
                else:
                    claim.error_type = "Both"

                claim.error_explanation = [err["message"] for err in errors]
                claim.recommended_action = "; ".join({err["recommendation"] for err in errors})

                # Insert into claim_errors
                for err in errors:
                    ce = models.ClaimError(
                        claim_id=claim.claim_id,
                        rule_id=err["rule_id"],
                        message=err["message"],
                        recommendation=err["recommendation"],
                    )
                    db.add(ce)

            else:
                claim.status = "Validated"
                claim.error_type = "No error"
                claim.error_explanation = []
                claim.recommended_action = "No action needed."

            db.add(claim)

        db.commit()

        # --- Compute metrics for charts ---
        _compute_metrics(db)

        print("[Worker] Validation complete.")

    except Exception as e:
        print(f"[Worker] ERROR: {e}")
    finally:
        db.close()


def _compute_metrics(db: Session):
    """Aggregate metrics and store in claim_metrics."""
    db.query(models.ClaimMetrics).delete()  # reset metrics
    db.commit()

    results = db.query(
        models.MasterClaim.error_type,
        models.MasterClaim.status,
        models.MasterClaim.paid_amount_aed
    ).all()

    metrics = {}
    for error_type, status, paid in results:
        cat = error_type or "No error"
        if cat not in metrics:
            metrics[cat] = {"count": 0, "paid": 0.0}
        metrics[cat]["count"] += 1
        metrics[cat]["paid"] += paid or 0.0

    for cat, vals in metrics.items():
        m = models.ClaimMetrics(
            category=cat,
            count=vals["count"],
            paid=vals["paid"]
        )
        db.add(m)

    db.commit()
