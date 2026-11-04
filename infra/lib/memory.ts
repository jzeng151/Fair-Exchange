import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import { Stack } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import type * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

/**
 * Persistent conversation memory on AgentCore Memory (docs/specs/memory.md, #59).
 *
 * One Memory resource backs the whole agent. Short-term events hold each conversation's state so a
 * producer can resume after the runtime is recycled; the summary and semantic strategies extract
 * long-term memories per producer. Namespaces are templated on the actor ID ({actorId}), so each
 * producer's long-term memories sit under their own namespace and no producer can reach another's
 * (spec #6, #7). The actor ID is the producer ID the chat API sets; it never comes from model output.
 *
 * The `aws-bedrockagentcore` L1 constructs are new (alpha surface in this CDK version). The infra pins
 * aws-cdk-lib (package.json) and the agent pins the matching memory client, so the version is held
 * steady across both, per the spec's "pin its version" note.
 */

/** Per-producer long-term namespace. Mirrors producer_namespace() in the agent (memory.py). */
const ACTOR_NAMESPACE = '/actor/{actorId}/';
/**
 * Summaries are kept per session, so AgentCore requires `{sessionId}` in the summary strategy's namespace
 * (CreateMemory rejects one without it). It stays under the producer's own namespace.
 */
const SESSION_NAMESPACE = `${ACTOR_NAMESPACE}session/{sessionId}/`;

export interface FexMemoryProps {
  /**
   * Short-term event retention, in days (AgentCore allows 3 to 365). Must be longer than the maximum
   * conversation lifetime (memory spec), which the agent also enforces at startup. Configuration value:
   * there is no safe default lifetime to compare against, so the caller must pass it.
   */
  readonly eventExpiryDays: number;
  /**
   * The application data key (docs/specs/05-cdk-stack.md "Security": one customer-managed key for every bucket,
   * table, log group and the memory resource). Set at creation: changing it later replaces the memory.
   */
  readonly encryptionKey: kms.IKey;
}

export class FexMemory extends Construct {
  readonly memory: agentcore.CfnMemory;
  private readonly encryptionKey: kms.IKey;

  constructor(scope: Construct, id: string, props: FexMemoryProps) {
    super(scope, id);

    if (props.eventExpiryDays < 3 || props.eventExpiryDays > 365) {
      throw new Error(`eventExpiryDays must be between 3 and 365 (AgentCore limit); got ${props.eventExpiryDays}`);
    }

    this.encryptionKey = props.encryptionKey;
    this.memory = new agentcore.CfnMemory(this, 'Resource', {
      name: 'fair_exchange_conversation',
      description: 'Fair Exchange (#59): short-term conversation state for resume, long-term per-producer memory',
      eventExpiryDuration: props.eventExpiryDays,
      // Customer-managed key. CloudFormation creates the memory as the bootstrap execution role, whose IAM access
      // covers the key operations AgentCore needs at creation (CreateGrant, GenerateDataKey and so on).
      encryptionKeyArn: props.encryptionKey.keyArn,
      // Long-term strategies, namespaced per producer. Extraction reads the short-term events the agent
      // writes. Recall into intake/playback stays switched off in the agent (recall_eligibility) until
      // the decline policy is decided, so declined text cannot resurface.
      memoryStrategies: [
        {
          summaryMemoryStrategy: {
            name: 'conversation_summary',
            namespaces: [SESSION_NAMESPACE],
          },
        },
        {
          semanticMemoryStrategy: {
            name: 'conversation_semantic',
            namespaces: [ACTOR_NAMESPACE],
          },
        },
      ],
    });
  }

  get memoryId(): string {
    return this.memory.attrMemoryId;
  }

  get memoryArn(): string {
    return this.memory.attrMemoryArn;
  }

  /**
   * Grant the agent runtime role only the memory permissions it needs, on this one memory resource
   * (spec "Permissions"; #13 "Agent runtime permissions"). Short-term read/write for state and resume,
   * delete for the deletion function, and retrieve for long-term recall once it is switched on.
   */
  grantAgentAccess(role: iam.IRole): void {
    role.addToPrincipalPolicy(new iam.PolicyStatement({
      sid: 'FexConversationMemory',
      actions: [
        'bedrock-agentcore:CreateEvent',
        'bedrock-agentcore:ListEvents',
        'bedrock-agentcore:GetEvent',
        'bedrock-agentcore:DeleteEvent',
        'bedrock-agentcore:ListSessions',
        'bedrock-agentcore:RetrieveMemoryRecords',
      ],
      // This memory resource only: the ARN plus its per-session/per-record children.
      resources: [this.memoryArn, `${this.memoryArn}/*`],
    }));
    // The memory's data key, only through AgentCore: events and records are encrypted with it.
    role.addToPrincipalPolicy(new iam.PolicyStatement({
      sid: 'FexConversationMemoryKey',
      actions: ['kms:Decrypt', 'kms:GenerateDataKey'],
      resources: [this.encryptionKey.keyArn],
      conditions: { StringEquals: { 'kms:ViaService': `bedrock-agentcore.${Stack.of(this).region}.amazonaws.com` } },
    }));
  }
}
