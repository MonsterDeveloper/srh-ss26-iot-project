from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import Settings

STREAMS = {
    "motion": {"filename": "motion.csv", "content_type": "text/csv", "limit": 10 * 1024 * 1024},
    "audio": {"filename": "audio.wav", "content_type": "audio/wav", "limit": 64 * 1024 * 1024},
    "video": {"filename": "video.h264", "content_type": "video/h264", "limit": 256 * 1024 * 1024},
}


class ObjectStorage:
    def __init__(self, settings: Settings):
        base = dict(region_name=settings.s3_region, aws_access_key_id=settings.s3_access_key_id, aws_secret_access_key=settings.s3_secret_access_key, config=Config(signature_version="s3v4"))
        self.bucket = settings.s3_bucket
        self.ttl = settings.presigned_url_ttl_seconds
        self.get_ttl = settings.presigned_get_url_ttl_seconds
        self.public = boto3.client("s3", endpoint_url=settings.s3_public_endpoint, **base)
        self.internal = boto3.client("s3", endpoint_url=settings.s3_internal_endpoint, **base)

    @staticmethod
    def manifest(experiment_id: str, exercise_id: str, recording_id: str) -> dict:
        prefix = f"experiments/{experiment_id}/exercises/{exercise_id}/recordings/{recording_id}"
        return {stream: {"key": f"{prefix}/{spec['filename']}", "contentType": spec["content_type"], "maxBytes": spec["limit"]} for stream, spec in STREAMS.items()}

    def presigned_put_urls(self, manifest: dict) -> dict:
        return {stream: self.public.generate_presigned_url("put_object", Params={"Bucket": self.bucket, "Key": item["key"], "ContentType": item["contentType"]}, ExpiresIn=self.ttl, HttpMethod="PUT") for stream, item in manifest.items()}

    def ensure_bucket_cors(self, origins: list[str]) -> None:
        """Create the private bucket when needed and allow only browser PUTs from the API allowlist."""
        try:
            self.internal.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.internal.create_bucket(Bucket=self.bucket)
        self.internal.put_bucket_cors(Bucket=self.bucket, CORSConfiguration={"CORSRules": [{"AllowedOrigins": origins, "AllowedMethods": ["GET", "HEAD", "PUT"], "AllowedHeaders": ["Content-Type", "Range"], "ExposeHeaders": ["ETag", "Accept-Ranges", "Content-Length", "Content-Range"], "MaxAgeSeconds": 900}]})

    def head_all(self, manifest: dict) -> dict:
        objects = {}
        for stream, item in manifest.items():
            try:
                head = self.internal.head_object(Bucket=self.bucket, Key=item["key"])
            except (ClientError, BotoCoreError) as exc:
                raise ValueError(f"Missing uploaded {stream} object") from exc
            content_type = head.get("ContentType", "").split(";", 1)[0].lower()
            if content_type != item["contentType"] or head.get("ContentLength", 0) > item["maxBytes"]:
                raise ValueError(f"Invalid {stream} object metadata")
            objects[stream] = head
        return objects

    def download_all(self, manifest: dict, directory: Path) -> dict[str, str]:
        paths: dict[str, str] = {}
        for stream, item in manifest.items():
            target = directory / STREAMS[stream]["filename"]
            self.internal.download_file(self.bucket, item["key"], str(target))
            paths[stream] = str(target)
        return paths

    def delete_manifest(self, manifest: dict) -> None:
        if not manifest:
            return
        try:
            response = self.internal.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": item["key"]} for item in manifest.values()], "Quiet": True})
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError("Could not delete recording objects") from exc
        if response.get("Errors"):
            raise RuntimeError("Could not delete recording objects")

    def upload_artifact(self, key: str, path: Path, content_type: str) -> dict:
        self.internal.upload_file(str(path), self.bucket, key, ExtraArgs={"ContentType": content_type})
        head = self.internal.head_object(Bucket=self.bucket, Key=key)
        return {"key": key, "contentType": content_type, "size": int(head["ContentLength"])}

    def delete_artifacts(self, artifacts: dict) -> None:
        self.delete_manifest({key: value for key, value in artifacts.items() if isinstance(value, dict) and value.get("key")})

    def media_link(self, item: dict, filename: str) -> dict:
        try:
            head = self.internal.head_object(Bucket=self.bucket, Key=item["key"])
        except (ClientError, BotoCoreError) as exc:
            raise ValueError("Media object is unavailable") from exc
        content_type = item.get("contentType") or head.get("ContentType") or "application/octet-stream"
        disposition = f'attachment; filename="{filename}"'
        url = self.public.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": item["key"], "ResponseContentType": content_type, "ResponseContentDisposition": disposition},
            ExpiresIn=self.get_ttl,
            HttpMethod="GET",
        )
        return {"url": url, "expiry": datetime.now(timezone.utc) + timedelta(seconds=self.get_ttl), "filename": filename, "contentType": content_type, "size": int(head["ContentLength"])}
