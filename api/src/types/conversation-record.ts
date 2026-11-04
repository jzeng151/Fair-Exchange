// GENERATED FILE. Do not edit by hand.
// Source: agent/src/fex/models.py  ->  agent/scripts/generate_types.py
// schema-sha256: be8f98dad8c03dad644969727195154b9cd044ceb72be9e5f805106d0ec8616c
// body-sha256: 2cbe4f3667595644d0ad94af5a05cc6d3dd936053cc5836fa33998b0c7a2a529
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
 * Personal information flagged for human review; never redacted
 */
export type PiiFlag = boolean;
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
  earlier_answers?: EarlierAnswers;
  entity_type: EntityType;
  evidence: Evidence1;
  feedback?: Feedback;
  insights?: Insights1;
  language: Language;
  peer_examples?: PeerExamples1;
  pii_flag?: PiiFlag;
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
