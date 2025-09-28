import pytest
from app.pipeline.static_eval import evaluate_claim, load_rules

def test_paid_amount_rule(tmp_path):
    rules = {
        "technical": [
            {
                "rule_id": "T001",
                "field": "paid_amount_aed",
                "op": ">",
                "value": 250,
                "conditions": [{"field": "approval_number", "op": "is_null"}],
                "message": "Paid amount > 250 but no approval",
                "recommendation": "Provide approval number",
                "enabled": True,
            }
        ],
        "medical": []
    }

    claim = {"paid_amount_aed": 300, "approval_number": None}
    errors = evaluate_claim(claim, rules)
    assert len(errors) == 1
    assert errors[0]["rule_id"] == "T001"
