"""R2Store — Cloudflare R2 storage for MWGym experiment logs.

Stores experiment results, reviews, and evolution traces on R2
so they persist across runs and are accessible from any worker.

Credentials loaded from /root/.r2-credentials or env vars:
  R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET, R2_BUCKET
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config


# Default bucket name from credentials
_DEFAULT_BUCKET = "tiro6590"
_CREDENTIALS_PATH = Path("/root/.r2-credentials")


def _load_credentials() -> dict:
    """Load R2 credentials from file or env vars."""
    creds = {}
    if _CREDENTIALS_PATH.exists():
        for line in _CREDENTIALS_PATH.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()

    return {
        "account_id": creds.get("R2_ACCOUNT_ID") or os.environ.get("R2_ACCOUNT_ID", ""),
        "access_key": creds.get("R2_ACCESS_KEY") or os.environ.get("R2_ACCESS_KEY", ""),
        "secret_key": creds.get("R2_SECRET") or os.environ.get("R2_SECRET", ""),
        "bucket": creds.get("R2_BUCKET") or os.environ.get("R2_BUCKET", _DEFAULT_BUCKET),
    }


class R2Store:
    """S3-compatible storage for experiment artifacts."""

    PREFIX = "mwgym/"

    def __init__(self, bucket: str = ""):
        creds = _load_credentials()
        self.bucket = bucket or creds["bucket"]
        self.endpoint = f"https://{creds['account_id']}.r2.cloudflarestorage.com"
        self.s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=creds["access_key"],
            aws_secret_access_key=creds["secret_key"],
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

    def _key(self, path: str) -> str:
        """Prefix all keys with mwgym/."""
        return f"{self.PREFIX}{path}"

    def upload_log(self, local_path: Path, experiment_name: str = "") -> str:
        """Upload an experiment log to R2. Returns the R2 key."""
        if not local_path.exists():
            raise FileNotFoundError(f"{local_path} not found")

        data = local_path.read_text()
        # Extract experiment name from JSON if not provided
        if not experiment_name:
            try:
                exp = json.loads(data)
                experiment_name = exp.get("run_id", local_path.stem)
            except (json.JSONDecodeError, KeyError):
                experiment_name = local_path.stem

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        key = self._key(f"logs/{experiment_name}/{ts}-{local_path.name}")
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data.encode(),
            ContentType="application/json",
        )
        return key

    def upload_review(self, local_path: Path) -> str:
        """Upload a review markdown to R2."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        key = self._key(f"reviews/{ts}-{local_path.name}")
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=local_path.read_bytes(),
            ContentType="text/markdown",
        )
        return key

    def list_logs(self, limit: int = 50) -> list[dict]:
        """List experiment logs on R2."""
        paginator = self.s3.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{self.PREFIX}logs/"):
            for obj in page.get("Contents", []):
                keys.append({"key": obj["Key"], "size": obj["Size"], "last_modified": obj["LastModified"]})
                if len(keys) >= limit:
                    break
            if len(keys) >= limit:
                break
        return sorted(keys, key=lambda x: x["last_modified"], reverse=True)

    def download_log(self, key: str, local_dir: Path) -> Path:
        """Download a log from R2 to local directory."""
        local_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(key).name
        local_path = local_dir / filename
        obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        local_path.write_bytes(obj["Body"].read())
        return local_path

    def sync_logs_to_local(self, local_dir: Path, limit: int = 20) -> list[Path]:
        """Download recent logs from R2 to local directory."""
        logs = self.list_logs(limit=limit)
        downloaded = []
        for log in logs:
            path = self.download_log(log["key"], local_dir)
            downloaded.append(path)
        return downloaded

    def health(self) -> dict:
        """Check R2 connectivity."""
        try:
            self.s3.head_bucket(Bucket=self.bucket)
            return {"ok": True, "bucket": self.bucket, "endpoint": self.endpoint}
        except Exception as e:
            return {"ok": False, "error": str(e), "bucket": self.bucket}
