"""The chat engine. Today it mocks input/output (SDD.md); the interface is shaped so the real
Fair Exchange API can replace `respond()` without the UI changing.

Every answer:
- is grounded with a citation (the vision doc requires every claim to carry a source),
- is phrased as a suggestion, never a command (enablement tone),
- offers a few simple follow-up questions,
- stays within guardrails and flags PII rather than redacting it,
- can be returned in the visitor's chosen language.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import guardrails
from .catalog import Persona

# Languages offered in the UI. Output can be translated to any of these (mocked here).
LANGUAGES = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "pt": "Português",
    "sw": "Kiswahili",
    "hi": "हिन्दी",
}


@dataclass
class Answer:
    text: str
    citations: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    pii_flagged: list[str] = field(default_factory=list)
    in_scope: bool = True
    language: str = "en"
    sentiment: str = "supportive"   # E5: a gentle read of the exchange's tone
    tags: list[str] = field(default_factory=list)  # challenge tags, for reports/trends

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "citations": self.citations,
            "suggestions": self.suggestions,
            "pii_flagged": self.pii_flagged,
            "in_scope": self.in_scope,
            "language": self.language,
            "sentiment": self.sentiment,
            "tags": self.tags,
        }


# Fixed UI copy per language, written in code (not model-generated) so tone and translation are stable.
_COPY = {
    "en": {
        "greeting": "Hi {name}, good to meet you. I'm the Fair Trade Exchange assistant. "
                    "What has felt difficult lately for your {focus} work in {region}?",
        "scope_redirect": "That's a little outside what I can help with here. I'm best at your own "
                          "challenges, what regional data shows, and what peers have tried. "
                          "Would any of these be useful?",
        "pii_note": "I noticed what looks like personal contact details. I've flagged it for a human "
                    "reviewer and kept your words exactly as you wrote them.",
        "evidence_lead": "Here's what the evidence suggests, and what some peers have tried:",
        "handback": "You and your cooperative know your situation best. These are options to weigh, not steps to take.",
    },
    "es": {
        "greeting": "Hola {name}, un gusto saludarte. Soy el asistente de Fair Trade Exchange. "
                    "¿Qué ha sido difícil últimamente en tu trabajo de {focus} en {region}?",
        "scope_redirect": "Eso queda un poco fuera de lo que puedo ayudar aquí. Lo mío son tus propios "
                          "desafíos, lo que muestran los datos de la región y lo que han probado otros productores. "
                          "¿Te sirve alguna de estas?",
        "pii_note": "Noté lo que parecen datos de contacto personales. Lo marqué para revisión humana "
                    "y mantuve tus palabras tal como las escribiste.",
        "evidence_lead": "Esto es lo que sugiere la evidencia, y lo que han probado algunos productores:",
        "handback": "Tú y tu cooperativa conocen mejor su situación. Son opciones para considerar, no pasos a seguir.",
    },
    "fr": {
        "greeting": "Bonjour {name}, ravi de vous rencontrer. Je suis l'assistant Fair Trade Exchange. "
                    "Qu'est-ce qui a été difficile récemment dans votre travail de {focus} à {region} ?",
        "scope_redirect": "Cela sort un peu de ce que je peux traiter ici. Je suis surtout utile sur vos "
                          "propres difficultés, ce que montrent les données régionales et ce que des pairs ont essayé. "
                          "L'une de ces pistes vous aiderait-elle ?",
        "pii_note": "J'ai repéré ce qui ressemble à des coordonnées personnelles. Je l'ai signalé à un "
                    "relecteur humain et j'ai gardé vos mots tels quels.",
        "evidence_lead": "Voici ce que suggèrent les données, et ce que des pairs ont essayé :",
        "handback": "Vous et votre coopérative connaissez le mieux votre situation. Ce sont des options à peser, pas des consignes.",
    },
    "pt": {
        "greeting": "Olá {name}, prazer em conhecer você. Sou o assistente Fair Trade Exchange. "
                    "O que tem sido difícil ultimamente no seu trabalho de {focus} em {region}?",
        "scope_redirect": "Isso foge um pouco do que posso ajudar aqui. Sou melhor com os seus próprios "
                          "desafios, o que os dados regionais mostram e o que outros produtores tentaram. "
                          "Alguma destas ajudaria?",
        "pii_note": "Percebi o que parecem dados de contato pessoais. Sinalizei para revisão humana e "
                    "mantive suas palavras exatamente como você escreveu.",
        "evidence_lead": "Veja o que a evidência sugere, e o que alguns produtores tentaram:",
        "handback": "Você e sua cooperativa conhecem melhor a sua situação. São opções a ponderar, não passos a seguir.",
    },
    "sw": {
        "greeting": "Habari {name}, nafurahi kukutana nawe. Mimi ni msaidizi wa Fair Trade Exchange. "
                    "Ni nini kimekuwa kigumu hivi karibuni katika kazi yako ya {focus} huko {region}?",
        "scope_redirect": "Hilo liko nje kidogo ya ninachoweza kusaidia hapa. Nina uwezo zaidi kuhusu "
                          "changamoto zako mwenyewe, data ya eneo, na walichojaribu wakulima wenzako. "
                          "Je, mojawapo ya haya linaweza kusaidia?",
        "pii_note": "Nimeona kinachoonekana kama taarifa binafsi za mawasiliano. Nimeiweka alama kwa "
                    "mkaguzi wa kibinadamu na nimehifadhi maneno yako kama ulivyoyaandika.",
        "evidence_lead": "Haya ndiyo ushahidi unapendekeza, na walichojaribu baadhi ya wakulima:",
        "handback": "Wewe na ushirika wako mnajua hali yenu vizuri zaidi. Haya ni machaguo ya kupima, si hatua za kufuata.",
    },
    "hi": {
        "greeting": "नमस्ते {name}, आपसे मिलकर अच्छा लगा। मैं Fair Trade Exchange सहायक हूँ। "
                    "{region} में आपके {focus} कार्य में हाल में क्या कठिन रहा है?",
        "scope_redirect": "यह उससे थोड़ा बाहर है जिसमें मैं यहाँ मदद कर सकता हूँ। मैं आपकी अपनी "
                          "चुनौतियों, क्षेत्रीय आँकड़ों और साथी किसानों के प्रयासों पर सबसे उपयोगी हूँ। "
                          "क्या इनमें से कोई मदद करेगा?",
        "pii_note": "मुझे व्यक्तिगत संपर्क जानकारी जैसी कोई चीज़ दिखी। मैंने इसे मानव समीक्षक के लिए "
                    "चिह्नित किया है और आपके शब्द ज्यों के त्यों रखे हैं।",
        "evidence_lead": "आँकड़े यह सुझाते हैं, और कुछ किसानों ने यह आज़माया है:",
        "handback": "आप और आपकी सहकारी समिति अपनी स्थिति सबसे अच्छी तरह जानते हैं। ये विचार करने के विकल्प हैं, निर्देश नहीं।",
    },
}

# Topic playbooks: a data insight + a peer example, each with a citation, and simple follow-ups.
# Keyed by a challenge tag from the vision doc's 11-tag set.
_TOPICS = {
    "water": {
        "match": ("water", "rain", "drought", "dry", "irrigat", "agua", "lluvia", "sequía", "eau", "pluie"),
        "insight": "Rainfall in your region has run below the ten-year average for the last two seasons, "
                   "and water stress is rated high.",
        "insight_src": {"label": "CHIRPS rainfall + WRI Aqueduct (open data)", "kind": "regional"},
        "peer": "A comparable cooperative used Community Development Premium to build shade-and-mulch "
                "water retention and small catchment tanks.",
        "peer_src": {"label": "Fair Trade Premium project (sample) PROJ-1C85", "kind": "peer"},
        "clause": "APS 3.6 (water resource management)",
    },
    "price": {
        "match": ("price", "market", "sell", "income", "precio", "mercado", "prix", "marché"),
        "insight": "Farm-gate prices for your crop have been volatile this year, with a dip below the "
                   "five-year median in recent months.",
        "insight_src": {"label": "World Bank Commodity Price Data (Pink Sheet)", "kind": "regional"},
        "peer": "Peers facing the same dip pooled Premium funds into shared processing to capture more "
                "value per lot rather than selling raw.",
        "peer_src": {"label": "Fair Trade Premium project (sample) PROJ-A1AE", "kind": "peer"},
        "clause": "APS 1.1 (Fair Trade pricing and Premium use)",
    },
    "labor": {
        "match": ("labor", "labour", "worker", "harvest help", "migrant", "trabajo", "mano de obra", "main-d'œuvre"),
        "insight": "Seasonal labor availability in your area has tightened, matching a regional migration trend.",
        "insight_src": {"label": "Regional labor and migration indicators (open data)", "kind": "regional"},
        "peer": "A nearby organization used Premium for a shared childcare and transport scheme to keep "
                "harvest crews available.",
        "peer_src": {"label": "Fair Trade Premium project (sample) PROJ-26C3", "kind": "peer"},
        "clause": "FPS 2.4 (working conditions and labor)",
    },
    "soil": {
        "match": ("soil", "land", "erosion", "fertil", "suelo", "tierra", "sol", "terre"),
        "insight": "Soil organic matter in comparable plots has declined where cover cropping is low.",
        "insight_src": {"label": "Regional soil health indicators (open data)", "kind": "regional"},
        "peer": "Peers introduced legume cover crops funded through Premium and reported firmer yields "
                "within two cycles.",
        "peer_src": {"label": "Fair Trade Premium project (sample) PROJ-7A5D", "kind": "peer"},
        "clause": "APS 3.2 (soil and land management)",
    },
}

_FALLBACK = {
    "insight": "I don't have strong regional data on that exact issue yet, so I'll be honest about the gap "
               "rather than guess.",
    "insight_src": {"label": "No matching dataset in this session", "kind": "regional"},
    "peer": "I also don't have a close peer example on file for it right now.",
    "peer_src": {"label": "No matching peer project", "kind": "peer"},
    "clause": "APS (general certification standard)",
}

_SUGGESTIONS = {
    "en": ["What does the rainfall data show for my area?",
           "How have similar cooperatives used the Premium?",
           "What do the standards say about this?",
           "Can you summarize this for my records?"],
    "es": ["¿Qué muestran los datos de lluvia para mi zona?",
           "¿Cómo han usado la Prima cooperativas parecidas?",
           "¿Qué dicen las normas sobre esto?",
           "¿Puedes resumir esto para mi registro?"],
    "fr": ["Que montrent les données de pluie pour ma zone ?",
           "Comment des coopératives similaires ont-elles utilisé la Prime ?",
           "Que disent les normes à ce sujet ?",
           "Peux-tu résumer ceci pour mon dossier ?"],
    "pt": ["O que os dados de chuva mostram para a minha área?",
           "Como cooperativas parecidas usaram o Prêmio?",
           "O que as normas dizem sobre isso?",
           "Pode resumir isso para o meu registro?"],
    "sw": ["Data ya mvua inaonyesha nini kwa eneo langu?",
           "Vyama vya ushirika kama changu vimetumiaje Premium?",
           "Viwango vinasemaje kuhusu hili?",
           "Unaweza kufupisha hili kwa kumbukumbu zangu?"],
    "hi": ["मेरे क्षेत्र के लिए वर्षा के आँकड़े क्या दिखाते हैं?",
           "समान सहकारी समितियों ने प्रीमियम का उपयोग कैसे किया?",
           "मानक इस बारे में क्या कहते हैं?",
           "क्या आप इसे मेरे रिकॉर्ड के लिए सारांशित कर सकते हैं?"],
}


def opening(persona: Persona, language: str) -> str:
    copy = _COPY.get(language, _COPY["en"])
    focus = catalog_focus(persona)
    return copy["greeting"].format(name=persona.name.split()[0], focus=focus, region=persona.location.place)


def catalog_focus(persona: Persona) -> str:
    """A short natural phrase for the persona's focus, used in the greeting."""
    if persona.role == "consumer":
        return persona.product
    labels = {"coffee": "coffee", "seafood": "fishing", "rice": "rice", "cocoa": "cocoa", "groceries": "groceries"}
    return labels.get(persona.product, persona.product)


def starter_suggestions(language: str) -> list[str]:
    return list(_SUGGESTIONS.get(language, _SUGGESTIONS["en"]))


def _match_topic(text: str) -> tuple[str, dict]:
    low = text.lower()
    for key, topic in _TOPICS.items():
        if any(term in low for term in topic["match"]):
            return key, topic
    return "general", _FALLBACK


# E5: a gentle, non-clinical sentiment read of the producer's message.
_NEG = ("difficult", "hard", "worried", "struggl", "lost", "drop", "short", "fail", "late",
        "problema", "difícil", "preocup", "perd", "difficile", "inquiet")
_POS = ("better", "improved", "good", "hopeful", "grateful", "mejor", "bien", "mieux")


def _sentiment(message: str) -> str:
    low = message.lower()
    if any(t in low for t in _NEG):
        return "concerned"
    if any(t in low for t in _POS):
        return "encouraged"
    return "neutral"


def _bedrock_answer(message: str, persona: Persona, language: str, topic: dict, copy: dict) -> str | None:
    """Optional live path: ask Amazon Bedrock to phrase the grounded answer. Falls back to the mock
    text on any error, so the demo never breaks. Model access goes only through Bedrock (tech-env rule)."""
    from django.conf import settings
    if not getattr(settings, "USE_BEDROCK", False):
        return None
    try:
        import boto3
        client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
        lang_name = LANGUAGES.get(language, "English")
        system = (
            "You are the Fair Trade Exchange assistant. "
            "Reply in " + lang_name + ". Use ONLY the two evidence points provided; do not invent facts. "
            "Phrase everything as suggestions, never commands (no 'you should'/'you must'). "
            "End by handing the decision back to the producer and their cooperative. Keep it to 4 short sentences."
        )
        prompt = (
            f"Person: {persona.name}, a {persona.role} ({persona.product}) in {persona.location.place}.\n"
            f"They said: {message}\n"
            f"Evidence 1 (regional data): {topic['insight']}\n"
            f"Evidence 2 (peer example): {topic['peer']}\n"
            "Write the reply now."
        )
        resp = client.converse(
            modelId=settings.BEDROCK_MODEL_ID,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0.3},
        )
        return resp["output"]["message"]["content"][0]["text"]
    except Exception:
        return None


def respond(message: str, persona: Persona, language: str) -> Answer:
    """Produce one grounded, suggestion-toned answer in the chosen language. Mock by default;
    uses Amazon Bedrock when USE_BEDROCK=1 (with a safe fallback to the mock text)."""
    language = language if language in _COPY else "en"
    copy = _COPY[language]

    in_scope, _reason = guardrails.scope_verdict(message)
    pii = guardrails.pii_flags(message)

    if not in_scope:
        return Answer(
            text=copy["scope_redirect"],
            suggestions=starter_suggestions(language),
            pii_flagged=pii,
            in_scope=False,
            language=language,
        )

    tag, topic = _match_topic(message)
    # Make the regional insight location-aware using the persona's (made-up) weather overlay.
    topic = dict(topic)
    w = persona.weather
    topic["insight"] = (f"In {persona.location.place}, recent conditions are {w.summary.lower()} "
                        f"(about {w.temp_c}°C, rainfall {w.rain_vs_normal}, water stress {w.water_stress.lower()}). "
                        + topic["insight"])
    live = _bedrock_answer(message, persona, language, topic, copy)
    if live:
        body = live
    else:
        body = f"{copy['evidence_lead']}\n\n• {topic['insight']}\n• {topic['peer']}\n\n{copy['handback']}"
    body = guardrails.to_suggestion_tone(body)
    if pii:
        body = f"{copy['pii_note']}\n\n{body}"

    return Answer(
        text=body,
        citations=[
            {"label": topic["insight_src"]["label"], "kind": topic["insight_src"]["kind"]},
            {"label": topic["peer_src"]["label"], "kind": topic["peer_src"]["kind"]},
            {"label": topic["clause"], "kind": "standard"},
        ],
        suggestions=starter_suggestions(language),
        pii_flagged=pii,
        in_scope=True,
        language=language,
        sentiment=_sentiment(message),
        tags=[tag] if tag != "general" else [],
    )
