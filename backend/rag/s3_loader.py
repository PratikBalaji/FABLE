"""Load documents from S3 for RAG ingestion."""
from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from ..core.config import settings
from .pipeline import vector_store


def ingest_from_s3(prefix: str = "", bucket: str | None = None) -> int:
    """Download and ingest all text files under an S3 prefix."""
    bucket = bucket or settings.s3_bucket
    s3 = boto3.client("s3", region_name=settings.aws_region)

    total_chunks = 0
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith((".txt", ".md", ".py", ".json", ".csv")):
                continue
            try:
                resp = s3.get_object(Bucket=bucket, Key=key)
                text = resp["Body"].read().decode("utf-8", errors="ignore")
                n = vector_store.ingest(text, metadata={"source": f"s3://{bucket}/{key}"})
                total_chunks += n
                print(f"Ingested {n} chunks from s3://{bucket}/{key}")
            except ClientError as e:
                print(f"Warning: could not read {key}: {e}")

    print(f"Total chunks ingested from S3: {total_chunks}")
    return total_chunks


def upload_feedback_to_s3(bucket: str | None = None) -> str:
    """Upload the feedback JSONL to S3 for persistence."""
    bucket = bucket or settings.s3_bucket
    s3 = boto3.client("s3", region_name=settings.aws_region)
    key = "feedback/feedback.jsonl"
    s3.upload_file(settings.feedback_db_path, bucket, key)
    return f"s3://{bucket}/{key}"
