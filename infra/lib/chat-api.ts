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
import { RECORDS_GLUE_TABLE, RECORDS_PREFIX, SEEDED_GLUE_TABLE, SEEDED_PREFIX, SYNC_DATABASE } from './athena-sync-stack';

const REPO = path.resolve(__dirname, '..', '..');
const API_DIR = path.join(REPO, 'api');

/** Header names; they match api/src/core/demoAuth.ts and web/src/lib/liveClient.ts. */
const PRODUCER_HEADER = 'x-demo-producer-id';
const PASSCODE_HEADER = 'x-demo-passcode';
const ADMIN_PASSCODE_HEADER = 'x-demo-admin-passcode';
const REVIEWER_PASSCODE_HEADER = 'x-demo-reviewer-passcode';

/** The Athena side of the analytics route (#29): from the FairExchangeAthenaSync and analytics queries stacks. */
export interface AnalyticsSource {
  workGroup: string;
  namedQueryIds: string;
  recordsBucketName: string;
  resultsBucketName: string;
  syncKeyArn: string;
}

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
  records: dynamodb.ITable;
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
  /** When set, adds GET /analytics behind the admin passcode (#29, #11). Absent until the Athena stacks exist. */
  analytics?: AnalyticsSource;
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
  readonly adminPasscode?: secretsmanager.Secret;

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
        allowMethods: ['GET', 'POST', 'PATCH', 'OPTIONS'],
        allowHeaders: ['content-type', PRODUCER_HEADER, PASSCODE_HEADER, ADMIN_PASSCODE_HEADER, REVIEWER_PASSCODE_HEADER],
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

    if (props.analytics) this.adminPasscode = this.addAnalytics(props, fn);

    const reviewerSecret = new secretsmanager.Secret(this, 'ReviewerPasscode', {
      description: 'Fair Exchange sandbox reviewer passcode',
      generateSecretString: { passwordLength: 20, excludePunctuation: true, includeSpace: false },
      encryptionKey: props.dataKey, removalPolicy: RemovalPolicy.DESTROY,
    });
    const sessionAuth = fn('SessionAuthorizer', 'sessionAuthorizer.ts', 'handler', {
      timeout: Duration.seconds(10), description: 'FEX sandbox identity for producer, reviewer and admin',
      environment: {
        PRODUCER_SECRET_ARN: this.passcode.secretArn, REVIEWER_SECRET_ARN: reviewerSecret.secretArn,
        ...(this.adminPasscode ? { ADMIN_SECRET_ARN: this.adminPasscode.secretArn } : {}),
        DEMO_PRODUCER_IDS: scenarioProducerIds().join(','),
      },
    });
    this.passcode.grantRead(sessionAuth);
    reviewerSecret.grantRead(sessionAuth);
    this.adminPasscode?.grantRead(sessionAuth);
    const sessionAuthorizer = new apigw.RequestAuthorizer(this, 'SessionAuthorizerConfig', {
      handler: sessionAuth,
      // Credential headers are alternatives. With caching off, missing optional headers do not short-circuit to 401.
      identitySources: [], resultsCacheTtl: Duration.seconds(0),
    });
    const session = { authorizer: sessionAuthorizer, authorizationType: apigw.AuthorizationType.CUSTOM };
    const recordEnv = { RECORDS_TABLE: props.records.tableName, ALLOWED_ORIGIN: props.allowedOrigin };
    const identity = fn('Identity', 'me.ts', 'identity', {
      timeout: Duration.seconds(10), environment: { ALLOWED_ORIGIN: props.allowedOrigin }, description: 'FEX: GET /me',
    });
    const mine = fn('MyRecords', 'me.ts', 'records', {
      timeout: Duration.seconds(29), environment: recordEnv, description: 'FEX: producer-only GET /me/records',
    });
    const grantRecords = (f: lambda.IFunction, actions: string[]) => {
      f.addToRolePolicy(new iam.PolicyStatement({ actions, resources: [props.records.tableArn] }));
      props.dataKey.grantDecrypt(f);
    };
    grantRecords(mine, ['dynamodb:Scan']);
    const me = this.api.root.addResource('me');
    me.addMethod('GET', proxied(identity), session);
    me.addResource('records').addMethod('GET', proxied(mine), session);
    const review = {
      list: fn('ReviewList', 'review.ts', 'list', { timeout: Duration.seconds(29), environment: recordEnv, description: 'FEX: reviewer record list' }),
      get: fn('ReviewGet', 'review.ts', 'get', { timeout: Duration.seconds(29), environment: recordEnv, description: 'FEX: reviewer record detail' }),
      patch: fn('ReviewPatch', 'review.ts', 'patch', { timeout: Duration.seconds(29), environment: recordEnv, description: 'FEX: reviewer corrections' }),
      approve: fn('ReviewApprove', 'review.ts', 'approve', { timeout: Duration.seconds(29), environment: recordEnv, description: 'FEX: reviewer approval' }),
    };
    grantRecords(review.list, ['dynamodb:Scan']);
    grantRecords(review.get, ['dynamodb:GetItem']);
    for (const f of [review.patch, review.approve]) {
      grantRecords(f, ['dynamodb:GetItem', 'dynamodb:PutItem']);
      props.dataKey.grantEncryptDecrypt(f);
    }
    const records = this.api.root.addResource('records');
    records.addMethod('GET', proxied(review.list), session);
    const record = records.addResource('{id}');
    record.addMethod('GET', proxied(review.get), session);
    record.addMethod('PATCH', proxied(review.patch), session);
    record.addResource('approve').addMethod('POST', proxied(review.approve), session);
    new CfnOutput(Stack.of(this), 'ReviewerPasscodeSecretArn', { value: reviewerSecret.secretArn });

    // #25 sweep: every 15 minutes
    new events.Rule(this, 'SweepSchedule', {
      schedule: events.Schedule.rate(Duration.minutes(15)),
      targets: [new targets.LambdaFunction(sweep, { retryAttempts: 0 })],
    });

    new CfnOutput(Stack.of(this), 'ApiUrl', { value: this.api.url });
    new CfnOutput(Stack.of(this), 'DemoPasscodeSecretArn', { value: this.passcode.secretArn });
  }

  /**
   * GET /analytics (#29) behind the admin stand-in: its own passcode, secret, header and authorizer, which grant
   * the `admin` role only. The analytics Lambda reads the fixed named queries and runs them in the `fex` workgroup.
   */
  private addAnalytics(props: FexChatApiProps, fn: (name: string, file: string, handler: string, opts: {
    timeout: Duration; environment?: Record<string, string>; description: string;
  }) => NodejsFunction): secretsmanager.Secret {
    const a = props.analytics!;
    const { region, account } = Stack.of(this);
    const secret = new secretsmanager.Secret(this, 'AdminPasscode', {
      description: 'Fair Exchange sandbox admin passcode (analytics; sign-in stand-in, docs/specs/11-identity.md)',
      generateSecretString: { passwordLength: 20, excludePunctuation: true, includeSpace: false },
      encryptionKey: props.dataKey,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const authorizerFn = fn('AdminAuthorizer', 'authorizer.ts', 'handler', {
      timeout: Duration.seconds(10),
      environment: { DEMO_ROLE: 'admin', DEMO_PASSCODE_SECRET_ARN: secret.secretArn },
      description: 'FEX analytics: admin sign-in stand-in (admin passcode only)',
    });
    secret.grantRead(authorizerFn);
    const authorizer = new apigw.RequestAuthorizer(this, 'AdminAuthorizerConfig', {
      handler: authorizerFn,
      identitySources: [apigw.IdentitySource.header(ADMIN_PASSCODE_HEADER)],
      resultsCacheTtl: Duration.minutes(5),
    });

    const analytics = fn('Analytics', 'analytics.ts', 'handler', {
      timeout: Duration.seconds(29), // the queries have a 20-second limit (#29)
      environment: {
        ATHENA_WORKGROUP: a.workGroup,
        ANALYTICS_NAMED_QUERY_IDS: a.namedQueryIds,
        ALLOWED_ORIGIN: props.allowedOrigin,
      },
      description: 'FEX analytics: GET /analytics (admin)',
    });
    const allow = (sid: string, actions: string[], resources: string[]) =>
      analytics.addToRolePolicy(new iam.PolicyStatement({ sid, actions, resources }));
    allow('RunNamedQueries', [
      'athena:BatchGetNamedQuery', 'athena:StartQueryExecution', 'athena:GetQueryExecution',
      'athena:GetQueryResults', 'athena:StopQueryExecution', 'athena:GetWorkGroup',
    ], [`arn:aws:athena:${region}:${account}:workgroup/${a.workGroup}`]);
    allow('ReadRecordTables', ['glue:GetDatabase', 'glue:GetTable', 'glue:GetPartitions'], [
      `arn:aws:glue:${region}:${account}:catalog`,
      `arn:aws:glue:${region}:${account}:database/${SYNC_DATABASE}`,
      ...[RECORDS_GLUE_TABLE, SEEDED_GLUE_TABLE].map((t) => `arn:aws:glue:${region}:${account}:table/${SYNC_DATABASE}/${t}`),
    ]);
    allow('ReadRecordObjects', ['s3:GetObject'],
      [RECORDS_PREFIX, SEEDED_PREFIX].map((p) => `arn:aws:s3:::${a.recordsBucketName}/${p}*`));
    allow('ListRecordObjects', ['s3:ListBucket', 's3:GetBucketLocation'], [`arn:aws:s3:::${a.recordsBucketName}`]);
    allow('WriteQueryResults', [
      's3:GetObject', 's3:PutObject', 's3:AbortMultipartUpload', 's3:ListMultipartUploadParts',
    ], [`arn:aws:s3:::${a.resultsBucketName}/results/*`]);
    allow('ListQueryResults', ['s3:ListBucket', 's3:GetBucketLocation'], [`arn:aws:s3:::${a.resultsBucketName}`]);
    allow('UseSyncKey', ['kms:Decrypt', 'kms:GenerateDataKey'], [a.syncKeyArn]);

    this.api.root.addResource('analytics').addMethod('GET', new apigw.LambdaIntegration(analytics), {
      authorizer, authorizationType: apigw.AuthorizationType.CUSTOM,
    });
    new CfnOutput(Stack.of(this), 'AdminPasscodeSecretArn', { value: secret.secretArn });
    return secret;
  }
}
