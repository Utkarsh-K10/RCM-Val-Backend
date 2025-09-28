# app/pipeline/parser.py
import pdfplumber
import re
import json
from typing import List, Dict

def extract_text(pdf_path: str) -> str:
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                text += t + "\n"
    return text

def tech_pdf_to_rules(pdf_path: str) -> List[Dict]:
    text = extract_text(pdf_path)
    rules = []

    # Example: find paid thresholds "AED 250", "AED 500" etc.
    for m in re.finditer(r'(?:paid(?: amount)?\s*(?:>\s*|greater than\s*)AED\s*([0-9,]+))', text, re.I):
        val = int(m.group(1).replace(',', ''))
        rules.append({
            "rule_id": f"TECH_PAID_GT_{val}",
            "category": "technical",
            "field": "paid_amount_aed",
            "op": ">",
            "value": val,
            "message": f"Paid amount > AED {val} requires prior approval.",
            "recommendation": "Request prior approval and attach approval number.",
            "enabled": True
        })

    # Example: find service codes like SRV1234
    for m in re.finditer(r'\b(SRV[0-9]{3,5})\b.*?(?:requires|require|needs)\s+(?:prior\s+approval|approval)', text, re.I | re.S):
        code = m.group(1)
        rules.append({
            "rule_id": f"TECH_{code}_REQUIRES_APPROVAL",
            "category": "technical",
            "field": "service_code",
            "op": "==",
            "value": code,
            "message": f"Service {code} requires prior approval.",
            "recommendation": "Attach approval number and re-submit.",
            "enabled": True
        })

    # If nothing found, return an empty list so existing default rules are used
    return rules

def med_pdf_to_rules(pdf_path: str) -> List[Dict]:
    text = extract_text(pdf_path)
    rules = []

    # Example: service requiring diagnosis mapping (heuristic)
    # Look for patterns "Service SRVxxxx requires diagnosis E11.9"
    for m in re.finditer(r'\b(SRV[0-9]{3,5})\b[^\n\r]{0,80}?(?:requires|requires diagnosis|requires dx)\s*([A-Z0-9.\s,]+)', text, re.I):
        svc = m.group(1)
        dxs = re.findall(r'[A-Z]\d{1,2}\.?[0-9A-Z]*', m.group(2))
        if dxs:
            rules.append({
                "rule_id": f"MED_{svc}_REQUIRES_DX",
                "category": "medical",
                "field": "service_code",
                "op": "==",
                "value": svc,
                "message": f"Service {svc} requires diagnosis {', '.join(dxs)}.",
                "recommendation": f"Add diagnosis {', '.join(dxs)} if clinically indicated.",
                "enabled": True
            })

    # Mutually exclusive diag heuristics — look for "cannot co-exist" phrases
    for m in re.finditer(r'([A-Z0-9.\s,]+?)\s+cannot co-?exist with\s+([A-Z0-9.\s,]+)', text, re.I):
        a = re.findall(r'[A-Z]\d{1,2}\.?[0-9A-Z]*', m.group(1))
        b = re.findall(r'[A-Z]\d{1,2}\.?[0-9A-Z]*', m.group(2))
        if a and b:
            rules.append({
                "rule_id": f"MED_MUTUAL_{a[0]}_{b[0]}",
                "category": "medical",
                "field": "diagnosis_codes",
                "op": "conflict_pair",
                "value": {"a": a, "b": b},
                "message": f"Diagnoses {a} cannot co-exist with {b}.",
                "recommendation": "Review diagnosis list and correct.",
                "enabled": True
            })

    return rules

def pdf_to_rules(tech_path: str, med_path: str) -> Dict[str, List[Dict]]:
    tech_rules = tech_pdf_to_rules(tech_path) if tech_path.lower().endswith(".pdf") else []
    med_rules = med_pdf_to_rules(med_path) if med_path.lower().endswith(".pdf") else []
    return {"technical": tech_rules, "medical": med_rules}

def save_rules_json(rules: Dict[str, List[Dict]], tenant: str):
    with open(f"app/rules/{tenant}_technical.json", "w", encoding="utf-8") as f:
        json.dump(rules.get("technical", []), f, indent=2)
    with open(f"app/rules/{tenant}_medical.json", "w", encoding="utf-8") as f:
        json.dump(rules.get("medical", []), f, indent=2)
