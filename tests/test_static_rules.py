# tests/test_static_rules.py
from app.pipeline.static_eval import evaluate_claim, load_rules

def test_unique_id_mismatch():
    # national/member/facility produce expected unique id parts
    claim = {
        "claim_id": "C1",
        "national_id": "AB12XXXX",
        "member_id": "12CDEFGH",
        "facility_id": "9XYZ",
        "unique_id": "AB12-CDE1-9XYZ",
        "diagnosis_codes": "",
        "service_code": "SRV2001",
        "paid_amount_aed": 10,
        "approval_number": None,
        "encounter_type": "OUTPATIENT"
    }
    rules = load_rules("default")
    errors = evaluate_claim(claim, rules)
    assert any(e['rule_id'].startswith("TECH_UNIQUEID") for e in errors)

def test_service_requires_diagnosis():
    claim = {
        "claim_id": "C2",
        "national_id": "A1B2C3D4",
        "member_id": "EFGH5678",
        "facility_id": "OCQUMGDW",
        "unique_id": "A1B2-GH56-MGDW",
        "diagnosis_codes": "",  # missing E11.9
        "service_code": "SRV2007",
        "paid_amount_aed": 100,
        "approval_number": None,
        "encounter_type": "OUTPATIENT"
    }
    rules = load_rules("default")
    errors = evaluate_claim(claim, rules)
    assert any("MED_SERVICE_SRV2007_MISSING_REQUIRED_DIAG" == e['rule_id'] for e in errors)
