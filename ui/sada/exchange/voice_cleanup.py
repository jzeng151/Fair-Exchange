"""Completion cleanup for voice notes whose request stopped waiting (deploy/template.yaml: VoiceCleanup).

An EventBridge rule sends each finished `fx-ui-voice-*` Transcribe job here. If the request left the "abandoned"
marker (see aws_tools.transcribe), the audio, transcript and marker are deleted, and the job too. Otherwise the request
is still reading the transcript and deletes everything itself, so this does nothing.

Runs as its own small Lambda from the same code package, without Django.
"""
from __future__ import annotations

import os
import re

from exchange.aws_tools import ABANDONED, VOICE_JOB_PREFIX, delete_voice_files

_VID = re.compile(r"^[0-9a-f]{32}$")


def _clients():
    import boto3
    return boto3.client("s3"), boto3.client("transcribe")


def handler(event, _context, bucket: str | None = None):
    job = ((event or {}).get("detail") or {}).get("TranscriptionJobName") or ""
    vid = job[len(VOICE_JOB_PREFIX):] if job.startswith(VOICE_JOB_PREFIX) else ""
    if not _VID.match(vid):
        return
    bucket = bucket or os.environ["UPLOADS_BUCKET"]
    s3, tr = _clients()
    try:
        s3.head_object(Bucket=bucket, Key=f"voice/{vid}/{ABANDONED}")
    except Exception:
        return  # no marker: the request is still waiting and cleans up itself
    delete_voice_files(s3, tr, bucket, vid)
