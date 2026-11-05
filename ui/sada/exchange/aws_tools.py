"""AWS services behind the sample UI's extras (all optional; each falls back to the browser or a note):

- Amazon Polly: "Listen" reads an answer aloud with a neural voice in the chat language.
- Amazon Transcribe: the mic records a voice note, which is uploaded to S3 and transcribed into the message box.
- Amazon Translate: FEX's real answers are translated when the producer picks another language in the menu.
- Amazon Bedrock (Claude): an attached photo or document is read, and a short factual description goes to FEX with
  the producer's message, so FEX's normal grounding, scope and PII checks still apply to it.

Audio, transcripts and attachments live in UPLOADS_BUCKET (private, 1-day lifecycle); audio and transcripts are
deleted as soon as the transcript is read.
"""
from __future__ import annotations

import json
import time
import uuid

from django.conf import settings

# Polly neural voices per UI language (Kiswahili has no Polly voice: the browser voice is used instead).
POLLY_VOICES = {
    "en": ("Joanna", "en-US"),
    "es": ("Lupe", "es-US"),
    "fr": ("Lea", "fr-FR"),
    "pt": ("Camila", "pt-BR"),
    "hi": ("Kajal", "hi-IN"),
}
TRANSCRIBE_LANGUAGES = {"en": "en-US", "es": "es-US", "fr": "fr-FR", "pt": "pt-BR", "hi": "hi-IN", "sw": "sw-KE"}
TRANSLATE_CODES = {"en": "en", "es": "es", "fr": "fr", "pt": "pt", "sw": "sw", "hi": "hi"}
_MEDIA_FORMATS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/mpeg": "mp3", "audio/wav": "wav"}
_IMAGE_FORMATS = {"image/png": "png", "image/jpeg": "jpeg", "image/gif": "gif", "image/webp": "webp"}
_DOC_FORMATS = {
    "application/pdf": "pdf", "text/plain": "txt", "text/csv": "csv", "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _client(name: str):
    import boto3
    return boto3.client(name, region_name=settings.AWS_REGION)


def bucket() -> str:
    return getattr(settings, "UPLOADS_BUCKET", "")


# ---------------------------------------------------------------------------------------------- Polly

def speak(text: str, language: str) -> bytes | None:
    """MP3 of the text in a neural voice, or None when the language has no Polly voice."""
    voice = POLLY_VOICES.get(language)
    if not voice or not text.strip():
        return None
    out = _client("polly").synthesize_speech(
        Text=text[:2900], OutputFormat="mp3", VoiceId=voice[0], LanguageCode=voice[1], Engine="neural")
    return out["AudioStream"].read()


# ----------------------------------------------------------------------------------------- Transcribe

def transcribe(audio: bytes, content_type: str, language: str) -> str:
    """Upload a voice note, transcribe it (batch), delete the audio and transcript, and return the text."""
    fmt = _MEDIA_FORMATS.get(content_type.split(";")[0].strip(), "webm")
    vid = uuid.uuid4().hex
    s3, tr = _client("s3"), _client("transcribe")
    audio_key, out_key, job = f"voice/{vid}/audio.{fmt}", f"voice/{vid}/transcript.json", f"fx-ui-voice-{vid}"
    s3.put_object(Bucket=bucket(), Key=audio_key, Body=audio, ContentType=content_type)
    try:
        tr.start_transcription_job(
            TranscriptionJobName=job, MediaFormat=fmt, Media={"MediaFileUri": f"s3://{bucket()}/{audio_key}"},
            OutputBucketName=bucket(), OutputKey=out_key,
            LanguageCode=TRANSCRIBE_LANGUAGES.get(language, "en-US"))
        deadline = time.time() + 120
        while time.time() < deadline:
            status = tr.get_transcription_job(TranscriptionJobName=job)["TranscriptionJob"]["TranscriptionJobStatus"]
            if status == "COMPLETED":
                body = json.loads(s3.get_object(Bucket=bucket(), Key=out_key)["Body"].read())
                return body["results"]["transcripts"][0]["transcript"].strip()
            if status == "FAILED":
                raise RuntimeError("transcription failed")
            time.sleep(1.5)
        raise RuntimeError("transcription timed out")
    finally:
        s3.delete_objects(Bucket=bucket(), Delete={"Objects": [{"Key": audio_key}, {"Key": out_key}], "Quiet": True})
        try:
            tr.delete_transcription_job(TranscriptionJobName=job)
        except Exception:
            pass


# ------------------------------------------------------------------------------------------ Translate

def translate(text: str, target: str, source: str = "auto") -> str:
    code = TRANSLATE_CODES.get(target)
    if not code or not text.strip():
        return text
    out = _client("translate").translate_text(Text=text[:9000], SourceLanguageCode=source, TargetLanguageCode=code)
    return out["TranslatedText"]


# ----------------------------------------------------------------------------- Bedrock (attachments)

_READ_PROMPT = (
    "A Fair Trade producer attached this file to describe a challenge on their farm or in their organization. "
    "In one or two short sentences, state factually what it shows that is relevant to farming, water, crops, "
    "land, labour or prices. Do not name or describe any person, and do not include names, phone numbers, IDs "
    "or addresses. If nothing relevant is visible, say so. Reply in {language}."
)


def read_attachment(key: str, content_type: str, language_name: str) -> str | None:
    """A short factual description of an uploaded photo or document, read with Claude on Amazon Bedrock."""
    content_type = (content_type or "").split(";")[0].strip()
    data = _client("s3").get_object(Bucket=bucket(), Key=key)["Body"].read()
    if content_type in _IMAGE_FORMATS:
        block = {"image": {"format": _IMAGE_FORMATS[content_type], "source": {"bytes": data}}}
    elif content_type in _DOC_FORMATS:
        block = {"document": {"format": _DOC_FORMATS[content_type], "name": "attachment", "source": {"bytes": data}}}
    else:
        return None
    out = _client("bedrock-runtime").converse(
        modelId=settings.VISION_MODEL_ID,
        messages=[{"role": "user", "content": [block, {"text": _READ_PROMPT.format(language=language_name)}]}],
        inferenceConfig={"maxTokens": 200},
    )
    texts = [b["text"] for b in out["output"]["message"]["content"] if "text" in b]
    return " ".join(texts).strip() or None
