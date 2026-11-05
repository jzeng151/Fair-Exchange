"""Real API mode: talk to the real FEX agent through the Fair Exchange chat API (docs/specs/25-chat-endpoint.md).

    POST /conversations                  -> NDJSON stream (first event: {type: "conversation", conversationId})
    POST /conversations/{id}/messages    {text}          -> NDJSON stream
    POST /conversations/{id}/actions     {action, args}  -> NDJSON stream

Event shapes come from the shared contract (api/src/types/conversation-contract.ts): text, claim, answer, step,
actions, record_saved, error, done. The API is either the local chain (`bash scripts/e2e/run_local.sh --web`,
http://127.0.0.1:3000) or the deployed `ApiUrl` stack output with the demo passcode (docs/handoff/02-deploy.md).

Identity is the sign-in stand-in (docs/specs/11-identity.md): the `x-demo-producer-id` header names one of the
scenario producers in eval/scenarios/, plus `x-demo-passcode` for the deployed API. The real agent reads the
producer's own data; scope is enforced in its tools, never by this UI.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings

from .catalog import Persona


class LiveUnavailable(Exception):
    """The chat API can't be used for this request: not configured, unreachable, or refused it."""


# Labels for the buttons offered at each step, in the languages the agent speaks (en, es, fr).
_ACTION_LABELS = {
    "en": {
        ("confirm_playback", ""): "✓ Yes, that's right",
        ("reopen_playback", ""): "↺ Change what I said",
        ("retry_answer", ""): "↻ Try the answer again",
        ("set_consent", "internal"): "Save for Fair Trade USA only",
        ("set_consent", "internal_and_outward"): "Save and share with other producers",
        ("set_consent", "declined"): "Don't save",
        ("set_feedback", "yes"): "👍 It helped",
        ("set_feedback", "somewhat"): "🤔 Somewhat",
        ("set_feedback", "no"): "👎 Not really",
        ("end", ""): "End the conversation",
    },
    "es": {
        ("confirm_playback", ""): "✓ Sí, es correcto",
        ("reopen_playback", ""): "↺ Cambiar lo que dije",
        ("retry_answer", ""): "↻ Intentar la respuesta de nuevo",
        ("set_consent", "internal"): "Guardar solo para Fair Trade USA",
        ("set_consent", "internal_and_outward"): "Guardar y compartir con otros productores",
        ("set_consent", "declined"): "No guardar",
        ("set_feedback", "yes"): "👍 Me ayudó",
        ("set_feedback", "somewhat"): "🤔 Algo",
        ("set_feedback", "no"): "👎 No mucho",
        ("end", ""): "Terminar la conversación",
    },
    "fr": {
        ("confirm_playback", ""): "✓ Oui, c'est bien ça",
        ("reopen_playback", ""): "↺ Modifier ce que j'ai dit",
        ("retry_answer", ""): "↻ Réessayer la réponse",
        ("set_consent", "internal"): "Enregistrer pour Fair Trade USA seulement",
        ("set_consent", "internal_and_outward"): "Enregistrer et partager avec d'autres producteurs",
        ("set_consent", "declined"): "Ne pas enregistrer",
        ("set_feedback", "yes"): "👍 Ça m'a aidé",
        ("set_feedback", "somewhat"): "🤔 Un peu",
        ("set_feedback", "no"): "👎 Pas vraiment",
        ("end", ""): "Terminer la conversation",
    },
}
# The argument each button sends; set_consent and set_feedback offer one button per value.
_ACTION_CHOICES = {
    "confirm_playback": [("", {})],
    "reopen_playback": [("", {})],
    "retry_answer": [("", {})],
    "set_consent": [(v, {"scope": v}) for v in ("internal", "internal_and_outward", "declined")],
    "set_feedback": [(v, {"value": v}) for v in ("yes", "somewhat", "no")],
    "end": [("", {})],
}
# Button order: the step's main choice first. correct_playback needs the corrected text, so it isn't a button;
# typing during playback sends a correction (the agent treats a playback-step message as one).
_BUTTON_ORDER = ["confirm_playback", "set_feedback", "set_consent", "retry_answer", "reopen_playback", "end"]
_SECTION_KIND = {"insights": "regional", "peer_examples": "peer"}


def configured() -> bool:
    return bool(getattr(settings, "FEX_API_URL", ""))


def available_for(persona: Persona) -> bool:
    """The real agent needs a configured API and a persona mapped to a scenario producer (producers only)."""
    return configured() and bool(persona.fex_producer_id)


def _request(persona: Persona, method: str, path: str, body: dict | None = None) -> list[dict]:
    base = settings.FEX_API_URL.rstrip("/")
    headers = {"content-type": "application/json", "x-demo-producer-id": persona.fex_producer_id}
    if getattr(settings, "FEX_DEMO_PASSCODE", ""):
        headers["x-demo-passcode"] = settings.FEX_DEMO_PASSCODE
    req = urllib.request.Request(f"{base}{path}", method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=settings.FEX_API_TIMEOUT) as res:
            raw = res.read().decode()
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read().decode()).get("message") or str(e)
        except Exception:
            message = str(e)
        raise LiveUnavailable(f"The chat API refused the request ({e.code}): {message}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LiveUnavailable(f"Can't reach the chat API at {base}") from e
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def start(persona: Persona) -> tuple[str, dict]:
    """Open a conversation. Returns (conversation_id, the opening as an answer dict)."""
    events = _request(persona, "POST", "/conversations", {})
    cid = next((e["conversationId"] for e in events if e.get("type") == "conversation"), None)
    if not cid:
        raise LiveUnavailable("The chat API did not return a conversation")
    return cid, to_answer(events, persona.language)


def message(persona: Persona, cid: str, text: str) -> list[dict]:
    return _request(persona, "POST", f"/conversations/{cid}/messages", {"text": text})


def action(persona: Persona, cid: str, name: str, args: dict) -> list[dict]:
    return _request(persona, "POST", f"/conversations/{cid}/actions", {"action": name, "args": args})


def to_answer(events: list[dict], fallback_language: str) -> dict:
    """Map one turn's events onto the answer shape the chat UI renders (engine.Answer.as_dict)."""
    language, step, allowed, has_actions = fallback_language, None, [], False
    said, claims, errors, saved = [], [], [], None
    for e in events:
        kind = e.get("type")
        if kind == "text":
            said.append(e.get("text", ""))
        elif kind == "claim":
            claims.append(e)
        elif kind == "step":
            step, language = e.get("step"), e.get("language") or language
        elif kind == "actions":
            allowed, language, has_actions = list(e.get("allowed") or []), e.get("language") or language, True
        elif kind == "error":
            errors.append(e.get("message") or e.get("code") or "Something went wrong.")
        elif kind == "record_saved":
            saved = e

    parts = ["".join(said).strip()] if "".join(said).strip() else []
    citations: list[dict] = []
    for c in claims:
        claim = c.get("claim") or {}
        cit = claim.get("citation") or {}
        parts.append("• " + claim.get("text", ""))
        label = cit.get("source", "source")
        if cit.get("period"):
            label += f" ({cit['period']})"
        citations.append({"label": label, "kind": _SECTION_KIND.get(c.get("section"), "regional")})
        if cit.get("standard_clause"):
            citations.append({"label": cit["standard_clause"], "kind": "standard"})
    parts += errors
    if saved:
        declined = saved.get("status") == "declined"
        parts.append(({"en": "Noted: nothing about your conversation is stored.", "es": "Anotado: no se guarda nada de su conversación.",
                       "fr": "Noté : rien de votre conversation n'est conservé."} if declined else
                      {"en": "Saved (version {v}).", "es": "Guardado (versión {v}).", "fr": "Enregistré (version {v})."})
                     .get(language, "Saved (version {v}).").format(v=saved.get("version")))

    if step == "closed" and not parts:
        parts.append({"en": "This conversation is closed. Start a new chat to talk again.",
                      "es": "Esta conversación terminó. Empieza un chat nuevo para hablar otra vez.",
                      "fr": "Cette conversation est terminée. Commencez un nouveau chat pour reparler."}
                     .get(language, "This conversation is closed. Start a new chat to talk again."))

    # Deduplicate citations (the same standard clause often backs several claims), keeping order.
    seen, unique = set(), []
    for c in citations:
        if c["label"] not in seen:
            seen.add(c["label"])
            unique.append(c)

    labels = _ACTION_LABELS.get(language, _ACTION_LABELS["en"])
    suggestions = [
        {"label": labels.get((name, key), name.replace("_", " ")), "action": name, "args": args}
        for name in sorted((a for a in allowed if a in _BUTTON_ORDER), key=_BUTTON_ORDER.index)
        for key, args in _ACTION_CHOICES[name]
    ]
    return {
        "text": "\n\n".join(p for p in parts if p) or "…",
        "citations": unique,
        "suggestions": suggestions,
        "pii_flagged": [],
        "in_scope": True,
        "language": language,
        "sentiment": "",
        "tags": [],
        "source": "live",
        "step": step,
        "closed": step == "closed",
        "has_actions": has_actions,  # False: this turn didn't change what's allowed (e.g. an error); keep the last buttons
    }
