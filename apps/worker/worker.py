#!/usr/bin/env python3
"""RQ Worker for processing jobs"""

import sys
import os

# Add paths for imports
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "api"))
sys.path.insert(0, os.path.join(base_dir, "..", "packages", "core"))

from rq import Worker, Connection  # noqa: E402
import redis  # noqa: E402

if __name__ == "__main__":
    # RQ works better with decode_responses=False for binary serialization
    redis_conn = redis.Redis(host="localhost", port=6379, db=0, decode_responses=False)

    with Connection(redis_conn):
        worker = Worker(["jobs"])
        print("Worker started, waiting for jobs...")
        worker.work()
