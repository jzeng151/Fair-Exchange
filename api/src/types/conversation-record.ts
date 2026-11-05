// GENERATED FILE. Do not edit by hand.
// Source: agent/src/fex/models.py  ->  agent/scripts/generate_types.py
// schema-sha256: 27c6d1d4c9c0a53afa0410f40f7fd01decdc4871c08a16c9b22bd5ab85707dbe
// body-sha256: 2e0b15e60c0d222bf9ff8533aa4fa93732735dd9d81335fdd359b5315c8c8346
// end-of-banner
/**
 * One record per Fair Exchange conversation. Generated from agent/src/fex/models.py; do not edit by hand.
 */
export type ConversationRecord = CompletedRecord | DeclinedRecord;
export type InputTokens = number;
export type ModelId = string;
export type OutputTokens = number;
/**
 * Tokens per model for this conversation (AI footprint)
 */
export type AiUsage = ModelUsage[];
/**
 * Set when the conversation closes. Records are reviewable only when set.
 */
export type ClosedAt = string | null;
export type RecordedAt = string;
export type Scope = "internal" | "internal_and_outward";
export type RecordedAt1 = string;
export type Scope1 = "internal" | "internal_and_outward" | "declined";
/**
 * The producer's distinct consent choices, in order
 */
export type ConsentHistory = ConsentChoice[];
export type CreatedAt = string;
export type At = string;
export type Code = string;
export type Kind = "step" | "tool" | "verifier" | "pii";
export type Refs = string[];
/**
 * The agent's reasoning trail for reviewers, oldest first (#26)
 */
export type DecisionLog = DecisionLogEntry[];
/**
 * null for an interrupted answer, which never finished
 */
export type Evidence = ("full" | "limited") | null;
export type GivenAt = string;
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
export type Text = string;
export type Insights = Claim[];
export type PeerExamples = Claim[];
export type Reason = "reopened" | "interrupted";
/**
 * Answers shown and later replaced, oldest first
 */
export type EarlierAnswers = EarlierAnswer[];
/**
 * e.g. cooperative, smallholder, hired-labor farm, processor
 */
export type EntityType = string;
/**
 * limited when the shown answer had no insights or no peer examples
 */
export type Evidence1 = "full" | "limited";
/**
 * Was the guidance helpful?
 */
export type Feedback = ("yes" | "somewhat" | "no") | null;
/**
 * What the data shows, as given to the producer
 */
export type Insights1 = Claim[];
/**
 * ISO 639-1 code of the producer's language, e.g. 'es'
 */
export type Language = string;
/**
 * What others tried, as given to the producer
 */
export type PeerExamples1 = Claim[];
/**
 * Scan result: None until the first scan ran; unsupported_language covers languages other than en and es
 */
export type PiiCheck = ("done" | "failed" | "unsupported_language") | null;
/**
 * Types found across the conversation, in first-seen order
 */
export type PiiEntityTypes = ("NAME" | "PHONE" | "EMAIL" | "ADDRESS")[];
/**
 * Personal information flagged for human review; never redacted
 */
export type PiiFlag = boolean;
/**
 * Up to 10 words before and after the match
 */
export type Context = string;
/**
 * Only these four types are looked for
 */
export type EntityType1 = "NAME" | "PHONE" | "EMAIL" | "ADDRESS";
/**
 * When the text containing the match was said
 */
export type MessageAt = string;
/**
 * The matched words; kept for review, never redacted or logged
 */
export type Text1 = string;
/**
 * Every match found across scanned texts; matches are removed if the record turns declined
 */
export type PiiMatches = PiiMatch[];
/**
 * Reviewer decision on the PII flag
 */
export type PiiReview = ("confirmed" | "cleared") | null;
/**
 * Set from the session, never from the conversation
 */
export type ProducerId = string;
export type RecordId = string;
export type ReviewStatus = "pending" | "reviewed";
export type ReviewedAt = string | null;
export type ReviewedBy = string | null;
/**
 * Reviewer's corrected English summary
 */
export type ReviewerSummaryEnglish = string | null;
/**
 * Reviewer's corrected summary in the producer's language
 */
export type ReviewerSummaryOriginal = string | null;
/**
 * Reviewer's corrected tags
 */
export type ReviewerTags =
  | (
      | "climate and weather"
      | "water"
      | "soil and land"
      | "market and price"
      | "labor and migration"
      | "financial and access to capital"
      | "education"
      | "health"
      | "infrastructure"
      | "biodiversity and conservation"
      | "social and community"
    )[]
  | null;
/**
 * Never confused with mandatory or compliance reporting data
 */
export type Source1 = "agent conversation";
export type Status = "completed";
/**
 * English version; required for non-English conversations
 */
export type SummaryEnglish = string | null;
/**
 * The challenge in the producer's own words and language
 */
export type SummaryOriginal = string;
/**
 * Challenge tags from the 11-tag set (the agent's)
 *
 * @minItems 1
 */
export type Tags = [
  (
    | "climate and weather"
    | "water"
    | "soil and land"
    | "market and price"
    | "labor and migration"
    | "financial and access to capital"
    | "education"
    | "health"
    | "infrastructure"
    | "biodiversity and conservation"
    | "social and community"
  ),
  ...(
    | "climate and weather"
    | "water"
    | "soil and land"
    | "market and price"
    | "labor and migration"
    | "financial and access to capital"
    | "education"
    | "health"
    | "infrastructure"
    | "biodiversity and conservation"
    | "social and community"
  )[]
];
/**
 * Time of the latest save
 */
export type UpdatedAt = string;
/**
 * Starts at 1; incremented on every save; used for conditional writes
 */
export type Version = number;
/**
 * Tokens per model for this conversation (AI footprint)
 */
export type AiUsage1 = ModelUsage[];
/**
 * Set when the conversation closes. Records are reviewable only when set.
 */
export type ClosedAt1 = string | null;
export type RecordedAt2 = string;
export type Scope2 = "declined";
/**
 * The producer's distinct consent choices, in order
 */
export type ConsentHistory1 = ConsentChoice[];
export type CreatedAt1 = string;
/**
 * Set from the session, never from the conversation
 */
export type ProducerId1 = string;
export type RecordId1 = string;
/**
 * Never confused with mandatory or compliance reporting data
 */
export type Source2 = "agent conversation";
export type Status1 = "declined";
/**
 * Time of the latest save
 */
export type UpdatedAt1 = string;
/**
 * Starts at 1; incremented on every save; used for conditional writes
 */
export type Version1 = number;

/**
 * A conversation the producer agreed to save.
 */
export interface CompletedRecord {
  ai_usage?: AiUsage;
  closed_at?: ClosedAt;
  consent: StoredConsent;
  consent_history?: ConsentHistory;
  created_at: CreatedAt;
  decision_log?: DecisionLog;
  earlier_answers?: EarlierAnswers;
  entity_type: EntityType;
  evidence: Evidence1;
  feedback?: Feedback;
  insights?: Insights1;
  language: Language;
  peer_examples?: PeerExamples1;
  pii_check?: PiiCheck;
  pii_entity_types?: PiiEntityTypes;
  pii_flag?: PiiFlag;
  pii_matches?: PiiMatches;
  pii_review?: PiiReview;
  producer_id: ProducerId;
  record_id: RecordId;
  review_status?: ReviewStatus;
  reviewed_at?: ReviewedAt;
  reviewed_by?: ReviewedBy;
  reviewer_summary_english?: ReviewerSummaryEnglish;
  reviewer_summary_original?: ReviewerSummaryOriginal;
  reviewer_tags?: ReviewerTags;
  source?: Source1;
  status: Status;
  summary_english?: SummaryEnglish;
  summary_original: SummaryOriginal;
  tags: Tags;
  updated_at: UpdatedAt;
  version: Version;
}
/**
 * Tokens one model used in this conversation, for the AI footprint (#26, #29). Non-narrative.
 */
export interface ModelUsage {
  input_tokens: InputTokens;
  model_id: ModelId;
  output_tokens: OutputTokens;
}
/**
 * The producer agreed to store the conversation. Consent is a scope, not a yes/no:
 *
 * internal: stored for Fair Trade USA's own review and trends
 * internal_and_outward: may also be shared outward (e.g. aggregated for partners)
 */
export interface StoredConsent {
  recorded_at: RecordedAt;
  scope: Scope;
}
/**
 * One consent choice the producer made (#19, #26). Non-narrative, so allowed on declined records.
 */
export interface ConsentChoice {
  recorded_at: RecordedAt1;
  scope: Scope1;
}
/**
 * One step of the agent's reasoning trail (#26). `refs` holds opaque IDs only (DECISION_REF).
 */
export interface DecisionLogEntry {
  at: At;
  code: Code;
  kind: Kind;
  refs?: Refs;
}
/**
 * An answer shown to the producer and later replaced (#26).
 *
 * reopened: the full answer shown before the producer reopened the playback
 * interrupted: only the claims shown before a failed answer was retried
 */
export interface EarlierAnswer {
  evidence?: Evidence;
  given_at: GivenAt;
  insights?: Insights;
  peer_examples?: PeerExamples;
  reason: Reason;
}
/**
 * One insight or peer example given to the producer, with its citation.
 */
export interface Claim {
  citation: Citation;
  text: Text;
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
/**
 * One personal-information match a scan found, kept for human review (issue #20).
 */
export interface PiiMatch {
  context: Context;
  entity_type: EntityType1;
  message_at: MessageAt;
  text: Text1;
}
/**
 * The producer declined. Only identifiers, status and time are kept: no narrative content.
 */
export interface DeclinedRecord {
  ai_usage?: AiUsage1;
  closed_at?: ClosedAt1;
  consent: DeclinedConsent;
  consent_history?: ConsentHistory1;
  created_at: CreatedAt1;
  producer_id: ProducerId1;
  record_id: RecordId1;
  source?: Source2;
  status: Status1;
  updated_at: UpdatedAt1;
  version: Version1;
}
/**
 * The producer declined: nothing narrative is stored.
 */
export interface DeclinedConsent {
  recorded_at: RecordedAt2;
  scope: Scope2;
}
