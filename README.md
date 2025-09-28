
# 📊 Mini RCM Validation Engine

A production-minded prototype for validating healthcare claims data against **Technical** and **Medical adjudication rules**, enriched with **LLM-based explanations**.

The system ingests claims, applies static & AI rules, persists adjudication outcomes, and exposes them via API for a secure frontend.

---

## 🚀 Features

* **Frontend**

  * Secure login
  * File upload (Claims + Technical rules + Medical rules)
  * Results visualization:

    * Waterfall charts
    * Claims result table

* **Backend (FastAPI)**

  * API endpoints for ingestion, validation, metrics, health check
  * Master table persistence of all claims and adjudication results
  * Async job execution via Redis + RQ
  * Multi-tenant rule config (switch rule files without code changes)

* **Data Pipeline**

  * **Validation**: schema + missing field checks
  * **Static rule evaluation**: deterministic application of adjudication rules
  * **LLM rule evaluation**: optional Hugging Face API for explanations
  * **Metrics aggregation**: error category counts & paid amounts

---

## 🏗️ Project Structure

```
mini-rcm-backend/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── db.py                # DB engine + session
│   ├── models.py            # SQLAlchemy models
│   ├── db_utils.py          # upsert helpers
│   ├── routes/
│   │   ├── upload.py        # File upload + enqueue job
│   │   ├── claims.py        # Claims listing API
│   │   ├── metrics.py       # Metrics API
│   │   └── health.py        # Health check
│   ├── pipeline/
│   │   ├── static_eval.py   # Static rule engine
│   │   ├── llm_client.py    # LLM enrichment
│   │   ├── worker.py        # Background worker logic
│   │   └── queue.py         # Redis Queue config
│   ├── rules/               # Uploaded rule files (per tenant)
│   └── __init__.py
├── requirements.txt
├── Dockerfile
├── render.yaml              # Render service config (optional)
├── .gitignore
└── README.md
```

---

## 🗄️ Database Schema

### Master Claims Table

| Field              | Description                         |
| ------------------ | ----------------------------------- |
| claim_id           | Claim identifier                    |
| encounter_type     | INPATIENT / OUTPATIENT              |
| service_date       | Date of service                     |
| national_id        | Patient national ID                 |
| member_id          | Member identifier                   |
| facility_id        | Facility identifier                 |
| unique_id          | Composite ID (NID + MID + FID)      |
| diagnosis_codes    | List of diagnoses                   |
| service_code       | Service code                        |
| paid_amount_aed    | Claimed paid amount                 |
| approval_number    | Approval ref if any                 |
| status             | Validated / Not validated / Pending |
| error_type         | Technical / Medical / Both / None   |
| error_explanation  | Bullet list of rule failures        |
| recommended_action | Corrective steps                    |

### Claim Errors Table

Stores individual errors per claim (rule_id, message, recommendation).

### Claim Metrics Table

Aggregates claim counts & paid amounts by error category.

---

## ⚙️ Setup & Local Run

### 1. Clone repo & create virtualenv

```bash
git clone https://github.com/Utkarsh-K10/RCM-Val-Backend.git
cd RCM-Val-Backend
python -m venv venv
source venv/bin/activate   # (Linux/Mac)
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Redis locally (or use Upstash URL)

```bash
redis-server
```

### 4. Set environment variables

Create `.env`:

```env
DATABASE_URL=sqlite:///./claims.db
REDIS_URL=redis://127.0.0.1:6379
HF_INFERENCE_API_KEY=   # optional Hugging Face API key
```

### 5. Start FastAPI server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Start worker (new terminal)

```bash
rq worker validation
```

---

## 🔗 API Endpoints

### Upload Claims + Rules

`POST /api/upload`
Form-data:

* `claims` (Excel file)
* `technical` (rules file)
* `medical` (rules file)
* `tenant` (default: `default`)

### Check Job Status

`GET /admin/job/{job_id}`

### List Claims

`GET /api/claims`

### Get Metrics

`GET /api/metrics`

### Health Check

`GET /health`

---

## 🧪 Example Workflow

1. Upload claims + rule files → `/api/upload`
2. API saves claims as `Pending` and enqueues validation job
3. Worker validates claims (static + LLM), updates DB
4. Frontend (or Postman) queries:

   * `/api/claims` → full results per claim
   * `/api/metrics` → aggregated stats for charts

---

## 📌 Notes

* Rule engine parses Technical & Medical adjudication files dynamically.
* Multi-tenant: each tenant can upload its own rules (`app/rules/{tenant}_technical.json`).
* LLM client optional → system works without it (pure static rules).
* PostgreSQL in `DATABASE_URL`.
