#!/usr/bin/env python
"""Upload partitioned JSONL logs to S3 (s3://<bucket>/logs/dt=YYYY-MM-DD/<file>).

Server-side encryption is always requested; files already present with the same size are
skipped, so re-runs are idempotent.

    python scripts/upload_logs_s3.py --bucket my-bucket [--log-dir logs] [--kms-key-id ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401
from rqg.config import get_settings


def upload_logs(
    log_dir: Path,
    bucket: str,
    prefix: str = "logs",
    s3: Any = None,
    kms_key_id: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    if s3 is None:
        import boto3

        s3 = boto3.client("s3")
    keys: list[str] = []
    for f in sorted(Path(log_dir).glob("dt=*/*.jsonl")):
        key = f"{prefix}/{f.parent.name}/{f.name}"
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
            if head["ContentLength"] == f.stat().st_size:
                continue
        except s3.exceptions.ClientError:
            pass
        keys.append(key)
        if dry_run:
            continue
        extra = (
            {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": kms_key_id}
            if kms_key_id
            else {"ServerSideEncryption": "AES256"}
        )
        s3.upload_file(
            str(f), bucket, key, ExtraArgs={**extra, "ContentType": "application/x-ndjson"}
        )
    return keys


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=os.getenv("RQG_S3_BUCKET"))
    ap.add_argument("--log-dir", type=Path, default=s.log_dir)
    ap.add_argument("--prefix", default="logs")
    ap.add_argument("--kms-key-id", default=os.getenv("RQG_KMS_KEY_ID"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not a.bucket:
        print("set --bucket or RQG_S3_BUCKET")
        return 2
    keys = upload_logs(a.log_dir, a.bucket, a.prefix, kms_key_id=a.kms_key_id, dry_run=a.dry_run)
    print(
        f"{'would upload' if a.dry_run else 'uploaded'} {len(keys)} file(s) to s3://{a.bucket}/{a.prefix}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
