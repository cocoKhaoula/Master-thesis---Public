"""311.compression - compresses a set of files into one archive.

Adapted from the SeBS benchmark 311.compression (Copik et al., 2021). Each invocation
runs for several seconds, so a lowered Timeout (F2) causes timeouts and overlapping
invocations make reserved concurrency of 1 (F4) produce throttles.
"""
import io
import json
import os
import time
import uuid
import zipfile

import boto3

S3 = boto3.client("s3")
INPUT_BUCKET = os.environ["INPUT_BUCKET"]
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def handler(event, context):
    prefix = event.get("prefix", "compression/")

    begin = time.time()
    keys = [o["Key"] for o in S3.list_objects_v2(Bucket=INPUT_BUCKET, Prefix=prefix).get("Contents", [])]
    files = {k: S3.get_object(Bucket=INPUT_BUCKET, Key=k)["Body"].read() for k in keys}
    download_time = time.time() - begin

    begin = time.time()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for key, data in files.items():
            zf.writestr(os.path.basename(key), data)
    compute_time = time.time() - begin

    out_key = f"compression/{uuid.uuid4()}.zip"
    S3.put_object(Bucket=OUTPUT_BUCKET, Key=out_key, Body=archive.getvalue())

    return {
        "statusCode": 200,
        "body": json.dumps({"key": out_key, "files": len(files),
                            "archive_bytes": archive.getbuffer().nbytes,
                            "download_time_s": round(download_time, 4),
                            "compute_time_s": round(compute_time, 4)}),
    }
