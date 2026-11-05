"""Tests for the picker, the chat page and the Mock / Real API answer sources.

    .venv/bin/python manage.py test exchange

Real API tests use a fake chat API (fex_live._request patched) shaped like the real NDJSON events
(api/src/types/conversation-contract.ts), so they need no network.
"""
import json
from unittest import mock

from django.test import SimpleTestCase, override_settings

from . import fex_live

START = [{"type": "conversation", "conversationId": "c-1"},
         {"type": "step", "step": "intake", "language": "en", "seq": 1},
         {"type": "text", "text": "What has been most difficult lately?", "seq": 2},
         {"type": "actions", "allowed": ["end"], "language": "en", "seq": 3},
         {"type": "done", "seq": 4}]
PLAYBACK = [{"type": "step", "step": "playback", "language": "es", "seq": 1},
            {"type": "text", "text": "Esto es lo que entendí.", "seq": 2},
            {"type": "actions", "allowed": ["correct_playback", "end", "confirm_playback"], "language": "es", "seq": 3}]
ANSWER = [{"type": "text", "text": "Esto es lo que encontré.", "seq": 1},
          {"type": "claim", "section": "insights", "seq": 2,
           "claim": {"text": "Rain was 30% below normal.", "citation": {"source": "CHIRPS v2.0", "period": "2025", "standard_clause": "APS 2.4.2.a"}}},
          {"type": "claim", "section": "peer_examples", "seq": 3,
           "claim": {"text": "A peer group built tanks.", "citation": {"source": "Premium project PROJ-1", "standard_clause": "APS 2.4.2.a"}}},
          {"type": "step", "step": "consent", "language": "es", "seq": 4},
          {"type": "actions", "allowed": ["reopen_playback", "set_consent", "end"], "language": "es", "seq": 5}]
INVALID = [{"type": "error", "code": "invalid_action", "message": "That option isn't available right now.", "seq": 1}]
CLOSED = [{"type": "record_saved", "status": "completed", "version": 3, "consent_scope": "internal", "seq": 1},
          {"type": "step", "step": "closed", "language": "en", "seq": 2}]


class ToAnswerTests(SimpleTestCase):
    def test_each_claim_is_numbered_with_its_own_citation(self):
        a = fex_live.to_answer(ANSWER, "en")
        self.assertIn("• Rain was 30% below normal. [1]", a["text"])
        self.assertIn("• A peer group built tanks. [2]", a["text"])
        self.assertEqual([c["label"] for c in a["citations"]],
                         ["[1] CHIRPS v2.0 (2025) · Standard APS 2.4.2.a", "[2] Premium project PROJ-1 · Standard APS 2.4.2.a"])
        self.assertEqual([c["kind"] for c in a["citations"]], ["regional", "peer"])
        self.assertEqual(a["language"], "es")

    def test_aqueduct_citations_note_the_tnfd_tools_catalogue(self):
        events = [{"type": "claim", "section": "insights", "seq": 1, "claim": {"text": "Water stress is high.", "citation":
                   {"source": "WRI Aqueduct 4.0 projected water stress, Chiapas", "standard_clause": "FPS 5.1.2.c"}}}]
        label = fex_live.to_answer(events, "en")["citations"][0]["label"]
        self.assertTrue(label.endswith("· Listed in the TNFD Tools Catalogue"))
        self.assertNotIn("TNFD", fex_live.to_answer(ANSWER, "en")["citations"][0]["label"])

    def test_buttons_follow_allowed_actions_in_order_without_correct_playback(self):
        labels = [b["label"] for b in fex_live.to_answer(PLAYBACK, "en")["suggestions"]]
        self.assertEqual(labels, ["✓ Sí, es correcto", "Terminar la conversación"])
        consent = fex_live.to_answer(ANSWER, "en")["suggestions"]
        self.assertEqual([b["args"] for b in consent if b["action"] == "set_consent"],
                         [{"scope": "internal"}, {"scope": "internal_and_outward"}, {"scope": "declined"}])

    def test_closed_turn_says_so(self):
        a = fex_live.to_answer(CLOSED, "en")
        self.assertTrue(a["closed"])
        self.assertIn("✓ Saved: only Fair Trade USA can see it.", a["text"])


class PickerAndChatTests(SimpleTestCase):
    def test_picker_shows_three_producers_and_three_consumers(self):
        html = self.client.get("/").content.decode()
        self.assertEqual(html.count('class="persona-card"'), 6)
        self.assertIn("Pick a persona to chat", html)

    @override_settings(USE_LIVE_WEATHER=False)
    def test_chat_opens_in_persona_language_with_mock(self):
        html = self.client.get("/chat/prod-rice-ci/").content.decode()
        self.assertIn("Bonjour Fatou", html)
        self.assertIn(">MOCK<", html)
        self.assertIn("Sample weather", html)

    @override_settings(USE_LIVE_WEATHER=False)
    def test_mock_answer(self):
        self.client.get("/chat/prod-coffee-mx/")
        r = self.client.post("/api/chat", json.dumps({"message": "The rains came late", "persona_id": "prod-coffee-mx"}),
                             content_type="application/json")
        self.assertEqual(r.json()["source"], "mock")
        self.assertTrue(r.json()["citations"])


@override_settings(FEX_API_URL="http://fex.test", USE_LIVE_WEATHER=False)
@mock.patch("exchange.weather._fetch", side_effect=OSError("no network in tests"))
class RealApiTests(SimpleTestCase):
    def chat(self, message, action=None):
        return self.client.post("/api/chat", json.dumps({"message": message, "persona_id": "prod-coffee-co", "action": action}),
                                content_type="application/json").json()

    def test_full_conversation_through_the_chat_api(self, _weather):
        calls = []

        def fake(persona, method, path, body=None):
            calls.append((path, body))
            self.assertEqual(persona.fex_producer_id, "CFC19603C1B7B29C017954FD1DB2D620")
            return {"/conversations": START, "/conversations/c-1/messages": PLAYBACK}.get(path) or \
                (ANSWER if body.get("action") == "confirm_playback" else INVALID)

        with mock.patch.object(fex_live, "_request", side_effect=fake):
            html = self.client.get("/chat/prod-coffee-co/?source=live").content.decode()
            self.assertIn(">REAL API<", html)
            self.assertIn("What has been most difficult lately?", html)
            self.assertEqual(self.chat("Prices dropped")["step"], "playback")
            answer = self.chat("✓ Sí, es correcto", {"name": "confirm_playback", "args": {}})
            self.assertEqual(answer["source"], "live")
            self.assertEqual(len(answer["citations"]), 2)
            # A rejected action keeps the previous buttons instead of leaving none.
            kept = self.chat("No guardar", {"name": "set_feedback", "args": {"value": "yes"}})
            self.assertEqual(kept["suggestions"], answer["suggestions"])
        self.assertEqual(calls[1], ("/conversations/c-1/messages", {"text": "Prices dropped"}))

    def test_translated_reply_shows_buttons_in_the_chosen_language(self, _weather):
        def fake(persona, method, path, body=None):
            return {"/conversations": START, "/conversations/c-1/messages": PLAYBACK}[path]

        with mock.patch.object(fex_live, "_request", side_effect=fake), \
                mock.patch("exchange.aws_tools.translate", return_value="Voici ce que j'ai compris."):
            self.client.get("/chat/prod-coffee-co/?source=live")
            d = self.client.post("/api/chat", json.dumps({
                "message": "Les prix ont baissé", "persona_id": "prod-coffee-co",
                "language": "fr", "language_chosen": True}), content_type="application/json").json()
        self.assertEqual(d["language"], "fr")
        self.assertEqual([b["label"] for b in d["suggestions"]], ["✓ Oui, c'est bien ça", "Terminer la conversation"])

    def test_attachment_description_fits_the_api_message_limit(self, _weather):
        sent = []

        def fake(persona, method, path, body=None):
            sent.append(body)
            return {"/conversations": START, "/conversations/c-1/messages": PLAYBACK}[path]

        read = [{"name": "field.jpg", "text": "Dry, cracked soil around young coffee plants."}]
        with mock.patch.object(fex_live, "_request", side_effect=fake), \
                mock.patch("exchange.views._read_attachments", return_value=read):
            self.client.get("/chat/prod-coffee-co/?source=live")
            d = self.client.post("/api/chat", json.dumps({
                "message": "é" * 3990 + " 🌧️", "persona_id": "prod-coffee-co",
                "attachments": [{"name": "field.jpg", "kind": "image", "key": "k"}]}),
                content_type="application/json").json()
        self.assertEqual(d["source"], "live")
        text = sent[-1]["text"]
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 4000)  # the API counts UTF-16 units
        self.assertIn("Dry, cracked soil around young coffee plants.", text)

    def test_unreachable_api_falls_back_to_mock_with_a_note(self, _weather):
        with mock.patch.object(fex_live, "_request", side_effect=fex_live.LiveUnavailable("Can't reach the chat API")):
            html = self.client.get("/chat/prod-coffee-co/?source=live").content.decode()
            self.assertIn(">MOCK<", html)
            self.assertIn("reach the chat API", html)
            d = self.chat("Prices dropped")
        self.assertEqual(d["source"], "mock")
        self.assertTrue(d["text"].startswith("⚠"))

    def test_consumers_stay_on_mock(self, _weather):
        with mock.patch.object(fex_live, "_request") as req:
            html = self.client.get("/chat/cons-coffee-us/?source=live").content.decode()
        req.assert_not_called()
        self.assertIn("serves producers only", html)


class FakeS3:
    """Just enough of boto3's S3 client: an in-memory bucket."""
    class exceptions:
        class ClientError(Exception):
            pass

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body=b"", **_):
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.ClientError("NoSuchKey")
        return {"Body": mock.Mock(read=mock.Mock(return_value=self.objects[Key]))}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.ClientError("404")
        return {}

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k} for k in self.objects if k.startswith(Prefix)]}

    def delete_objects(self, Bucket, Delete):
        for o in Delete["Objects"]:
            self.objects.pop(o["Key"], None)


class FakeTranscribe:
    """Statuses play in order; the last one repeats. COMPLETED writes the transcript, like the real job."""
    def __init__(self, s3, statuses):
        self.s3, self.statuses, self.deleted, self.output = s3, list(statuses), [], None

    def start_transcription_job(self, OutputKey, **_):
        self.output = OutputKey

    def get_transcription_job(self, TranscriptionJobName):
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if status == "COMPLETED":
            self.s3.objects[self.output] = json.dumps({"results": {"transcripts": [{"transcript": "hola"}]}}).encode()
        return {"TranscriptionJob": {"TranscriptionJobStatus": status}}

    def delete_transcription_job(self, TranscriptionJobName):
        self.deleted.append(TranscriptionJobName)


@override_settings(UPLOADS_BUCKET="test-uploads")
class TranscribeCleanupTests(SimpleTestCase):
    def run_transcribe(self, statuses):
        from . import aws_tools
        s3 = FakeS3()
        tr = FakeTranscribe(s3, statuses)
        clock = iter(range(0, 10_000, 30))  # every poll moves the clock 30 s, so the 120 s deadline passes quickly
        with mock.patch.object(aws_tools, "_client", side_effect=lambda name: {"s3": s3, "transcribe": tr}[name]), \
                mock.patch.object(aws_tools.time, "time", side_effect=lambda: next(clock)), \
                mock.patch.object(aws_tools.time, "sleep"):
            try:
                result = aws_tools.transcribe(b"audio", "audio/webm", "es")
            except RuntimeError as e:
                result = e
        return result, s3, tr

    def test_a_finished_job_is_cleaned_up_at_once(self):
        text, s3, tr = self.run_transcribe(["IN_PROGRESS", "COMPLETED"])
        self.assertEqual(text, "hola")
        self.assertEqual(s3.objects, {})
        self.assertEqual(len(tr.deleted), 1)

    def test_a_timed_out_job_still_running_is_left_for_the_completion_cleanup(self):
        err, s3, tr = self.run_transcribe(["IN_PROGRESS"])
        self.assertIsInstance(err, RuntimeError)
        keys = sorted(s3.objects)
        self.assertEqual(len(keys), 2)  # the audio the job is still reading, and the abandoned marker
        self.assertTrue(keys[0].endswith("/abandoned"))
        self.assertEqual(tr.deleted, [])

    def test_a_job_that_finishes_right_after_the_timeout_is_cleaned_up_by_the_request(self):
        statuses = ["IN_PROGRESS"] * 3 + ["COMPLETED"]  # 3 polls fit in the 120 s wait; done at the re-check
        err, s3, tr = self.run_transcribe(statuses)
        self.assertIsInstance(err, RuntimeError)
        self.assertEqual(s3.objects, {})
        self.assertEqual(len(tr.deleted), 1)

    def test_completion_cleanup_removes_an_abandoned_job_and_ignores_others(self):
        from . import voice_cleanup
        A, D = "a" * 32, "d" * 32  # voice IDs are uuid4 hex
        s3, tr = FakeS3(), FakeTranscribe(None, ["COMPLETED"])
        s3.objects = {f"voice/{A}/audio.webm": b"a", f"voice/{A}/transcript.json": b"t",
                      f"voice/{A}/abandoned": b"",
                      f"voice/{D}/audio.webm": b"a"}
        with mock.patch.object(voice_cleanup, "_clients", return_value=(s3, tr)):
            event = lambda job: {"detail": {"TranscriptionJobName": job, "TranscriptionJobStatus": "COMPLETED"}}
            voice_cleanup.handler(event(f"fx-ui-voice-{A}"), None, bucket="test-uploads")
            voice_cleanup.handler(event(f"fx-ui-voice-{D}"), None, bucket="test-uploads")  # still being read: left
            voice_cleanup.handler(event("other-job"), None, bucket="test-uploads")
        self.assertEqual(list(s3.objects), [f"voice/{D}/audio.webm"])
        self.assertEqual(tr.deleted, [f"fx-ui-voice-{A}"])


@override_settings(UPLOADS_BUCKET="test-uploads")
class VoiceUploadLimitTests(SimpleTestCase):
    def post(self, size):
        with mock.patch("exchange.aws_tools.transcribe", return_value="hola") as tr:
            r = self.client.post("/api/transcribe?language=es", data=b"x" * size, content_type="audio/webm")
        return r, tr

    def test_a_recording_over_djangos_default_body_limit_is_transcribed(self):
        r, tr = self.post(3 * 1024 * 1024)  # above Django's 2.5 MiB DATA_UPLOAD_MAX_MEMORY_SIZE
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["text"], "hola")
        self.assertEqual(len(tr.call_args.args[0]), 3 * 1024 * 1024)

    def test_a_recording_over_the_limit_is_refused_before_transcribing(self):
        from . import views
        r, tr = self.post(views.MAX_VOICE_BYTES + 1)
        self.assertEqual(r.status_code, 400)
        tr.assert_not_called()
