"""Views: persona picker, the chat page, about, docs, demo, and the mock chat API.

No sign-on (SDD.md). The visitor clicks a persona tile, then chats as that persona. Location and weather
(live from Open-Meteo, else sample values) come from the chosen persona. Answers come from the mock engine,
or, in Real API mode, from the real FEX agent through the Fair Exchange chat API (fex_live.py,
docs/REAL-API.md). The header's Mock / Real API switch picks the source per session.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from . import engine, catalog, fex_live, trends, weather, uploads, aws_tools


def _data_source(request) -> str:
    """The requested source: ?source=mock|live (remembered in the session), else the session, else DATA_SOURCE."""
    asked = request.GET.get("source")
    if asked in ("mock", "live"):
        request.session["data_source"] = asked
    return request.session.get("data_source") or settings.DATA_SOURCE


def _live_problem(persona) -> str:
    """Why the real agent can't serve this persona, or "" if it can."""
    if not fex_live.configured():
        return "The Real API needs FEX_API_URL (see docs/REAL-API.md), so this chat uses mock answers."
    if not persona.fex_producer_id:
        return "The real FEX agent serves producers only, so this consumer chat uses mock answers."
    return ""


def _live_conversations(request) -> dict:
    return request.session.setdefault("fex_conversations", {})


def picker(request):
    """Landing page: one click on a persona tile starts the chat in that persona's language."""
    groups = []
    for role in catalog.ROLES:
        tiles = []
        for p in (catalog.get_persona(pid) for pid in catalog.PICKER_IDS):
            if not p or p.role != role:
                continue
            chat_lang = p.language if p.language in engine.LANGUAGES else "en"
            tiles.append({
                **p.as_dict(),
                "role_icon": catalog.ROLE_ICON.get(role, "•"),
                "role_label": catalog.ROLE_LABEL.get(role, role.title()),
                "product_icon": catalog.PRODUCT_ICON.get(p.product, "•"),
                "product_label": catalog.PRODUCT_LABEL.get(p.product, p.product.title()),
                "chat_lang": chat_lang,
                "lang_label": engine.LANGUAGES[chat_lang],
            })
        groups.append({
            "role": role,
            "label": catalog.ROLE_LABEL.get(role, role.title()) + "s",
            "icon": catalog.ROLE_ICON.get(role, "•"),
            "personas": tiles,
        })
    return render(request, "exchange/picker.html", {"groups": groups})


def chat(request, persona_id: str):
    persona = catalog.get_persona(persona_id)
    if not persona:
        return redirect("picker")
    request.session["persona_id"] = persona_id
    # The tile's ?lang=, else the persona's own language; the chat's selector can still change it.
    language = request.GET.get("lang")
    if language not in engine.LANGUAGES:
        language = persona.language if persona.language in engine.LANGUAGES else "en"
    request.session["language"] = language

    requested = _data_source(request)
    source, notice, opening, opening_suggestions = "mock", "", engine.opening(persona, language), []
    conversations = _live_conversations(request)
    conversations.pop(persona_id, None)  # every page load starts a fresh conversation
    if requested == "live":
        notice = _live_problem(persona)
        if not notice:
            try:
                cid, first = fex_live.start(persona)
                conversations[persona_id] = cid
                source, opening, opening_suggestions = "live", first["text"], first["suggestions"]
                # Only action names go in the (cookie-backed) session; buttons are rebuilt from them.
                request.session.setdefault("fex_allowed", {})[persona_id] = first["allowed"]
                asked = request.GET.get("lang")
                if asked in engine.LANGUAGES and asked != first["language"]:
                    # The link names a language: keep it, and translate FEX's greeting (Amazon Translate).
                    try:
                        opening = aws_tools.translate(opening, asked)
                    except Exception:
                        pass
                    opening_suggestions = fex_live.buttons(first["allowed"], asked)
                    language = asked
                else:
                    language = first["language"] if first["language"] in engine.LANGUAGES else language
                request.session["language"] = language
            except fex_live.LiveUnavailable as e:
                notice = f"{e}. This chat uses mock answers until it's reachable."
    request.session.modified = True

    # Real weather (Open-Meteo) for this persona's location; always attempted in Real API mode.
    live_weather, weather_live = weather.weather_status(persona, force=requested == "live")
    pdata = persona.as_dict()
    pdata["weather"] = live_weather.as_dict()
    context = {
        "persona": pdata,
        "languages": engine.LANGUAGES,
        "language": language,
        "opening": opening,
        "opening_suggestions": opening_suggestions,
        "questions": persona.questions,
        "trends": trends.trends_for(persona),
        "uploads_enabled": uploads.enabled(),
        "data_source": source,
        "requested_source": requested,
        "notice": notice,
        "weather_live": weather_live,
    }
    return render(request, "exchange/chat.html", context)


def about(request):
    return render(request, "exchange/about.html", {})


def demo(request):
    return render(request, "exchange/demo.html", {})


def docs(request):
    return render(request, "exchange/docs.html", {"languages": engine.LANGUAGES})


@require_POST
def api_chat(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("invalid JSON")

    message = (payload.get("message") or "").strip()
    action = payload.get("action") if isinstance(payload.get("action"), dict) else None
    if not message:
        return HttpResponseBadRequest("empty message")
    if len(message) > 4000:
        message = message[:4000]

    language = payload.get("language") or request.session.get("language", "en")
    if language in engine.LANGUAGES:
        request.session["language"] = language

    persona = catalog.get_persona(payload.get("persona_id") or request.session.get("persona_id", ""))
    if not persona:
        return HttpResponseBadRequest("no persona selected")

    attachments = payload.get("attachments") or []  # E1: [{name, kind, key?, content_type?}]
    if _data_source(request) == "live" and not _live_problem(persona):
        # Attached photos/documents are read with Claude on Amazon Bedrock; the description goes to FEX with the
        # producer's words, so FEX's grounding, scope and PII checks apply to it like any message.
        read = _read_attachments(attachments, language) if action is None else []
        live = _live_turn(request, persona, _live_message(message, read), action)
        if live is not None:
            if read:
                live["text"] = "\n".join(f"📎 {r['name']} (read with Claude on Amazon Bedrock): {r['text']}"
                                         for r in read) + "\n\n" + live["text"]
                live["attachments_read"] = read
            chosen = payload.get("language")
            if payload.get("language_chosen") and chosen in engine.LANGUAGES and chosen != live.get("language"):
                try:
                    live["text"] = aws_tools.translate(live["text"], chosen) + \
                        "\n\n🌐 Translated from FEX's reply with Amazon Translate."
                    live["language"] = chosen
                    request.session["language"] = chosen
                    if not live.get("closed"):  # the buttons follow the chosen language too
                        live["suggestions"] = fex_live.buttons(
                            request.session.get("fex_allowed", {}).get(persona.id, []), chosen)
                except Exception:
                    pass
            return JsonResponse(live)

    # Answer with live weather folded into the persona so the insight reflects real conditions.
    import dataclasses
    live_persona = dataclasses.replace(persona, weather=weather.weather_for(persona))
    answer = engine.respond(message, live_persona, language)
    data = answer.as_dict()
    data["source"] = "mock"
    live_error = request.session.pop("fex_last_error", None)
    if live_error:
        data["text"] = f"⚠ {live_error}. This is a mock answer instead.\n\n" + data["text"]
    if attachments:
        names = ", ".join(a.get("name", "file") for a in attachments[:5])
        stored = sum(1 for a in attachments if a.get("key"))
        where = "saved securely for a reviewer" if stored else "noted"
        note = {
            "en": f"Thanks — I've {where} your {len(attachments)} attachment(s) ({names}).",
            "es": f"Gracias — he {('guardado de forma segura' if stored else 'registrado')} tus "
                  f"{len(attachments)} adjunto(s) ({names}).",
        }.get(language, f"Noted {len(attachments)} attachment(s): {names}.")
        data["text"] = note + "\n\n" + data["text"]
        data["attachments_ack"] = [a.get("name", "file") for a in attachments[:5]]
    return JsonResponse(data)


API_MESSAGE_LIMIT = 4000  # MAX_MESSAGE_CHARS in api/src/core/validate.ts, counted in UTF-16 units (JS length)


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _clip_utf16(text: str, limit: int) -> str:
    """Text cut to at most `limit` UTF-16 units, never splitting a character."""
    if _utf16_len(text) <= limit:
        return text
    return text.encode("utf-16-le")[:max(limit, 0) * 2].decode("utf-16-le", errors="ignore")


def _live_message(message: str, read: list[dict]) -> str:
    """The text sent to the chat API: the producer's words plus what was read from attachments, within the API's
    limit. Attachment context gets at most half the limit; the producer's words are trimmed to fit the rest."""
    if not read:
        return _clip_utf16(message, API_MESSAGE_LIMIT)
    context = _clip_utf16("\n".join(f"[Attached {r['name']}: {r['text']}]" for r in read), API_MESSAGE_LIMIT // 2)
    words = message if message != "(shared attachment)" else ""
    words = _clip_utf16(words, API_MESSAGE_LIMIT - _utf16_len(context) - 2)
    return (words + "\n\n" + context).strip()


def _live_turn(request, persona, message: str, action: dict | None) -> dict | None:
    """One turn with the real agent: a button sends its action, typed text a message. None means fall back to mock
    (with a note), so the demo never dead-ends when the chat API is down."""
    conversations = _live_conversations(request)
    try:
        cid = conversations.get(persona.id)
        if not cid:  # e.g. the session was reset; open a new conversation first
            cid, _ = fex_live.start(persona)
            conversations[persona.id] = cid
        if action and action.get("name"):
            events = fex_live.action(persona, cid, action["name"], action.get("args") or {})
            # Feedback is the last question: end the conversation right after it, so it doesn't keep asking.
            if action["name"] == "set_feedback" and not any(e.get("type") == "error" for e in events):
                events = events + fex_live.action(persona, cid, "end", {})
                events.append({"type": "text", "text": "\n\n" + fex_live.ENDED.get(
                    request.session.get("language", persona.language), fex_live.ENDED["en"])})
        else:
            events = fex_live.message(persona, cid, message)
        data = fex_live.to_answer(events, request.session.get("language", persona.language))
        allowed = request.session.setdefault("fex_allowed", {})
        if data["closed"]:
            conversations.pop(persona.id, None)
            allowed.pop(persona.id, None)
        elif data["has_actions"]:
            allowed[persona.id] = data["allowed"]
        else:  # e.g. an error: the allowed actions didn't change, so keep offering them
            data["suggestions"] = fex_live.buttons(allowed.get(persona.id, []), data["language"])
        if data["language"] in engine.LANGUAGES:
            request.session["language"] = data["language"]
        request.session.modified = True
        return data
    except fex_live.LiveUnavailable as e:
        request.session["fex_last_error"] = str(e)
        return None


def _read_attachments(attachments: list, language: str) -> list[dict]:
    if not aws_tools.bucket():
        return []
    out = []
    for a in attachments[:3]:
        if not a.get("key") or not str(a["key"]).startswith("uploads/"):
            continue
        import mimetypes  # an older page may not send the type: work it out from the file name
        content_type = a.get("content_type") or mimetypes.guess_type(a.get("name") or a["key"])[0] or ""
        try:
            text = aws_tools.read_attachment(a["key"], content_type, engine.LANGUAGES.get(language, "English"))
        except Exception:
            text = None
        out.append({"name": a.get("name", "file"),
                    "text": text or "this file couldn't be read, so FEX hasn't used it. Please describe it in words."})
    return out


@require_POST
def api_speak(request):
    """Amazon Polly: an answer read aloud (MP3). 204 when the language has no Polly voice."""
    try:
        payload = json.loads(request.body or "{}")
        audio = aws_tools.speak((payload.get("text") or "")[:2900], payload.get("language") or "en")
    except Exception:
        audio = None
    if not audio:
        return HttpResponse(status=204)
    return HttpResponse(audio, content_type="audio/mpeg")


# A Lambda function URL accepts at most 6 MB per request, and a binary body arrives base64-encoded (4/3 larger).
MAX_VOICE_BYTES = 4 * 1024 * 1024


@require_POST
def api_transcribe(request):
    """Amazon Transcribe: a recorded voice note (raw audio body) becomes text for the message box."""
    if not aws_tools.bucket():
        return JsonResponse({"error": "Voice notes are not set up."}, status=503)
    too_long = JsonResponse({"error": "The recording is empty or too long."}, status=400)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_VOICE_BYTES:
            return too_long
    except ValueError:
        return too_long
    # A bounded read of the raw body: request.body would stop at Django's 2.5 MiB DATA_UPLOAD_MAX_MEMORY_SIZE.
    audio = request.read(MAX_VOICE_BYTES + 1)
    if not audio or len(audio) > MAX_VOICE_BYTES:
        return too_long
    try:
        text = aws_tools.transcribe(audio, request.content_type or "audio/webm", request.GET.get("language", "en"))
    except Exception:
        return JsonResponse({"error": "The recording couldn't be transcribed. Please type instead."}, status=502)
    return JsonResponse({"text": text})


@require_POST
def api_presign(request):
    """E1: return presigned S3 PUT URLs so the browser uploads attachments directly to S3."""
    if not uploads.enabled():
        return JsonResponse({"enabled": False})
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("invalid JSON")
    files = payload.get("files") or []
    out = []
    for f in files[:5]:
        res = uploads.presign_put(f.get("name", "file"), f.get("content_type", ""), int(f.get("size") or 0))
        out.append(res or {"error": "upload unavailable"})
    return JsonResponse({"enabled": True, "results": out})


@require_POST
def api_report(request):
    """E3: build a downloadable report from the client's chat history."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("invalid JSON")
    persona = catalog.get_persona(payload.get("persona_id") or request.session.get("persona_id", ""))
    if not persona:
        return HttpResponseBadRequest("no persona selected")
    turns = payload.get("turns") or []
    report = trends.build_report(persona, turns)
    resp = HttpResponse(report, content_type="text/markdown; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="fair-trade-exchange-{persona.id}-report.md"'
    return resp


@require_POST
def api_points(request):
    """E6/E7: shared-data points (with breakdown), your ratings of shared answers, and how others used them."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("invalid JSON")
    shared_turns = int(payload.get("shared_turns") or 0)
    tags = payload.get("tags") or []
    ratings = payload.get("ratings") or []
    data = trends.points_summary(shared_turns, tags, ratings)
    persona = catalog.get_persona(payload.get("persona_id") or request.session.get("persona_id", ""))
    if persona:
        data["usage"] = trends.usage_summary(persona, shared_turns, tags)
    return JsonResponse(data)


def healthz(request):
    return JsonResponse({"status": "ok"})
