# app/pipeline/static_eval.py
import re
import json
import os
from typing import Dict, List, Any

# --- Hard-coded defaults extracted from the Technical & Medical rules you provided.
# These are used if tenant JSON files are not present.

DEFAULT_TECH_APPROVAL_SERVICES = {"SRV1001", "SRV1002", "SRV2008"}
DEFAULT_TECH_DIAG_APPROVAL = {"E11.9", "R07.9", "Z34.0"}
DEFAULT_PAID_THRESHOLD = 250.0

# Encounter restrictions
INPATIENT_ONLY = {"SRV1001", "SRV1002", "SRV1003"}
OUTPATIENT_ONLY = {
    "SRV2001", "SRV2002", "SRV2003", "SRV2004", "SRV2006",
    "SRV2007", "SRV2008", "SRV2010", "SRV2011"
}

# Facility service mapping (from medical rules' Facility Registry)
FACILITY_REGISTRY = {
    "0DBYE6KP": "DIALYSIS_CENTER",
    "2XKSZK4T": "MATERNITY_HOSPITAL",
    "7R1VMIGX": "CARDIOLOGY_CENTER",
    "96GUDLMT": "GENERAL_HOSPITAL",
    "9V7HTI6E": "GENERAL_HOSPITAL",
    "EGVP0QAQ": "GENERAL_HOSPITAL",
    "EPRETQTL": "DIALYSIS_CENTER",
    "FLXFBIMD": "GENERAL_HOSPITAL",
    "GLCTDQAJ": "MATERNITY_HOSPITAL",
    "GY0GUI8G": "GENERAL_HOSPITAL",
    "I2MFYKYM": "GENERAL_HOSPITAL",
    "LB7I54Z7": "CARDIOLOGY_CENTER",
    "M1XCZVQD": "CARDIOLOGY_CENTER",
    "M7DJYNG5": "GENERAL_HOSPITAL",
    "MT5W4HIR": "MATERNITY_HOSPITAL",
    "OCQUMGDW": "GENERAL_HOSPITAL",
    "OIAP2DTP": "CARDIOLOGY_CENTER",
    "Q3G9N34N": "GENERAL_HOSPITAL",
    "Q8OZ5Z7C": "GENERAL_HOSPITAL",
    "RNPGDXCU": "MATERNITY_HOSPITAL",
    "S174K5QK": "GENERAL_HOSPITAL",
    "SKH7D31V": "CARDIOLOGY_CENTER",
    "SZC62NTW": "GENERAL_HOSPITAL",
    "VV1GS6P0": "MATERNITY_HOSPITAL",
    "ZDE6M6NJ": "GENERAL_HOSPITAL",
    # Add more entries from your registry string as needed...
}

FACILITY_TYPE_ALLOWED_SERVICES = {
    "MATERNITY_HOSPITAL": {"SRV2008"},
    "DIALYSIS_CENTER": {"SRV1003", "SRV2010"},
    "CARDIOLOGY_CENTER": {"SRV2001", "SRV2011"},
    "GENERAL_HOSPITAL": {
        "SRV1001","SRV1002","SRV1003","SRV2001","SRV2002","SRV2003",
        "SRV2004","SRV2006","SRV2007","SRV2008","SRV2010","SRV2011"
    }
}

# Service -> required diagnosis (medical rules C)
SERVICE_REQUIRED_DIAG = {
    "SRV2007": {"E11.9"},      # HbA1c requires Diabetes E11.9
    "SRV2006": {"J45.909"},    # Pulmonary Function Test requires Asthma
    "SRV2001": {"R07.9"},      # ECG requires Chest Pain
    "SRV2008": {"Z34.0"},      # Ultrasonogram – Pregnancy Check requires Pregnancy
    "SRV2005": {"N39.0"},      # Urine Culture requires UTI
}

# Mutually exclusive diagnosis pairs (medical D)
MUTUALLY_EXCLUSIVE_PAIRS = [
    ({"R73.03"}, {"E11.9"}),
    ({"E66.9"}, {"E66.3"}),
    ({"R51"}, {"G43.9"})
]


def _normalize_value(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return None
        # treat common n/a markers as missing
        if s.upper() in {"NA", "N/A", "NONE", "NULL", "-"}:
            return None
        return s
    return v


def load_rules(tenant: str) -> Dict[str, Any]:
    """
    Load tenant-specific rule JSONs if present, else fallback to defaults.
    Expects files at app/rules/{tenant}_technical.json and ..._medical.json
    """
    base = f"app/rules/{tenant}"
    tech_path = f"{base}_technical.json"
    med_path = f"{base}_medical.json"

    rules = {
        "technical": {
            "approval_services": DEFAULT_TECH_APPROVAL_SERVICES,
            "diag_approval": DEFAULT_TECH_DIAG_APPROVAL,
            "paid_threshold": DEFAULT_PAID_THRESHOLD
        },
        "medical": {
            "inpatient_only": INPATIENT_ONLY,
            "outpatient_only": OUTPATIENT_ONLY,
            "facility_registry": FACILITY_REGISTRY,
            "facility_allowed": FACILITY_TYPE_ALLOWED_SERVICES,
            "service_required_diag": SERVICE_REQUIRED_DIAG,
            "mutual_exclusive": MUTUALLY_EXCLUSIVE_PAIRS
        }
    }

    # if tenant jsons exist and contain structured rules, try to load and override
    try:
        if os.path.exists(tech_path):
            with open(tech_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # expected structure is flexible; check keys
                if isinstance(loaded, dict):
                    rules["technical"].update(loaded)
    except Exception:
        pass

    try:
        if os.path.exists(med_path):
            with open(med_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    rules["medical"].update(loaded)
    except Exception:
        pass

    return rules


def _is_upper_alnum(val: str) -> bool:
    if not isinstance(val, str):
        return False
    return bool(re.fullmatch(r"[A-Z0-9]+", val))


def _compute_middle4(member_id: str) -> str:
    """Return the middle-4 characters of member_id (if possible)."""
    if not member_id:
        return None
    s = member_id
    n = len(s)
    if n <= 4:
        return s[:4].upper().ljust(4, 'X')[:4]
    start = (n - 4) // 2
    return s[start:start + 4].upper()


def evaluate_claim(claim: Dict[str, Any], rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Evaluate a single claim dict against the technical and medical rules.
    claim keys expected: claim_id, encounter_type, service_date, national_id,
      member_id, facility_id, unique_id, diagnosis_codes (list), service_code,
      paid_amount_aed, approval_number
    Returns list of error dicts with keys: rule_id, category, message, recommendation
    """
    errs = []

    # Normalize inputs
    cid = _normalize_value(claim.get("claim_id"))
    encounter = _normalize_value(claim.get("encounter_type"))
    service = _normalize_value(claim.get("service_code"))
    national_id = _normalize_value(claim.get("national_id"))
    member_id = _normalize_value(claim.get("member_id"))
    facility_id = _normalize_value(claim.get("facility_id"))
    unique_id = _normalize_value(claim.get("unique_id"))
    approval = _normalize_value(claim.get("approval_number"))
    paid = claim.get("paid_amount_aed")
    # normalize diagnosis codes -> list of uppercase codes
    raw_diag = claim.get("diagnosis_codes") or []
    if isinstance(raw_diag, str):
        # split on ; or , or |
        diag_list = [d.strip().upper() for d in re.split(r"[;,|]", raw_diag) if d.strip() != ""]
    elif isinstance(raw_diag, list):
        diag_list = [str(d).strip().upper() for d in raw_diag if str(d).strip() != ""]
    else:
        diag_list = []

    # Helper to detect real approval numbers: not None and not a placeholder like 'Obtain approval'
    def has_valid_approval(x):
        if x is None:
            return False
        if isinstance(x, str):
            s = x.strip()
            if s == "":
                return False
            if s.upper() in {"NA", "N/A", "NONE"}:
                return False
            if s.strip().lower() in {"obtain approval", "obtain approval "}:
                return False
            # otherwise treat as provided (APP001 etc)
            return True
        return True

    # TECHNICAL RULES
    tech = rules.get("technical", {})
    tech_approval_svcs = set([s.upper() for s in tech.get("approval_services", DEFAULT_TECH_APPROVAL_SERVICES)])
    tech_diag_approval = set([d.upper() for d in tech.get("diag_approval", DEFAULT_TECH_DIAG_APPROVAL)])
    paid_threshold = float(tech.get("paid_threshold", DEFAULT_PAID_THRESHOLD))

    # 1) ID formatting checks (All IDs uppercase alphanumeric)
    for field_name, value in [("claim_id", cid), ("national_id", national_id), ("member_id", member_id), ("facility_id", facility_id)]:
        if value is None or not _is_upper_alnum(value.upper()):
            errs.append({
                "rule_id": f"TECH_{field_name.upper()}_FORMAT",
                "category": "technical",
                "message": f"{field_name} must be UPPERCASE alphanumeric (A–Z, 0–9).",
                "recommendation": f"Ensure {field_name} uses uppercase letters and digits only."
            })

    # 2) unique_id structure check: first4(national)-middle4(member)-last4(facility), hyphen-separated
    if unique_id is None:
        errs.append({
            "rule_id": "TECH_UNIQUEID_MISSING",
            "category": "technical",
            "message": "unique_id is missing.",
            "recommendation": "Provide unique_id using first4(national_id)-middle4(member_id)-last4(facility_id)."
        })
    else:
        uid = unique_id.upper()
        if not re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}", uid):
            errs.append({
                "rule_id": "TECH_UNIQUEID_FORMAT",
                "category": "technical",
                "message": "unique_id must be 3 segments of 4 UPPERCASE alphanumeric characters separated by hyphens.",
                "recommendation": "Format unique_id as first4(national)-middle4(member)-last4(facility)."
            })
        else:
            seg1, seg2, seg3 = uid.split("-")
            expected1 = (national_id or "")[:4].upper() if national_id else None
            expected2 = _compute_middle4(member_id) if member_id else None
            expected3 = (facility_id or "")[-4:].upper() if facility_id else None
            # Compare only if sources exist; if they do and mismatch -> error
            mismatches = []
            if expected1 and seg1 != expected1:
                mismatches.append(f"segment1 expected {expected1} but got {seg1}")
            if expected2 and seg2 != expected2:
                mismatches.append(f"segment2 expected {expected2} but got {seg2}")
            if expected3 and seg3 != expected3:
                mismatches.append(f"segment3 expected {expected3} but got {seg3}")
            if mismatches:
                errs.append({
                    "rule_id": "TECH_UNIQUEID_MISMATCH",
                    "category": "technical",
                    "message": "unique_id segments do not match underlying ID sources: " + "; ".join(mismatches),
                    "recommendation": "Rebuild unique_id using the specified segments from national_id, member_id and facility_id."
                })

    # 3) Paid amount threshold
    try:
        if paid is not None and float(paid) > paid_threshold and not has_valid_approval(approval):
            errs.append({
                "rule_id": "TECH_PAID_THRESHOLD_APPROVAL",
                "category": "technical",
                "message": f"Paid amount AED {paid} exceeds threshold AED {paid_threshold} and no valid approval number present.",
                "recommendation": "Obtain prior approval and include approval number in approval_number field."
            })
    except Exception:
        # if parsing paid fails, ignore here (other validators or DB schema handles)
        pass

    # 4) Service-based approval requirement
    if service and service.upper() in tech_approval_svcs and not has_valid_approval(approval):
        errs.append({
            "rule_id": f"TECH_SERVICE_{service}_REQUIRES_APPROVAL",
            "category": "technical",
            "message": f"Service {service} requires prior approval but no valid approval number was supplied.",
            "recommendation": "Obtain and include prior approval number for this service."
        })

    # 5) Diagnosis-based approval requirement
    for d in diag_list:
        if d in tech_diag_approval and not has_valid_approval(approval):
            errs.append({
                "rule_id": f"TECH_DIAG_{d}_REQUIRES_APPROVAL",
                "category": "technical",
                "message": f"Diagnosis {d} requires prior approval, but approval number missing.",
                "recommendation": "Obtain and include prior approval number for claims with this diagnosis."
            })
            # one message per diag is sufficient
            break

    # MEDICAL RULES
    med = rules.get("medical", {})
    inpatient_only = set(med.get("inpatient_only", INPATIENT_ONLY))
    outpatient_only = set(med.get("outpatient_only", OUTPATIENT_ONLY))
    facility_registry = med.get("facility_registry", FACILITY_REGISTRY)
    facility_allowed = med.get("facility_allowed", FACILITY_TYPE_ALLOWED_SERVICES)
    service_required_diag = med.get("service_required_diag", SERVICE_REQUIRED_DIAG)
    mutual_exclusive = med.get("mutual_exclusive", MUTUALLY_EXCLUSIVE_PAIRS)

    svc = (service or "").upper()
    # 6) Encounter type constraints
    if svc in inpatient_only and (not encounter or encounter.upper() != "INPATIENT"):
        errs.append({
            "rule_id": f"MED_ENCOUNTER_{svc}_INPATIENT_ONLY",
            "category": "medical",
            "message": f"Service {svc} is inpatient-only but claim encounter_type={encounter}.",
            "recommendation": "Verify encounter_type is INPATIENT for this service."
        })
    if svc in outpatient_only and (not encounter or encounter.upper() != "OUTPATIENT"):
        errs.append({
            "rule_id": f"MED_ENCOUNTER_{svc}_OUTPATIENT_ONLY",
            "category": "medical",
            "message": f"Service {svc} is outpatient-only but claim encounter_type={encounter}.",
            "recommendation": "Verify encounter_type is OUTPATIENT for this service."
        })

    # 7) Facility type constraints
    fac_type = facility_registry.get(facility_id) if facility_id else None
    if fac_type:
        allowed = facility_allowed.get(fac_type, set())
        if svc and svc not in allowed:
            errs.append({
                "rule_id": f"MED_FACILITY_{svc}_NOT_ALLOWED",
                "category": "medical",
                "message": f"Service {svc} is not allowed at facility {facility_id} (type {fac_type}).",
                "recommendation": f"Perform {svc} at a facility type that supports it (current facility type: {fac_type})."
            })
    else:
        # unknown facility - optionally warn (not necessarily fail)
        pass

    # 8) Service requires specific diagnosis
    required = service_required_diag.get(svc)
    if required:
        if not any(d in diag_list for d in required):
            errs.append({
                "rule_id": f"MED_SERVICE_{svc}_MISSING_REQUIRED_DIAG",
                "category": "medical",
                "message": f"Service {svc} requires one of diagnoses: {', '.join(required)} but none present.",
                "recommendation": f"Include required diagnosis code(s): {', '.join(required)} when billing {svc}."
            })

    # 9) Mutually exclusive diagnosis checks
    for a_set, b_set in mutual_exclusive:
        if any(a in diag_list for a in a_set) and any(b in diag_list for b in b_set):
            errs.append({
                "rule_id": f"MED_MUTUAL_{'_'.join(list(a_set)[:1])}_{'_'.join(list(b_set)[:1])}",
                "category": "medical",
                "message": f"Mutually exclusive diagnoses present: {', '.join(a_set)} cannot co-exist with {', '.join(b_set)}.",
                "recommendation": "Review diagnosis list and remove incorrect / conflicting diagnosis codes."
            })

    # Done
    return errs
