import { CfnOutput, Stack, type StackProps } from 'aws-cdk-lib';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import type { Construct } from 'constructs';

/**
 * Issue #12: the FEX Bedrock Guardrail, in DETECT mode. Spec: docs/specs/12-guardrail.md.
 *
 * Every policy action is NONE for input and output, so the Guardrail never blocks or masks anything; it only
 * reports. The agent attaches it to every model call (FEX_GUARDRAIL_ID / FEX_GUARDRAIL_VERSION) with trace on
 * and redaction off, and logs findings (policy and topic or category only) to CloudWatch.
 * Not configured, per the spec: sensitive-information filters (PII is Comprehend's job, #20) and the
 * contextual grounding check (the citation verifier covers grounding).
 */
const DETECT = { inputAction: 'NONE', outputAction: 'NONE', inputEnabled: true, outputEnabled: true };

export const DENIED_TOPICS = [
  {
    name: 'Certification status and audit results',
    definition: "Questions about a producer's Fair Trade certification status, audit outcomes or compliance "
      + 'findings, including requests for audit results.',
    examples: ['What did our last audit find?', '¿Cuál es el estado de nuestra certificación?'],
  },
  {
    name: 'Worker grievances and complaints',
    definition: 'Complaints or grievances from or about workers, including reports of mistreatment, wage '
      + 'disputes or requests to file a grievance.',
    examples: ['I want to report that workers are not being paid.', 'Quiero presentar una queja.'],
  },
];

// Standard content filter categories. PROMPT_ATTACK applies to input only, so its output strength is NONE.
export const CONTENT_FILTERS = [
  { type: 'SEXUAL', inputStrength: 'HIGH', outputStrength: 'HIGH' },
  { type: 'VIOLENCE', inputStrength: 'HIGH', outputStrength: 'HIGH' },
  { type: 'HATE', inputStrength: 'HIGH', outputStrength: 'HIGH' },
  { type: 'INSULTS', inputStrength: 'HIGH', outputStrength: 'HIGH' },
  { type: 'MISCONDUCT', inputStrength: 'HIGH', outputStrength: 'HIGH' },
  { type: 'PROMPT_ATTACK', inputStrength: 'HIGH', outputStrength: 'NONE' },
];

export class GuardrailStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const guardrail = new bedrock.CfnGuardrail(this, 'FexGuardrail', {
      name: 'fair-exchange-fex',
      description: 'FEX Guardrail in detect mode (#12): every action NONE, nothing blocked or masked',
      // Required by the API; never shown, because no policy action blocks.
      blockedInputMessaging: 'This message was not processed.',
      blockedOutputsMessaging: 'This reply was not shown.',
      topicPolicyConfig: {
        topicsConfig: DENIED_TOPICS.map((t) => ({ ...t, type: 'DENY', ...DETECT })),
      },
      contentPolicyConfig: {
        filtersConfig: CONTENT_FILTERS.map((f) => ({ ...f, ...DETECT })),
      },
    });

    const version = new bedrock.CfnGuardrailVersion(this, 'FexGuardrailVersion', {
      guardrailIdentifier: guardrail.attrGuardrailId,
      description: 'Pinned version used by the agent (FEX_GUARDRAIL_VERSION)',
    });

    new CfnOutput(this, 'GuardrailId', { value: guardrail.attrGuardrailId });
    new CfnOutput(this, 'GuardrailArn', { value: guardrail.attrGuardrailArn });
    new CfnOutput(this, 'GuardrailVersion', { value: version.attrVersion });
  }
}
