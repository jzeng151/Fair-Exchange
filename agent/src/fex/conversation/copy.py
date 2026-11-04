"""Fixed text FEX shows in the producer's language (issue #13).

In `respond`, the only model-written text shown is checked claims. Everything else here is fixed,
so it can be reviewed once (tone: enablement, never directive). Unknown languages fall back to English.
"""

COPY = {
    "en": {
        "out_of_scope_other_producer_data": "I can't share another producer's records or conversations; each producer's information stays theirs.",
        "out_of_scope_certification_status": "I can't help with certification status or audit results; that isn't part of what I do.",
        "out_of_scope_grievance": "I'm not the right channel for complaints or grievances, so I can't take this here.",
        "back_to_open": "If you'd like, we can go back to it: what has been difficult for you?",
        "respond_opening": "Here is what I found. Each point shows where it comes from.",
        "no_insights": "I don't have data on this for your region yet.",
        "no_peers": "I haven't found examples from comparable producers yet.",
        "hand_back": "This is information to help you decide. You and your committee know your situation best.",
        "location_kept": "I'll use the location on file ({place}). Fair Trade USA can update it if it's wrong.",
        "failed": "Something went wrong while I was answering. You can try again.",
        "closed": "This conversation has ended.",
        "invalid": "That option isn't available right now.",
    },
    "es": {
        "out_of_scope_other_producer_data": "No puedo compartir registros ni conversaciones de otros productores; la información de cada productor es suya.",
        "out_of_scope_certification_status": "No puedo ayudar con el estado de la certificación ni con resultados de auditoría; eso no es parte de lo que hago.",
        "out_of_scope_grievance": "No soy el canal adecuado para quejas o reclamos, así que no puedo recibirlo aquí.",
        "back_to_open": "Si quiere, podemos volver a lo suyo: ¿qué ha sido difícil para usted?",
        "respond_opening": "Esto es lo que encontré. Cada punto muestra de dónde viene.",
        "no_insights": "Todavía no tengo datos sobre esto para su región.",
        "no_peers": "Todavía no encontré ejemplos de productores comparables.",
        "hand_back": "Esta información es para ayudarle a decidir. Usted y su comité conocen mejor su situación.",
        "location_kept": "Usaré la ubicación registrada ({place}). Fair Trade USA puede actualizarla si no es correcta.",
        "failed": "Algo falló mientras respondía. Puede intentarlo de nuevo.",
        "closed": "Esta conversación terminó.",
        "invalid": "Esa opción no está disponible ahora.",
    },
    "fr": {
        "out_of_scope_other_producer_data": "Je ne peux pas partager les dossiers ou les conversations d'autres producteurs ; les informations de chaque producteur lui appartiennent.",
        "out_of_scope_certification_status": "Je ne peux pas aider pour le statut de certification ou les résultats d'audit ; cela ne fait pas partie de mon rôle.",
        "out_of_scope_grievance": "Je ne suis pas le bon canal pour les plaintes ou réclamations, je ne peux donc pas les recevoir ici.",
        "back_to_open": "Si vous voulez, nous pouvons y revenir : qu'est-ce qui a été difficile pour vous ?",
        "respond_opening": "Voici ce que j'ai trouvé. Chaque point indique sa source.",
        "no_insights": "Je n'ai pas encore de données à ce sujet pour votre région.",
        "no_peers": "Je n'ai pas encore trouvé d'exemples de producteurs comparables.",
        "hand_back": "Ces informations sont là pour vous aider à décider. Vous et votre comité connaissez le mieux votre situation.",
        "location_kept": "J'utiliserai la localisation enregistrée ({place}). Fair Trade USA peut la mettre à jour si elle est incorrecte.",
        "failed": "Un problème est survenu pendant ma réponse. Vous pouvez réessayer.",
        "closed": "Cette conversation est terminée.",
        "invalid": "Cette option n'est pas disponible pour le moment.",
    },
}


def text(language: str, key: str, **values: str) -> str:
    return COPY.get(language, COPY["en"])[key].format(**values)
