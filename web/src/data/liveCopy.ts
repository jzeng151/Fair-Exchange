// Live mode (#116): the button and status text around FEX's own words, in the conversation's language.
// FEX's messages come from the agent; only these labels live in the web app. Wording follows the specs:
// "That's right" / "Correct this" on the playback, "Stop" before consent and "End conversation" after (#13),
// the three consent choices (#19) and the three feedback answers (#23).
export type LiveLang = 'en' | 'es' | 'fr'

export interface LiveCopy {
  start: string; send: string; placeholder: string; correctPlaceholder: string
  confirm: string; correct: string; reopen: string; retry: string
  stop: string; end: string; endConfirm: string
  consentAsk: string; consent: { internal: string; internal_and_outward: string; declined: string }
  yourChoice: string; change: string
  feedbackAsk: string; feedbackThanks: string; yourAnswer: string; feedback: { yes: string; somewhat: string; no: string }
  insights: string; peers: string; source: string; standard: string
  /** #169: who can see what, under each consent choice; and the TNFD note on WRI Aqueduct sources.
   *  A decline keeps no summary (#19), but the conversation stays in AgentCore Memory until it expires:
   *  the "7 days" here and in declinedSaved must match MEMORY_EVENT_EXPIRY_DAYS in infra/lib/fair-exchange-stack.ts. */
  consentExplain: { internal: string; internal_and_outward: string; declined: string }
  tnfd: string
  listen: string; stopListening: string; listenUnavailable: string
  strength: { exact: string; nearest: string; limited: string }
  limited: string; saved: (v: number) => string; declinedSaved: string; closed: string; working: string
  errors: { unreachable: string; busy: string; notFound: string; signIn: string; other: string }
}

export const liveCopy: Record<LiveLang, LiveCopy> = {
  en: {
    start: 'Start a conversation', send: 'Send', placeholder: 'Type a message…', correctPlaceholder: 'Type what I should change…',
    confirm: 'That’s right', correct: 'Correct this', reopen: 'Change my description', retry: 'Try again',
    stop: 'Stop', end: 'End conversation', endConfirm: 'End this conversation? You can’t continue it afterwards.',
    consentAsk: 'May Fair Trade USA keep a summary of this conversation?',
    consent: { internal: 'Yes, for Fair Trade USA only', internal_and_outward: 'Yes, and it may be shared (combined with others)', declined: 'No, don’t keep it' },
    consentExplain: { internal: 'For Fair Trade USA only: the Fair Trade USA team can read it to improve support.', internal_and_outward: 'Shared: other producers and partners only ever see it combined with others, never with your name.', declined: 'Don’t keep it: no summary is saved for Fair Trade USA, only that you said no. The conversation itself is deleted automatically after 7 days.' },
    tnfd: 'Listed in the TNFD Tools Catalogue',
    listen: '🔊 Listen', stopListening: '■ Stop', listenUnavailable: 'Reading aloud isn’t available in this browser.',
    yourChoice: 'Your choice', change: 'Change',
    feedbackAsk: 'Was this helpful?', feedbackThanks: 'Thank you.', yourAnswer: 'Your answer', feedback: { yes: 'Yes', somewhat: 'Somewhat', no: 'No' },
    insights: 'What the data shows', peers: 'What others have tried', source: 'Source', standard: 'Standard',
    strength: { exact: 'exact match', nearest: 'nearest match', limited: 'limited evidence' },
    limited: 'There was only limited evidence for this situation.',
    saved: (v) => `Saved (version ${v}).`, declinedSaved: 'Noted: no summary of this conversation is saved. The conversation itself is deleted automatically after 7 days.',
    closed: 'This conversation has ended.', working: 'FEX is working…',
    errors: { unreachable: 'Can’t reach FEX right now. Check that the chat API is running, then try again.', busy: 'FEX is still answering your last message. Please wait a moment.', notFound: 'That conversation wasn’t found. Start a new one.', signIn: 'The demo passcode wasn’t accepted. Go back, check the passcode, and choose the scenario again.', other: 'Something went wrong. Please try again.' },
  },
  es: {
    start: 'Iniciar una conversación', send: 'Enviar', placeholder: 'Escriba un mensaje…', correctPlaceholder: 'Escriba qué debo cambiar…',
    confirm: 'Es correcto', correct: 'Corregir', reopen: 'Cambiar mi descripción', retry: 'Intentar de nuevo',
    stop: 'Detener', end: 'Terminar la conversación', endConfirm: '¿Terminar esta conversación? Después no podrá continuarla.',
    consentAsk: '¿Puede Fair Trade USA guardar un resumen de esta conversación?',
    consent: { internal: 'Sí, solo para Fair Trade USA', internal_and_outward: 'Sí, y se puede compartir (junto con otros)', declined: 'No, no guardarlo' },
    consentExplain: { internal: 'Solo para Fair Trade USA: el equipo de Fair Trade USA puede leerlo para mejorar el apoyo.', internal_and_outward: 'Compartido: otros productores y socios solo lo ven junto con otros, nunca con su nombre.', declined: 'No guardarlo: no se guarda ningún resumen para Fair Trade USA, solo que usted dijo que no. La conversación se borra automáticamente después de 7 días.' },
    tnfd: 'Incluido en el catálogo de herramientas de la TNFD',
    listen: '🔊 Escuchar', stopListening: '■ Detener', listenUnavailable: 'La lectura en voz alta no está disponible en este navegador.',
    yourChoice: 'Su elección', change: 'Cambiar',
    feedbackAsk: '¿Le fue útil?', feedbackThanks: 'Gracias.', yourAnswer: 'Su respuesta', feedback: { yes: 'Sí', somewhat: 'Algo', no: 'No' },
    insights: 'Lo que muestran los datos', peers: 'Lo que otros han probado', source: 'Fuente', standard: 'Estándar',
    strength: { exact: 'coincidencia exacta', nearest: 'coincidencia cercana', limited: 'evidencia limitada' },
    limited: 'Solo había evidencia limitada para esta situación.',
    saved: (v) => `Guardado (versión ${v}).`, declinedSaved: 'Entendido: no se guarda ningún resumen de esta conversación. La conversación se borra automáticamente después de 7 días.',
    closed: 'Esta conversación ha terminado.', working: 'FEX está trabajando…',
    errors: { unreachable: 'No se puede contactar a FEX ahora. Revise que la API del chat esté funcionando e intente de nuevo.', busy: 'FEX todavía está respondiendo su último mensaje. Espere un momento.', notFound: 'No se encontró esa conversación. Inicie una nueva.', signIn: 'No se aceptó el código de acceso de la demo. Vuelva atrás, revise el código y elija el escenario de nuevo.', other: 'Algo salió mal. Intente de nuevo.' },
  },
  fr: {
    start: 'Commencer une conversation', send: 'Envoyer', placeholder: 'Écrivez un message…', correctPlaceholder: 'Écrivez ce que je dois changer…',
    confirm: 'C’est exact', correct: 'Corriger', reopen: 'Modifier ma description', retry: 'Réessayer',
    stop: 'Arrêter', end: 'Terminer la conversation', endConfirm: 'Terminer cette conversation ? Vous ne pourrez plus la continuer.',
    consentAsk: 'Fair Trade USA peut-il conserver un résumé de cette conversation ?',
    consent: { internal: 'Oui, pour Fair Trade USA seulement', internal_and_outward: 'Oui, et il peut être partagé (avec d’autres)', declined: 'Non, ne pas le conserver' },
    consentExplain: { internal: 'Pour Fair Trade USA seulement : l’équipe de Fair Trade USA peut le lire pour améliorer son soutien.', internal_and_outward: 'Partagé : les autres producteurs et partenaires ne le voient que regroupé avec d’autres, jamais avec votre nom.', declined: 'Ne pas le conserver : aucun résumé n’est enregistré pour Fair Trade USA, seulement votre refus. La conversation elle-même est supprimée automatiquement après 7 jours.' },
    tnfd: 'Répertorié dans le catalogue d’outils de la TNFD',
    listen: '🔊 Écouter', stopListening: '■ Arrêter', listenUnavailable: 'La lecture à voix haute n’est pas disponible dans ce navigateur.',
    yourChoice: 'Votre choix', change: 'Modifier',
    feedbackAsk: 'Cela vous a-t-il été utile ?', feedbackThanks: 'Merci.', yourAnswer: 'Votre réponse', feedback: { yes: 'Oui', somewhat: 'Un peu', no: 'Non' },
    insights: 'Ce que montrent les données', peers: 'Ce que d’autres ont essayé', source: 'Source', standard: 'Norme',
    strength: { exact: 'correspondance exacte', nearest: 'correspondance proche', limited: 'preuves limitées' },
    limited: 'Il n’y avait que des preuves limitées pour cette situation.',
    saved: (v) => `Enregistré (version ${v}).`, declinedSaved: 'Noté : aucun résumé de cette conversation n’est enregistré. La conversation elle-même est supprimée automatiquement après 7 jours.',
    closed: 'Cette conversation est terminée.', working: 'FEX travaille…',
    errors: { unreachable: 'Impossible de joindre FEX pour le moment. Vérifiez que l’API du chat fonctionne, puis réessayez.', busy: 'FEX répond encore à votre dernier message. Patientez un instant.', notFound: 'Cette conversation est introuvable. Commencez-en une nouvelle.', signIn: 'Le code d’accès de la démo n’a pas été accepté. Revenez en arrière, vérifiez le code et choisissez à nouveau le scénario.', other: 'Un problème est survenu. Réessayez.' },
  },
}

export const copyFor = (language: string): LiveCopy => liveCopy[(language in liveCopy ? language : 'en') as LiveLang]
