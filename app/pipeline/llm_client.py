# app/pipeline/llm_client.py
import os
import requests

HF_API_KEY = os.getenv("HF_INFERENCE_API_KEY")
HF_MODEL = os.getenv("HF_MODEL", "google/flan-t5-small")
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
HEADERS = {"Authorization": f"Bearer {HF_API_KEY}"} if HF_API_KEY else {}

def _build_prompt(claim, errors):
    bullets = "\n".join([f"- {e['message']}" for e in errors])
    prompt = f"""
You are a claims adjudication assistant. Given this claim (sensitive IDs masked):
service_code={claim.get('service_code')}, diagnosis_codes={claim.get('diagnosis_codes')}, paid_amount={claim.get('paid_amount_aed')}, approval_number={claim.get('approval_number')}
Triggered errors:
{bullets}

Task:
1) For each triggered error, output one short bullet explaining why it happened (plain English).
2) Provide one concise recommended action to fix the claim.

Return JSON: {{ "bullets": ["...","..."], "recommendation": "..." }}
"""
    return prompt

def explain_with_llm(claim, errors):
    # If no HF key, deterministic fallback
    if not HF_API_KEY:
        return {
            "bullets": [e["message"] for e in errors],
            "recommendation": "; ".join({e["recommendation"] for e in errors})
        }
    try:
        payload = {"inputs": _build_prompt(claim, errors), "parameters":{"max_new_tokens":120}}
        resp = requests.post(HF_URL, headers=HEADERS, json=payload, timeout=20)
        if resp.status_code == 200:
            output = resp.json()
            # HF sometimes returns [{"generated_text": "..."}]
            if isinstance(output, list) and "generated_text" in output[0]:
                text = output[0]["generated_text"]
                # naive attempt: split into bullets by newline
                bullets = [l.strip("- ").strip() for l in text.splitlines() if l.strip()]
                return {"bullets": bullets or [e["message"] for e in errors],
                        "recommendation": bullets[-1] if bullets else "; ".join({e["recommendation"] for e in errors})}
        # fallback
        return {"bullets": [e["message"] for e in errors], "recommendation": "; ".join({e["recommendation"] for e in errors})}
    except Exception:
        return {"bullets": [e["message"] for e in errors], "recommendation": "; ".join({e["recommendation"] for e in errors})}
