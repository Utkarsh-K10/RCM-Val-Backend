# app/pipeline/queue.py
import os
import redis
from rq import Queue

# Get Redis URL from env (.env file)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# --- Quick fix for Upstash Redis SSL issues ---
# If using rediss:// (TLS) but system has no CA certs, disable strict SSL check
if redis_url.startswith("rediss://"):
    redis_conn = redis.from_url(redis_url, ssl_cert_reqs=None)
else:
    redis_conn = redis.from_url(redis_url)

# --- Proper fix for production (optional) ---
# Uncomment if you install certifi and want strict SSL verification
"""
import certifi
if redis_url.startswith("rediss://"):
    redis_conn = redis.from_url(
        redis_url,
        ssl_cert_reqs="required",
        ssl_ca_certs=certifi.where()
    )
else:
    redis_conn = redis.from_url(redis_url)
"""

# Create RQ queue
queue = Queue("validation", connection=redis_conn)
print(f"[Queue] Connected to Redis, queue 'validation' ready.")