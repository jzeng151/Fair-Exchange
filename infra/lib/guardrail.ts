import { createHash } from 'node:crypto';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

/**
 * Bedrock Guardrail in detect mode (issue #12, docs/specs/12-guardrail.md).
 *
 * Every policy action is NONE for input and output: the Guardrail flags and never blocks or masks,
 * so the producer's words reach FEX as written. The agent logs each finding to CloudWatch
 * (agent/src/fex/guardrail.py). Not configured, per the spec: sensitive information filters
 * (PII is Comprehend's job, #20; French PII comes with #24) and the contextual grounding check
 * (the citation verifier covers grounding).
 */

const DETECT = { inputAction: 'NONE', outputAction: 'NONE', inputEnabled: true, outputEnabled: true } as const;

const DENIED_TOPICS: bedrock.CfnGuardrail.TopicConfigProperty[] = [
  {
    name: 'Certification status and audit results',
    type: 'DENY',
    definition:
      "Questions or statements about a producer's Fair Trade certification status, audit outcomes, " +
      'non-conformities, or whether certification will be granted, suspended or revoked.',
    examples: [
      'Will I lose my certification?',
      'What did the auditor find at our cooperative?',
      'Is our certificate still valid?',
    ],
    ...DETECT,
  },
  {
    name: 'Worker grievances and complaints',
    type: 'DENY',
    definition:
      'Reports or complaints about worker treatment, wages, working conditions, harassment or ' +
      'retaliation, including grievances against an employer, buyer or cooperative.',
    examples: [
      'Our workers are not being paid on time.',
      'I want to file a complaint against my employer.',
      'A supervisor is threatening the pickers.',
    ],
    ...DETECT,
  },
];

// The standard content filter categories. PROMPT_ATTACK applies to input only, so its output strength is NONE.
const CONTENT_FILTERS: bedrock.CfnGuardrail.ContentFilterConfigProperty[] = [
  ...['SEXUAL', 'VIOLENCE', 'HATE', 'INSULTS', 'MISCONDUCT'].map((type) => ({
    type,
    inputStrength: 'MEDIUM',
    outputStrength: 'MEDIUM',
    ...DETECT,
  })),
  { type: 'PROMPT_ATTACK', inputStrength: 'MEDIUM', outputStrength: 'NONE', ...DETECT, outputEnabled: false },
];

/** Environment variable names the agent reads (agent/src/fex/guardrail.py). */
export const GUARDRAIL_ENV = { id: 'FEX_GUARDRAIL_ID', version: 'FEX_GUARDRAIL_VERSION' } as const;

export class FexGuardrail extends Construct {
  readonly guardrail: bedrock.CfnGuardrail;
  readonly version: bedrock.CfnGuardrailVersion;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    const topicPolicyConfig = { topicsConfig: DENIED_TOPICS };
    const contentPolicyConfig = { filtersConfig: CONTENT_FILTERS };

    this.guardrail = new bedrock.CfnGuardrail(this, 'Guardrail', {
      name: 'fair-exchange-fex-detect',
      description: 'FEX responsible-AI layer in detect mode: flags, never blocks (#12)',
      topicPolicyConfig,
      contentPolicyConfig,
      // Required by Bedrock. Never shown: no policy blocks, and the agent turns redaction off.
      blockedInputMessaging: 'This message could not be processed.',
      blockedOutputsMessaging: 'This response could not be shown.',
    });

    // A version snapshots the Guardrail when it is created. Tie it to the configuration so that any
    // policy change creates a new version and the agent picks it up on the next deploy.
    const configHash = createHash('sha256')
      .update(JSON.stringify({ topicPolicyConfig, contentPolicyConfig }))
      .digest('hex')
      .slice(0, 12);
    this.version = new bedrock.CfnGuardrailVersion(this, 'Version', {
      guardrailIdentifier: this.guardrail.attrGuardrailId,
      description: `Detect-mode configuration ${configHash}`,
    });
  }

  /** Environment variables for the AgentCore runtime that runs FEX. */
  get runtimeEnvironment(): Record<string, string> {
    return { [GUARDRAIL_ENV.id]: this.guardrail.attrGuardrailId, [GUARDRAIL_ENV.version]: this.version.attrVersion };
  }

  /** Converse calls with a guardrailConfig also need ApplyGuardrail on the Guardrail. */
  grantApply(grantee: iam.IGrantable): iam.Grant {
    return iam.Grant.addToPrincipal({
      grantee,
      actions: ['bedrock:ApplyGuardrail'],
      resourceArns: [this.guardrail.attrGuardrailArn],
    });
  }
}
