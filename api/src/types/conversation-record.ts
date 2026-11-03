// GENERATED FILE. Do not edit by hand.
// Source: agent/src/fex/models.py  ->  agent/scripts/generate_types.py
// schema-sha256: 9842e32e6446fb9723567cef0124223cdacb03ce4b718c8ed86a2fcd2a7a4007
// body-sha256: dc93f9223bd0604cc899389990fd0175ff5180d6092344398b6c61125f48fb16
// end-of-banner
/**
 * One record per Fair Exchange conversation. Generated from agent/src/fex/models.py; do not edit by hand.
 */
export type ConversationRecord = CompletedRecord | DeclinedRecord;
export type RecordedAt = string;
export type Scope = "declined" | "internal" | "internal_and_outward";
export type CreatedAt = string;
/**
 * e.g. cooperative, smallholder, hired-labor farm, processor
 */
export type EntityType = string;
/**
 * Was the guidance helpful?
 */
export type Feedback = ("yes" | "somewhat" | "no") | null;
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
/**
 * What the data shows, as given to the producer
 */
export type Insights = Claim[];
/**
 * ISO 639-1 code of the producer's language, e.g. 'es'
 */
export type Language = string;
/**
 * What others tried, as given to the producer
 */
export type PeerExamples = Claim[];
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
 * Never confused with mandatory or compliance reporting data
 */
export type Source1 = "agent conversation";
export type Status = "completed";
/**
 * English version, for non-English conversations
 */
export type SummaryEnglish = string | null;
/**
 * The challenge in the producer's own words and language
 */
export type SummaryOriginal = string;
/**
 * Challenge tags from the 11-tag set
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
 * A conversation the producer agreed to save.
 */
export interface CompletedRecord {
  consent: Consent;
  created_at: CreatedAt;
  entity_type: EntityType;
  feedback?: Feedback;
  insights?: Insights;
  language: Language;
  peer_examples?: PeerExamples;
  pii_flag?: PiiFlag;
  producer_id: ProducerId;
  record_id: RecordId;
  review_status?: ReviewStatus;
  reviewed_at?: ReviewedAt;
  reviewed_by?: ReviewedBy;
  source?: Source1;
  status: Status;
  summary_english?: SummaryEnglish;
  summary_original: SummaryOriginal;
  tags: Tags;
}
/**
 * What the producer agreed to, as a scope rather than a yes/no.
 *
 * declined: nothing narrative is stored
 * internal: stored for Fair Trade USA's own review and trends
 * internal_and_outward: may also be shared outward (e.g. aggregated for partners)
 */
export interface Consent {
  recorded_at: RecordedAt;
  scope: Scope;
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
  consent: Consent;
  created_at: CreatedAt1;
  producer_id: ProducerId1;
  record_id: RecordId1;
  source?: Source2;
  status: Status1;
}
