import * as path from 'node:path';
import { CfnOutput, Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { NodejsFunction } from 'aws-cdk-lib/aws-lambda-nodejs';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

interface Props {
  conversations: dynamodb.ITable; conversationResource: apigw.IResource; authorization: apigw.MethodOptions;
  dataKey: kms.IKey; allowedOrigin: string; logRetention: logs.RetentionDays;
}
/** Temporary voice data is separate from consented records; no browser receives AWS credentials. */
export class FexVoice extends Construct {
  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id);
    const stack = Stack.of(this);
    const bucket = new s3.Bucket(this, 'Bucket', {
      encryption: s3.BucketEncryption.KMS, encryptionKey: props.dataKey, bucketKeyEnabled: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL, enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED, removalPolicy: RemovalPolicy.RETAIN,
      lifecycleRules: [{ expiration: Duration.days(1), abortIncompleteMultipartUploadAfter: Duration.days(1) }],
      cors: [{ allowedOrigins: [props.allowedOrigin], allowedMethods: [s3.HttpMethods.POST], allowedHeaders: ['*'], maxAge: 300 }],
    });
    const table = new dynamodb.Table(this, 'Table', {
      partitionKey: { name: 'voice_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST, encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: props.dataKey, timeToLiveAttribute: 'expires_at', removalPolicy: RemovalPolicy.DESTROY,
      // Temporary transcripts must not acquire a second retention window in PITR/backups.
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: false },
    });
    const jobPrefix = `${stack.stackName}-voice-`;
    const jobs = stack.formatArn({ service: 'transcribe', resource: 'transcription-job', resourceName: `${jobPrefix}*` });
    const access = new iam.Role(this, 'TranscribeDataAccess', {
      assumedBy: new iam.ServicePrincipal('transcribe.amazonaws.com', { conditions: {
        // Transcribe validates data access before the job exists. Scope trust to this
        // account/region; job API permissions and PassRole below remain prefix-scoped.
        StringEquals: { 'aws:SourceAccount': stack.account },
        ArnLike: { 'aws:SourceArn': stack.formatArn({ service: 'transcribe', resource: '*' }) },
      } }),
    });
    bucket.grantRead(access, 'audio/*');
    bucket.grantPut(access, 'transcripts/*');
    props.dataKey.grantEncryptDecrypt(access);
    const apiDir = path.resolve(__dirname, '..', '..', 'api');
    const make = (name: string, handler: string, timeout: number) => new NodejsFunction(this, name, {
      entry: path.join(apiDir, 'src/handlers/voice.ts'), handler, projectRoot: apiDir,
      depsLockFilePath: path.join(apiDir, 'package-lock.json'), runtime: lambda.Runtime.NODEJS_24_X,
      architecture: lambda.Architecture.ARM_64, memorySize: 512, timeout: Duration.seconds(timeout),
      environment: { VOICE_TABLE: table.tableName, VOICE_BUCKET: bucket.bucketName, VOICE_KEY_ARN: props.dataKey.keyArn,
        VOICE_DATA_ROLE: access.roleArn, VOICE_JOB_PREFIX: jobPrefix, CONVERSATIONS_TABLE: props.conversations.tableName,
        ALLOWED_ORIGIN: props.allowedOrigin },
      logGroup: new logs.LogGroup(this, `${name}Logs`, { encryptionKey: props.dataKey,
        retention: props.logRetention, removalPolicy: RemovalPolicy.DESTROY }),
      bundling: { externalModules: [], minify: true, sourceMap: false },
    });
    const route = make('Routes', 'handler', 29);
    const worker = make('Completion', 'completion', 60);
    for (const f of [route, worker]) {
      f.addToRolePolicy(new iam.PolicyStatement({ actions: ['dynamodb:GetItem', 'dynamodb:UpdateItem'], resources: [table.tableArn] }));
      props.dataKey.grantEncryptDecrypt(f);
    }
    route.addToRolePolicy(new iam.PolicyStatement({ actions: ['dynamodb:PutItem'], resources: [table.tableArn] }));
    route.addToRolePolicy(new iam.PolicyStatement({ actions: ['dynamodb:GetItem'], resources: [props.conversations.tableArn] }));
    bucket.grantReadWrite(route, 'audio/*'); // presigned POST, HEAD validation, cancellation
    bucket.grantDelete(route, 'transcripts/*');
    bucket.grantPut(route, 'transcripts/*'); // StartTranscriptionJob also validates the caller's output access.
    route.addToRolePolicy(new iam.PolicyStatement({ actions: ['transcribe:StartTranscriptionJob'], resources: [jobs] }));
    route.addToRolePolicy(new iam.PolicyStatement({ actions: ['iam:PassRole'], resources: [access.roleArn],
      conditions: { StringEquals: { 'iam:PassedToService': 'transcribe.amazonaws.com' } } }));
    worker.addToRolePolicy(new iam.PolicyStatement({ actions: ['transcribe:GetTranscriptionJob'], resources: [jobs] }));
    worker.addToRolePolicy(new iam.PolicyStatement({ actions: ['translate:TranslateText'], resources: ['*'] }));
    bucket.grantRead(worker, 'transcripts/*');
    bucket.grantDelete(worker, 'audio/*'); bucket.grantDelete(worker, 'transcripts/*');
    new events.Rule(this, 'Finished', {
      eventPattern: { source: ['aws.transcribe'], detailType: ['Transcribe Job State Change'], detail: {
        TranscriptionJobName: [{ prefix: jobPrefix }], TranscriptionJobStatus: ['COMPLETED', 'FAILED'],
      } }, targets: [new targets.LambdaFunction(worker)],
    });
    const voice = props.conversationResource.addResource('voice');
    const integration = new apigw.LambdaIntegration(route);
    voice.addMethod('POST', integration, props.authorization);
    const one = voice.addResource('{voice_id}');
    one.addMethod('GET', integration, props.authorization); one.addMethod('DELETE', integration, props.authorization);
    one.addResource('transcribe').addMethod('POST', integration, props.authorization);
    new CfnOutput(stack, 'VoiceBucketName', { value: bucket.bucketName });
    new CfnOutput(stack, 'VoiceTableName', { value: table.tableName });
    new CfnOutput(stack, 'VoiceCompletionFunctionName', { value: worker.functionName });
  }
}
