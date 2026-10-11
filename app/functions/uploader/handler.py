"""120.uploader - downloads a file from a URL and stores it in S3.

Adapted from the SeBS benchmark 120.uploader (Copik et al., 2021). The destination
bucket is read from OUTPUT_BUCKET, which is the parameter changed by fault F3. Storing
the object requires s3:PutObject, which is removed by fault F1.
"""
import json
import os
import time
import urllib.request
import uuid

import boto3

S3 = boto3.client("s3")
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def handler(event, context):
    url = event["url"]
    key = f"uploader/{uuid.uuid4()}-{os.path.basename(url.split('?')[0]) or 'file'}"

    begin = time.time()
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = resp.read()
    download_time = time.time() - begin

    begin = time.time()
    S3.put_object(Bucket=OUTPUT_BUCKET, Key=key, Body=data)
    upload_time = time.time() - begin

    return {
        "statusCode": 200,
        "body": json.dumps({"key": key, "bytes": len(data),
                            "download_time_s": round(download_time, 4),
                            "upload_time_s": round(upload_time, 4)}),
    }
