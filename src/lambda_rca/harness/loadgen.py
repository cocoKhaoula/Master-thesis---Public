"""Constant-rate load generator (Section 3.4).

Invokes every function synchronously at `requests_per_minute`, sent in bursts of
`burst_concurrency` concurrent requests so that reserved concurrency of 1 (F4) throttles.
Run it in its own terminal for the whole campaign: `lambda-rca loadgen`.
"""
from __future__ import annotations

import io
import json
import logging
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from botocore.config import Config as BotoConfig

from ..aws import resolve_functions, session, stack_outputs
from ..config import Config

log = logging.getLogger(__name__)

SEED_IMAGE_KEY = "thumbnailer/input.jpg"
SEED_UPLOAD_KEY = "uploader/payload.bin"
COMPRESSION_PREFIX = "compression/"


def seed_inputs(cfg: Config) -> None:
    """Upload the input objects the functions read: a large JPEG for the thumbnailer,
    a payload for the uploader, and a set of files for compression."""
    from PIL import Image  # only needed here

    s3 = session(cfg, "harness").client("s3")
    bucket = stack_outputs(cfg)["InputBucketName"]
    rng = random.Random(0)

    img = Image.effect_mandelbrot((4000, 3000), (-2.0, -1.2, 1.0, 1.2), 100).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    s3.put_object(Bucket=bucket, Key=SEED_IMAGE_KEY, Body=buf.getvalue())

    s3.put_object(Bucket=bucket, Key=SEED_UPLOAD_KEY, Body=rng.randbytes(512 * 1024))

    words = [f"word{i}" for i in range(2000)]
    for i in range(8):
        text = " ".join(rng.choice(words) for _ in range(400_000))
        s3.put_object(Bucket=bucket, Key=f"{COMPRESSION_PREFIX}file{i}.txt", Body=text.encode())
    log.info("seeded inputs in %s", bucket)


class LoadGenerator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        s = session(cfg, "harness")
        # No client-side retries: a throttled or failed request must show up as such.
        self.lam = s.client("lambda", config=BotoConfig(retries={"max_attempts": 1, "mode": "standard"},
                                                         read_timeout=120))
        self.s3 = s.client("s3")
        self.functions = resolve_functions(cfg, "harness")
        self.input_bucket = stack_outputs(cfg)["InputBucketName"]
        self.stop = threading.Event()
        self.stats: dict[str, dict[str, int]] = {k: {"ok": 0, "error": 0} for k in self.functions}

    def payload(self, key: str) -> dict:
        if key == "crud-api":
            cart = str(uuid.uuid4())
            pid = f"p{random.randint(1, 50)}"
            return {"cart_id": cart, "requests": [
                {"route": "PUT /cart", "body": {"product_id": pid, "name": "item", "price": 9.99, "quantity": 2}},
                {"route": "GET /cart/{id}", "body": {"product_id": pid}},
                {"route": "GET /cart"},
            ]}
        if key == "uploader":
            url = self.s3.generate_presigned_url("get_object", ExpiresIn=600,
                                                 Params={"Bucket": self.input_bucket, "Key": SEED_UPLOAD_KEY})
            return {"url": url}
        if key == "thumbnailer":
            return {"key": SEED_IMAGE_KEY, "width": 200, "height": 200}
        if key == "compression":
            return {"prefix": COMPRESSION_PREFIX}
        raise KeyError(key)

    def invoke(self, key: str) -> None:
        try:
            resp = self.lam.invoke(FunctionName=self.functions[key].function_name,
                                   Payload=json.dumps(self.payload(key)).encode())
            ok = "FunctionError" not in resp
        except Exception as e:  # throttling, timeouts
            log.debug("%s: %s", key, e)
            ok = False
        self.stats[key]["ok" if ok else "error"] += 1

    def run(self, minutes: float | None = None) -> None:
        rpm = self.cfg["load"]["requests_per_minute"]
        burst = self.cfg["load"]["burst_concurrency"]
        interval = 60.0 * burst / rpm
        end = time.time() + minutes * 60 if minutes else None
        with ThreadPoolExecutor(max_workers=len(self.functions) * burst * 4) as pool:
            next_t = time.time()
            last_report = time.time()
            while not self.stop.is_set() and (end is None or time.time() < end):
                for key in self.functions:
                    for _ in range(burst):
                        pool.submit(self.invoke, key)
                next_t += interval
                if time.time() - last_report > 60:
                    log.info("load: %s", self.stats)
                    last_report = time.time()
                time.sleep(max(0.0, next_t - time.time()))
