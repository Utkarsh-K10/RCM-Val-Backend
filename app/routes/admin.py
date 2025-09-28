from fastapi import APIRouter
import datetime
from ..pipeline.queue import redis_conn
from rq.job import Job

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat()}

@router.get("/job/{job_id}")
def job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        return {"id": job.id, "status": job.get_status(), "result": job.result}
    except Exception as e:
        return {"error": str(e)}
