# app/pipeline/queue.py
import os
import redis
from rq import Queue

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = redis.from_url(redis_url)
queue = Queue("validation", connection=redis_conn)
