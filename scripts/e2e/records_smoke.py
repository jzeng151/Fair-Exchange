"""Exercise deployed record access, reviewer writes, and Athena synchronization.

Run with `cd agent && uv run python ../scripts/e2e/records_smoke.py` using sandbox
credentials. Creates two synthetic closed records and deletes only those records
in finally. Credentials are read in memory and never printed.
"""
import json
import os
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from fex.models import CompletedRecord, parse_record
from fex.records import DynamoRecordStore


def main():
    region = os.environ.get('AWS_REGION', 'us-west-2')
    account = os.environ['EXPECTED_AWS_ACCOUNT']
    assert boto3.client('sts').get_caller_identity()['Account'] == account, 'Wrong account'
    cf = boto3.client('cloudformation', region_name=region)

    def outputs(stack):
        return {o['OutputKey']: o['OutputValue'] for o in cf.describe_stacks(StackName=stack)['Stacks'][0]['Outputs']}

    app, sync = outputs('FairExchange'), outputs('FairExchangeAthenaSync')
    base = app['ApiUrl'].rstrip('/')
    secret_client = boto3.client('secretsmanager', region_name=region)

    def credential(output):
        return secret_client.get_secret_value(SecretId=app[output])['SecretString']

    scenarios = Path(__file__).resolve().parents[2] / 'eval' / 'scenarios'
    producers = sorted({json.loads(p.read_text())['producer_id'] for p in scenarios.glob('*.json')})
    assert len(producers) >= 2
    producer = {'x-demo-passcode': credential('DemoPasscodeSecretArn'), 'x-demo-producer-id': producers[0]}
    reviewer = {'x-demo-reviewer-passcode': credential('ReviewerPasscodeSecretArn')}
    admin = {'x-demo-admin-passcode': credential('AdminPasscodeSecretArn')}

    def request(path, auth=None, method='GET', body=None, expected=200):
        time.sleep(0.25)  # Stay below the sandbox API's rate limit.
        req = urllib.request.Request(base + path, method=method,
            headers={'content-type': 'application/json', 'Origin': app['WebUrl'], **(auth or {})},
            data=None if body is None else json.dumps(body).encode())
        try:
            response = urllib.request.urlopen(req, timeout=45)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status, headers, raw = response.code, response.headers, response.read()
        assert status == expected, f'{method} {path}: expected {expected}, got {status}'
        assert headers.get('Access-Control-Allow-Origin') == app['WebUrl'], f'Missing CORS for {path}'
        return json.loads(raw) if raw else {}

    for auth, role in [(producer, 'producer'), (reviewer, 'reviewer'), (admin, 'admin')]:
        assert request('/me', auth)['roles'] == [role]
    request('/me', expected=401)
    request('/records', producer, expected=403)
    request('/records', admin, expected=403)
    request('/me/records', reviewer, expected=403)
    print('PASS: identity, role isolation, anonymous rejection and CORS', flush=True)

    table = boto3.resource('dynamodb', region_name=region).Table(app['RecordsTableName'])
    store = DynamoRecordStore(table)
    s3 = boto3.client('s3', region_name=region)
    athena = boto3.client('athena', region_name=region)
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    created = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        for record_id, producer_id in zip(ids, producers):
            record = CompletedRecord(record_id=record_id, producer_id=producer_id,
                created_at=now, updated_at=now, closed_at=now, version=1,
                consent={'scope': 'internal', 'recorded_at': now}, language='en', entity_type='cooperative',
                summary_original='[Synthetic deployment test] Rainfall affected the harvest.',
                tags=['climate and weather'], evidence='limited', review_status='pending', pii_flag=True)
            parse_record(record.model_dump(mode='json'))
            store.create(record); created.append(record_id)
        mine = request('/me/records', producer)['records']
        assert ids[0] in {r['record_id'] for r in mine} and ids[1] not in {r['record_id'] for r in mine}
        own = next(r for r in mine if r['record_id'] == ids[0])
        assert not any(k in own for k in ['pii_flag', 'pii_matches', 'reviewed_by', 'ai_usage'])
        assert ids[0] in {r['record_id'] for r in request('/records', reviewer)['records']}
        original = request('/records/' + ids[0], reviewer)
        request('/records/' + ids[0] + '/approve', reviewer, 'POST', {'version': 1}, expected=409)
        patched = request('/records/' + ids[0], reviewer, 'PATCH', {
            'version': 1, 'reviewer_summary_original': '[Synthetic deployment test] Reviewer correction.', 'pii_review': 'cleared'})
        assert patched['version'] == 2 and patched['summary_original'] == original['summary_original']
        request('/records/' + ids[0], reviewer, 'PATCH', {'version': 1, 'pii_review': 'cleared'}, expected=409)
        approved = request('/records/' + ids[0] + '/approve', reviewer, 'POST', {'version': 2})
        assert approved['version'] == 3 and approved['review_status'] == 'reviewed'
        request('/records/' + ids[0], reviewer, 'PATCH', {'version': 3, 'pii_review': 'confirmed'}, expected=409)
        updated = next(r for r in request('/me/records', producer)['records'] if r['record_id'] == ids[0])
        assert updated['summary'] == patched['reviewer_summary_original'] and updated['changed_by_reviewer']
        print('PASS: producer scope, reviewer correction, PII gating, conflict and approval', flush=True)

        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                obj = json.loads(s3.get_object(Bucket=sync['RecordsBucketName'], Key=f'records/{ids[0]}.json')['Body'].read())
                if obj['version'] == 3 and obj['review_status'] == 'reviewed':
                    break
            except ClientError as e:
                if e.response['Error']['Code'] != 'NoSuchKey': raise
            time.sleep(2)
        else: raise AssertionError('Reviewed record did not reach S3')
        query = athena.start_query_execution(WorkGroup=sync['AthenaWorkGroup'], QueryString=
            f"SELECT version, review_status FROM fex.conversation_records WHERE record_id = '{ids[0]}'")['QueryExecutionId']
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            status = athena.get_query_execution(QueryExecutionId=query)['QueryExecution']['Status']
            if status['State'] == 'SUCCEEDED': break
            if status['State'] in ('FAILED', 'CANCELLED'): raise AssertionError(status['State'])
            time.sleep(1)
        else: raise AssertionError('Athena timed out')
        rows = athena.get_query_results(QueryExecutionId=query)['ResultSet']['Rows'][1:]
        assert [[v.get('VarCharValue') for v in r['Data']] for r in rows] == [['3', 'reviewed']]
        print('PASS: reviewer approval reached S3 and Athena', flush=True)
    finally:
        for record_id in created:
            table.delete_item(Key={'record_id': record_id})
        deadline = time.monotonic() + 90
        pending = set(created)
        while pending and time.monotonic() < deadline:
            for record_id in list(pending):
                try: s3.head_object(Bucket=sync['RecordsBucketName'], Key=f'records/{record_id}.json')
                except ClientError as e:
                    if e.response['Error']['Code'] in ('404', 'NoSuchKey'): pending.remove(record_id)
                    else: raise
            if pending: time.sleep(2)
        assert not pending, f'Synthetic S3 records still present: {pending}'
        print('Cleaned up synthetic records: ' + ', '.join(created), flush=True)


if __name__ == '__main__':
    main()
