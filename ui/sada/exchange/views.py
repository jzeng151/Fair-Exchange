"""Views: persona picker, the chat page, about, docs, demo, and the mock chat API.

No sign-on (SDD.md). The visitor clicks a persona tile, then chats as that persona. Location
and a (made-up) weather overlay come from the chosen persona; the chat engine mocks the Fair Exchange
API and is shaped so the real runtime can replace it.
"""
from __future__ import annotations

import json

from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from . import engine, catalog, trends, weather, uploads


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
    # Real weather (Open-Meteo) for this persona's location; falls back to the mocked overlay.
    live = weather.weather_for(persona)
    pdata = persona.as_dict()
    pdata["weather"] = live.as_dict()
    context = {
        "persona": pdata,
        "languages": engine.LANGUAGES,
        "language": language,
        "opening": engine.opening(persona, language),
        "questions": persona.questions,
        "trends": trends.trends_for(persona),
        "uploads_enabled": uploads.enabled(),
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

    attachments = payload.get("attachments") or []  # E1: [{name, kind, key?}]
    # Answer with live weather folded into the persona so the insight reflects real conditions.
    import dataclasses
    live_persona = dataclasses.replace(persona, weather=weather.weather_for(persona))
    answer = engine.respond(message, live_persona, language)
    data = answer.as_dict()
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
    """E6/E7: compute shared-data points for the given shared turns and tags."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("invalid JSON")
    shared_turns = int(payload.get("shared_turns") or 0)
    tags = payload.get("tags") or []
    return JsonResponse(trends.points_summary(shared_turns, tags))


def healthz(request):
    return JsonResponse({"status": "ok"})
