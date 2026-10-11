"""210.thumbnailer - image resizing.

Adapted from the SeBS benchmark 210.thumbnailer (Copik et al., 2021). The function is
CPU and memory bound, so lowering MemorySize or Timeout (fault F2) produces timeouts and
higher duration.
"""
import io
import json
import os
import time
import uuid

import boto3
from PIL import Image

S3 = boto3.client("s3")
INPUT_BUCKET = os.environ["INPUT_BUCKET"]
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def resize(image_bytes, width, height):
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.thumbnail((width, height))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=85)
        return out.getvalue()


def handler(event, context):
    key = event["key"]
    width = int(event.get("width", 200))
    height = int(event.get("height", 200))

    begin = time.time()
    image = S3.get_object(Bucket=INPUT_BUCKET, Key=key)["Body"].read()
    download_time = time.time() - begin

    begin = time.time()
    thumbnail = resize(image, width, height)
    compute_time = time.time() - begin

    out_key = f"thumbnailer/{uuid.uuid4()}-{os.path.basename(key)}"
    S3.put_object(Bucket=OUTPUT_BUCKET, Key=out_key, Body=thumbnail, ContentType="image/jpeg")

    return {
        "statusCode": 200,
        "body": json.dumps({"key": out_key, "download_time_s": round(download_time, 4),
                            "compute_time_s": round(compute_time, 4)}),
    }
