"""S3-backed attachments: the browser asks for a presigned PUT URL, uploads directly to S3, then
sends the object key with its chat message. Keeps large files off the Django process.

When UPLOADS_BUCKET is unset the feature is off and the UI treats attachments as local-only chips.
Uploads expire via the bucket lifecycle rule (7 days) to keep the sandbox clean.
"""
from __future__ import annotations

import uuid
import re

from django.conf import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB cap per file
_ALLOWED = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "application/pdf", "text/plain", "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def enabled() -> bool:
    return bool(getattr(settings, "UPLOADS_BUCKET", ""))


def _client():
    import boto3
    from botocore.config import Config
    # Regional virtual-host endpoint + SigV4 so presigned PUTs don't get a 307 redirect.
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        endpoint_url=f"https://s3.{settings.AWS_REGION}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def presign_put(filename: str, content_type: str, size: int) -> dict | None:
    """A presigned PUT URL for a single file, or None if rejected/disabled."""
    if not enabled():
        return None
    if content_type not in _ALLOWED:
        return {"error": "That file type isn't allowed."}
    if size and size > _MAX_BYTES:
        return {"error": "That file is larger than the 10 MB limit."}
    safe = _SAFE.sub("_", filename or "file")[-80:]
    key = f"uploads/{uuid.uuid4().hex}/{safe}"
    url = _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.UPLOADS_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,
    )
    return {"url": url, "key": key, "bucket": settings.UPLOADS_BUCKET}
