import { readdirSync, readFileSync } from 'node:fs';
import * as path from 'node:path';
import { CfnOutput, Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import type * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import type * as kms from 'aws-cdk-lib/aws-kms';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { NodejsFunction } from 'aws-cdk-lib/aws-lambda-nodejs';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

const REPO = path.resolve(__dirname, '..', '..');
const API_DIR = path.join(REPO, 'api');

/** Header names; they match api/src/core/demoAuth.ts and web/src/lib/liveClient.ts. */
const PRODUCER_HEADER = 'x-demo-producer-id';
const PASSCODE_HEADER = 'x-demo-passcode';

/**
 * The demo allow-list: the producer of every eval scenario (eval/scenarios/*.json), read at synth time so it
 * cannot drift from the web app's picker, which reads the same files. Synthetic producers only.
 */
export function scenarioProducerIds(dir = path.join(REPO, 'eval', 'scenarios')): string[] {
  const ids = readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => (JSON.parse(readFileSync(path.join(dir, f), 'utf8')) as { producer_id?: unknown }).producer_id)
    .filter((id): id is string => typeof id === 'string' && /^[A-Za-z0-9-]+$/.test(id));
  if (ids.length === 0) throw new Error(`No scenario producers found in ${dir}`);
  return [...new Set(ids)].sort();
}

export interface FexChatApiProps {
  conversations: dynamodb.ITable;
  runtimeArn: string;
  /** The web app's origin, e.g. https://dxxxx.cloudfront.net; the only CORS origin (#25). */
  allowedOrigin: string;
  /** Idle period before the sweep auto-closes a conversation (#13: 120 minutes). */
  inactivityMinutes: number;
  logRetention: logs.RetentionDays;
  /** The application data key: encrypts the log groups and the passcode secret (spec 05 "Security"). */
  dataKey: kms.IKey;
  /** Reported by GET /health. */
  version: string;
}

/**
 * The chat API (docs/specs/25-chat-endpoint.md): API Gateway REST API in front of TypeScript Lambdas, with
 * response streaming on the turn routes, the inactivity sweep, and the sandbox sign-in stand-in (#11):
 * a Lambda authorizer that accepts a shared passcode (Secrets Manager) plus a producer from the scenario
 * allow-list. Each Lambda has its own role; only the chat and sweep roles may invoke the agent runtime.
 */
export class FexChatApi extends Construct {
  readonly api: apigw.RestApi;
  readonly passcode: secretsmanager.Secret;

  constructor(scope: Construct, id: string, props: FexChatApiProps) {
    super(scope, id);
    const fn = (name: string, file: string, handler: string, opts: {
      timeout: Duration; environment?: Record<string, string>; description: string;
    }) => new NodejsFunction(this, name, {
      entry: path.join(API_DIR, 'src', 'handlers', file),
      handler,
      projectRoot: API_DIR,
      depsLockFilePath: path.join(API_DIR, 'package-lock.json'),
      runtime: lambda.Runtime.NODEJS_24_X,
      architecture: lambda.Architecture.ARM_64,
      memorySize: 512,
      timeout: opts.timeout,
      description: opts.description,
      environment: opts.environment,
      // Spec 05: retention set explicitly on every log group
      logGroup: new logs.LogGroup(this, `${name}Logs`, {
        retention: props.logRetention,
        encryptionKey: props.dataKey,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
      // Bundle every dependency (including the AWS SDK clients), so the code runs with the versions it was tested with
      bundling: { externalModules: [], minify: true, sourceMap: false },
    });

    const chatEnv = {
      CONVERSATIONS_TABLE: props.conversations.tableName,
      AGENT_RUNTIME_ARN: props.runtimeArn,
      ALLOWED_ORIGIN: props.allowedOrigin,
    };
    const turnTimeout = Duration.minutes(5); // #25: LAMBDA_TIMEOUT_MS in api/src/core/types.ts
    const chat = {
      start: fn('Start', 'conversations.ts', 'start', { timeout: turnTimeout, environment: chatEnv, description: 'FEX chat: POST /conversations (streams)' }),
      message: fn('Message', 'conversations.ts', 'message', { timeout: turnTimeout, environment: chatEnv, description: 'FEX chat: POST /conversations/{id}/messages (streams)' }),
      action: fn('Action', 'conversations.ts', 'action', { timeout: turnTimeout, environment: chatEnv, description: 'FEX chat: POST /conversations/{id}/actions (streams)' }),
      get: fn('Get', 'conversations.ts', 'get', { timeout: Duration.seconds(29), environment: chatEnv, description: 'FEX chat: GET /conversations/{id}' }),
      list: fn('List', 'conversations.ts', 'list', { timeout: Duration.seconds(29), environment: chatEnv, description: 'FEX chat: GET /conversations' }),
    };
    const sweep = fn('Sweep', 'sweep.ts', 'handler', {
      timeout: Duration.minutes(15),
      environment: {
        CONVERSATIONS_TABLE: props.conversations.tableName,
        AGENT_RUNTIME_ARN: props.runtimeArn,
        INACTIVITY_MINUTES: String(props.inactivityMinutes),
      },
      description: 'FEX chat: closes idle conversations and reconciles open ones (#25 sweep)',
    });
    const health = fn('Health', 'health.ts', 'handler', {
      timeout: Duration.seconds(5),
      environment: { FEX_VERSION: props.version, ALLOWED_ORIGIN: props.allowedOrigin },
      description: 'FEX chat: GET /health (no sign-in)',
    });

    // #25 "Only the chat handlers' role and the sweep's role may invoke the runtime"
    const invoke = new iam.PolicyStatement({
      sid: 'InvokeFexRuntime',
      actions: ['bedrock-agentcore:InvokeAgentRuntime'],
      resources: [props.runtimeArn, `${props.runtimeArn}/runtime-endpoint/*`],
    });
    for (const f of [...Object.values(chat), sweep]) {
      props.conversations.grantReadWriteData(f);
      f.addToRolePolicy(invoke);
    }

    // The sign-in stand-in (#11). The passcode is generated here; read it with the command deploy.sh prints.
    this.passcode = new secretsmanager.Secret(this, 'DemoPasscode', {
      description: 'Fair Exchange sandbox demo passcode (sign-in stand-in, docs/specs/11-identity.md)',
      generateSecretString: { passwordLength: 20, excludePunctuation: true, includeSpace: false },
      encryptionKey: props.dataKey,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const authorizerFn = fn('Authorizer', 'authorizer.ts', 'handler', {
      timeout: Duration.seconds(10),
      environment: {
        DEMO_PASSCODE_SECRET_ARN: this.passcode.secretArn,
        DEMO_PRODUCER_IDS: scenarioProducerIds().join(','),
      },
      description: 'FEX chat: demo sign-in stand-in (passcode + scenario producer allow-list)',
    });
    this.passcode.grantRead(authorizerFn);
    const authorizer = new apigw.RequestAuthorizer(this, 'DemoAuthorizer', {
      handler: authorizerFn,
      identitySources: [
        apigw.IdentitySource.header(PRODUCER_HEADER),
        apigw.IdentitySource.header(PASSCODE_HEADER),
      ],
      resultsCacheTtl: Duration.minutes(5),
    });

    this.api = new apigw.RestApi(this, 'Api', {
      description: 'Fair Exchange chat API (#25)',
      endpointTypes: [apigw.EndpointType.REGIONAL],
      // No execution logging (it could hold request content), so no account-wide CloudWatch role either
      cloudWatchRole: false,
      deployOptions: {
        stageName: 'v1',
        // Sandbox demo: a low ceiling, since anyone with the passcode can start agent turns
        throttlingRateLimit: 5,
        throttlingBurstLimit: 10,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: [props.allowedOrigin],
        allowMethods: ['GET', 'POST', 'OPTIONS'],
        allowHeaders: ['content-type', PRODUCER_HEADER, PASSCODE_HEADER],
        maxAge: Duration.hours(1),
      },
    });
    // Errors API Gateway itself returns (401 from the authorizer, throttling, 5xx) need the CORS header too,
    // or the browser hides the status from the web app.
    for (const [rid, type] of [['Default4xx', apigw.ResponseType.DEFAULT_4XX], ['Default5xx', apigw.ResponseType.DEFAULT_5XX]] as const) {
      this.api.addGatewayResponse(rid, {
        type,
        responseHeaders: { 'Access-Control-Allow-Origin': `'${props.allowedOrigin}'` },
      });
    }

    const signedIn = { authorizer, authorizationType: apigw.AuthorizationType.CUSTOM };
    const streamed = (f: lambda.IFunction) =>
      new apigw.LambdaIntegration(f, { responseTransferMode: apigw.ResponseTransferMode.STREAM, timeout: turnTimeout });
    const proxied = (f: lambda.IFunction) => new apigw.LambdaIntegration(f);

    const conversations = this.api.root.addResource('conversations');
    conversations.addMethod('POST', streamed(chat.start), signedIn);
    conversations.addMethod('GET', proxied(chat.list), signedIn);
    const one = conversations.addResource('{id}');
    one.addMethod('GET', proxied(chat.get), signedIn);
    one.addResource('messages').addMethod('POST', streamed(chat.message), signedIn);
    one.addResource('actions').addMethod('POST', streamed(chat.action), signedIn);
    this.api.root.addResource('health').addMethod('GET', proxied(health));

    // #25 sweep: every 15 minutes
    new events.Rule(this, 'SweepSchedule', {
      schedule: events.Schedule.rate(Duration.minutes(15)),
      targets: [new targets.LambdaFunction(sweep, { retryAttempts: 0 })],
    });

    new CfnOutput(Stack.of(this), 'ApiUrl', { value: this.api.url });
    new CfnOutput(Stack.of(this), 'DemoPasscodeSecretArn', { value: this.passcode.secretArn });
  }
}
