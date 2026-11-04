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
  feedbackAsk: string; feedback: { yes: string; somewhat: string; no: string }
  insights: string; peers: string; source: string; standard: string
  strength: { exact: string; nearest: string; limited: string }
  limited: string; saved: (v: number) => string; declinedSaved: string; closed: string; working: string
  errors: { unreachable: string; busy: string; notFound: string; other: string }
}

export const liveCopy: Record<LiveLang, LiveCopy> = {
  en: {
    start: 'Start a conversation', send: 'Send', placeholder: 'Type a message…', correctPlaceholder: 'Type what I should change…',
    confirm: 'That’s right', correct: 'Correct this', reopen: 'Change my description', retry: 'Try again',
    stop: 'Stop', end: 'End conversation', endConfirm: 'End this conversation? You can’t continue it afterwards.',
    consentAsk: 'May Fair Trade USA keep a summary of this conversation?',
    consent: { internal: 'Yes, for Fair Trade USA only', internal_and_outward: 'Yes, and it may be shared (combined with others)', declined: 'No, don’t keep it' },
    yourChoice: 'Your choice', change: 'Change',
    feedbackAsk: 'Was this helpful?', feedback: { yes: 'Yes', somewhat: 'Somewhat', no: 'No' },
    insights: 'What the data shows', peers: 'What others have tried', source: 'Source', standard: 'Standard',
    strength: { exact: 'exact match', nearest: 'nearest match', limited: 'limited evidence' },
    limited: 'There was only limited evidence for this situation.',
    saved: (v) => `Saved (version ${v}).`, declinedSaved: 'Noted: nothing from this conversation is kept.',
    closed: 'This conversation has ended.', working: 'FEX is working…',
    errors: { unreachable: 'Can’t reach FEX right now. Check that the chat API is running, then try again.', busy: 'FEX is still answering your last message. Please wait a moment.', notFound: 'That conversation wasn’t found. Start a new one.', other: 'Something went wrong. Please try again.' },
  },
  es: {
    start: 'Iniciar una conversación', send: 'Enviar', placeholder: 'Escriba un mensaje…', correctPlaceholder: 'Escriba qué debo cambiar…',
    confirm: 'Es correcto', correct: 'Corregir', reopen: 'Cambiar mi descripción', retry: 'Intentar de nuevo',
    stop: 'Detener', end: 'Terminar la conversación', endConfirm: '¿Terminar esta conversación? Después no podrá continuarla.',
    consentAsk: '¿Puede Fair Trade USA guardar un resumen de esta conversación?',
    consent: { internal: 'Sí, solo para Fair Trade USA', internal_and_outward: 'Sí, y se puede compartir (junto con otros)', declined: 'No, no guardarlo' },
    yourChoice: 'Su elección', change: 'Cambiar',
    feedbackAsk: '¿Le fue útil?', feedback: { yes: 'Sí', somewhat: 'Algo', no: 'No' },
    insights: 'Lo que muestran los datos', peers: 'Lo que otros han probado', source: 'Fuente', standard: 'Estándar',
    strength: { exact: 'coincidencia exacta', nearest: 'coincidencia cercana', limited: 'evidencia limitada' },
    limited: 'Solo había evidencia limitada para esta situación.',
    saved: (v) => `Guardado (versión ${v}).`, declinedSaved: 'Entendido: no se guarda nada de esta conversación.',
    closed: 'Esta conversación ha terminado.', working: 'FEX está trabajando…',
    errors: { unreachable: 'No se puede contactar a FEX ahora. Revise que la API del chat esté funcionando e intente de nuevo.', busy: 'FEX todavía está respondiendo su último mensaje. Espere un momento.', notFound: 'No se encontró esa conversación. Inicie una nueva.', other: 'Algo salió mal. Intente de nuevo.' },
  },
  fr: {
    start: 'Commencer une conversation', send: 'Envoyer', placeholder: 'Écrivez un message…', correctPlaceholder: 'Écrivez ce que je dois changer…',
    confirm: 'C’est exact', correct: 'Corriger', reopen: 'Modifier ma description', retry: 'Réessayer',
    stop: 'Arrêter', end: 'Terminer la conversation', endConfirm: 'Terminer cette conversation ? Vous ne pourrez plus la continuer.',
    consentAsk: 'Fair Trade USA peut-il conserver un résumé de cette conversation ?',
    consent: { internal: 'Oui, pour Fair Trade USA seulement', internal_and_outward: 'Oui, et il peut être partagé (avec d’autres)', declined: 'Non, ne pas le conserver' },
    yourChoice: 'Votre choix', change: 'Modifier',
    feedbackAsk: 'Cela vous a-t-il été utile ?', feedback: { yes: 'Oui', somewhat: 'Un peu', no: 'Non' },
    insights: 'Ce que montrent les données', peers: 'Ce que d’autres ont essayé', source: 'Source', standard: 'Norme',
    strength: { exact: 'correspondance exacte', nearest: 'correspondance proche', limited: 'preuves limitées' },
    limited: 'Il n’y avait que des preuves limitées pour cette situation.',
    saved: (v) => `Enregistré (version ${v}).`, declinedSaved: 'Noté : rien de cette conversation n’est conservé.',
    closed: 'Cette conversation est terminée.', working: 'FEX travaille…',
    errors: { unreachable: 'Impossible de joindre FEX pour le moment. Vérifiez que l’API du chat fonctionne, puis réessayez.', busy: 'FEX répond encore à votre dernier message. Patientez un instant.', notFound: 'Cette conversation est introuvable. Commencez-en une nouvelle.', other: 'Un problème est survenu. Réessayez.' },
  },
}

export const copyFor = (language: string): LiveCopy => liveCopy[(language in liveCopy ? language : 'en') as LiveLang]
