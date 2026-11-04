// GENERATED FILE. Do not edit by hand.
// Source: agent/src/fex/conversation/contract.py  ->  agent/scripts/generate_types.py
// schema-sha256: 02e1e54fb9ed20884a8348a563799719a409e835173076cb885aaefe28cc90eb
// body-sha256: 65f3c785281419ae52747a66ab014b9b61138f5fa0dc1367e416ca6fda7d0bca
// end-of-banner
export type Event =
  TextEvent | ClaimEvent | AnswerEvent | StepEvent | ActionsEvent | RecordSavedEvent | ErrorEvent | DoneEvent;
/**
 * Increasing within one turn
 */
export type Seq = number;
export type Text = string;
export type Type = "text";
/**
 * Time period of the data, if any
 */
export type Period = string | null;
/**
 * Dataset, record or document the fact came from
 */
export type Source = string;
/**
 * Related APS/FPS clause, e.g. 'APS 3.2.1'
 */
export type StandardClause = string;
/**
 * How well the evidence matches this producer's area
 */
export type Strength = "exact" | "nearest" | "limited";
export type Text1 = string;
export type Section = "insights" | "peer_examples";
/**
 * Increasing within one turn
 */
export type Seq1 = number;
export type Type1 = "claim";
export type Evidence = "full" | "limited";
export type Insights = Claim[];
export type PeerExamples = Claim[];
/**
 * Increasing within one turn
 */
export type Seq2 = number;
export type Type2 = "answer";
export type Language = string;
/**
 * Increasing within one turn
 */
export type Seq3 = number;
export type Step = "intake" | "playback" | "respond" | "consent" | "feedback" | "closed";
export type Type3 = "step";
export type Allowed = (
  "confirm_playback" | "correct_playback" | "reopen_playback" | "retry_answer" | "set_consent" | "set_feedback" | "end"
)[];
export type Language1 = string;
/**
 * Increasing within one turn
 */
export type Seq4 = number;
export type Type4 = "actions";
export type ConsentScope = ("internal" | "internal_and_outward" | "declined") | null;
/**
 * Increasing within one turn
 */
export type Seq5 = number;
export type Status = "completed" | "declined";
export type Type5 = "record_saved";
export type Version = number;
export type Code = "agent_failed" | "invalid_action" | "closed";
export type Message = string;
/**
 * Increasing within one turn
 */
export type Seq6 = number;
export type Type6 = "error";
/**
 * Increasing within one turn
 */
export type Seq7 = number;
export type Type7 = "done";
export type Request = StartRequest | MessageRequest | ActionRequest | ResumeRequest | AutoCloseRequest;
/**
 * Set by the chat API
 */
export type Conversationid = string;
export type Kind = "start";
/**
 * Set by the chat API from the identity
 */
export type Producerid = string;
/**
 * Set by the chat API
 */
export type Conversationid1 = string;
export type Kind1 = "message";
/**
 * Set by the chat API from the identity
 */
export type Producerid1 = string;
export type Text2 = string;
export type Action = ConfirmPlayback | CorrectPlayback | ReopenPlayback | RetryAnswer | SetConsent | SetFeedback | End;
export type Name = "confirm_playback";
export type Text3 = string;
export type Name1 = "correct_playback";
export type Name2 = "reopen_playback";
export type Name3 = "retry_answer";
export type Scope = "internal" | "internal_and_outward" | "declined";
export type Name4 = "set_consent";
export type Value = "yes" | "somewhat" | "no";
export type Name5 = "set_feedback";
export type Name6 = "end";
/**
 * Set by the chat API
 */
export type Conversationid2 = string;
export type Kind2 = "action";
/**
 * Set by the chat API from the identity
 */
export type Producerid2 = string;
/**
 * Set by the chat API
 */
export type Conversationid3 = string;
export type Kind3 = "resume";
/**
 * Set by the chat API from the identity
 */
export type Producerid3 = string;
/**
 * Set by the chat API
 */
export type Conversationid4 = string;
export type Kind4 = "auto_close";
/**
 * Set by the chat API from the identity
 */
export type Producerid4 = string;
export type Reason = "inactivity" | "max_lifetime";
export type Allowed1 = (
  "confirm_playback" | "correct_playback" | "reopen_playback" | "retry_answer" | "set_consent" | "set_feedback" | "end"
)[];
export type Evidence1 = "full" | "limited";
export type Insights1 = Claim[];
export type PeerExamples1 = Claim[];
export type At = string;
export type Role = "producer" | "fex";
export type Text4 = string;
export type At1 = string;
export type Name7 =
  "confirm_playback" | "correct_playback" | "reopen_playback" | "retry_answer" | "set_consent" | "set_feedback" | "end";
export type Role1 = "action";
export type History = (SpokenEntry | ActionEntry)[];
export type Language2 = string;
export type Step1 = "intake" | "playback" | "respond" | "consent" | "feedback" | "closed";

/**
 * Requests, actions and events between the chat API and the agent. Generated from agent/src/fex/conversation/contract.py; do not edit by hand.
 */
export interface ConversationContract {
  event: Event;
  request: Request;
  resume: ResumeResponse;
}
export interface TextEvent {
  seq: Seq;
  text: Text;
  type: Type;
}
export interface ClaimEvent {
  claim: Claim;
  section: Section;
  seq: Seq1;
  type: Type1;
}
/**
 * One insight or peer example given to the producer, with its citation.
 */
export interface Claim {
  citation: Citation;
  text: Text1;
}
/**
 * Where a claim comes from. Every insight and peer example must carry one.
 */
export interface Citation {
  period?: Period;
  source: Source;
  standard_clause: StandardClause;
  strength?: Strength;
}
export interface AnswerEvent {
  evidence: Evidence;
  insights: Insights;
  peer_examples: PeerExamples;
  seq: Seq2;
  type: Type2;
}
export interface StepEvent {
  language: Language;
  seq: Seq3;
  step: Step;
  type: Type3;
}
export interface ActionsEvent {
  allowed: Allowed;
  language: Language1;
  seq: Seq4;
  type: Type4;
}
export interface RecordSavedEvent {
  consent_scope: ConsentScope;
  seq: Seq5;
  status: Status;
  type: Type5;
  version: Version;
}
export interface ErrorEvent {
  code: Code;
  message: Message;
  seq: Seq6;
  type: Type6;
}
export interface DoneEvent {
  seq: Seq7;
  type: Type7;
}
export interface StartRequest {
  conversationId: Conversationid;
  kind: Kind;
  producerId: Producerid;
}
export interface MessageRequest {
  conversationId: Conversationid1;
  kind: Kind1;
  producerId: Producerid1;
  text: Text2;
}
export interface ActionRequest {
  action: Action;
  conversationId: Conversationid2;
  kind: Kind2;
  producerId: Producerid2;
}
export interface ConfirmPlayback {
  args?: NoArgs;
  name: Name;
}
export interface NoArgs {}
export interface CorrectPlayback {
  args: CorrectPlaybackArgs;
  name: Name1;
}
export interface CorrectPlaybackArgs {
  text: Text3;
}
export interface ReopenPlayback {
  args?: NoArgs;
  name: Name2;
}
export interface RetryAnswer {
  args?: NoArgs;
  name: Name3;
}
export interface SetConsent {
  args: SetConsentArgs;
  name: Name4;
}
export interface SetConsentArgs {
  scope: Scope;
}
export interface SetFeedback {
  args: SetFeedbackArgs;
  name: Name5;
}
export interface SetFeedbackArgs {
  value: Value;
}
export interface End {
  args?: NoArgs;
  name: Name6;
}
export interface ResumeRequest {
  conversationId: Conversationid3;
  kind: Kind3;
  producerId: Producerid3;
}
export interface AutoCloseRequest {
  conversationId: Conversationid4;
  kind: Kind4;
  producerId: Producerid4;
  reason: Reason;
}
export interface ResumeResponse {
  allowed: Allowed1;
  answer: Answer | null;
  history: History;
  language: Language2;
  step: Step1;
}
export interface Answer {
  evidence: Evidence1;
  insights: Insights1;
  peer_examples: PeerExamples1;
}
export interface SpokenEntry {
  at: At;
  role: Role;
  text: Text4;
}
export interface ActionEntry {
  args: Args;
  at: At1;
  name: Name7;
  role: Role1;
}
export interface Args {
  [k: string]: unknown;
}
