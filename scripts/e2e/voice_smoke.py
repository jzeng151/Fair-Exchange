"""Transcribe a synthetic Spanish recording through the deployed voice API.

cd agent && uv run python ../scripts/e2e/voice_smoke.py --audio /tmp/synthetic.mp4
Needs operator AWS credentials; never prints passcodes, presigned forms or transcripts.
Creates an isolated conversation without invoking FEX and deletes only its test items.
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True)
    args = parser.parse_args()
    audio = Path(args.audio)
    content_type = 'audio/mp4' if audio.suffix == '.mp4' else 'audio/webm'
    region = os.environ.get('AWS_REGION', 'us-west-2')
    session = boto3.Session(region_name=region)
    assert session.client('sts').get_caller_identity()['Account'] == os.environ['EXPECTED_AWS_ACCOUNT']
    cf = session.client('cloudformation')
    app = {o['OutputKey']: o['OutputValue'] for o in cf.describe_stacks(StackName='FairExchange')['Stacks'][0]['Outputs']}
    secret = session.client('secretsmanager').get_secret_value(SecretId=app['DemoPasscodeSecretArn'])['SecretString']
    scenarios = Path(__file__).resolve().parents[2] / 'eval/scenarios'
    producers = sorted({json.loads(p.read_text())['producer_id'] for p in scenarios.glob('*.json')})
    cid = str(uuid.uuid4())
    voices = []
    ddb = session.resource('dynamodb')
    conversations = ddb.Table(app['ConversationsTableName'])
    voice_table = ddb.Table(app['VoiceTableName'])
    s3 = session.client('s3')
    base = app['ApiUrl'].rstrip('/') + f'/conversations/{cid}/voice'

    def request(method, path='', body=None, producer=producers[0], expected=200):
        time.sleep(.3)
        req = urllib.request.Request(base + path, method=method, headers={
            'content-type': 'application/json', 'x-demo-passcode': secret,
            'x-demo-producer-id': producer, 'Origin': app['WebUrl'],
        }, data=None if body is None else json.dumps(body).encode())
        try:
            response = urllib.request.urlopen(req, timeout=35)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            raw = response.read()
            assert response.code == expected, f'{method} {path}: expected {expected}, got {response.code}'
            assert response.headers.get('Access-Control-Allow-Origin') == app['WebUrl']
        return json.loads(raw)

    try:
        now = int(time.time() * 1000)
        conversations.put_item(Item={'conversation_id': cid, 'producer_id': producers[0], 'created_at': now,
            'last_activity_at': now, 'status': 'open', 'language': 'es'}, ConditionExpression='attribute_not_exists(conversation_id)')
        created = request('POST', body={'content_type': content_type}, expected=201)
        vid = created['voice_id']; voices.append(vid)
        for method, path in [('GET', f'/{vid}'), ('DELETE', f'/{vid}'), ('POST', f'/{vid}/transcribe'), ('POST', '')]:
            request(method, path, body={} if method == 'POST' else None, producer=producers[1], expected=404)
        print('PASS: voice ownership and CORS', flush=True)
        boundary = 'fex' + uuid.uuid4().hex
        parts = []
        for name, value in created['upload']['fields'].items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic{audio.suffix}"\r\nContent-Type: {content_type}\r\n\r\n'.encode(), audio.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
        upload = urllib.request.Request(created['upload']['url'], method='POST', data=b''.join(parts),
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        with urllib.request.urlopen(upload, timeout=45) as response:
            assert response.status in [200, 201, 204]
        audio_key = created['upload']['fields']['key']
        assert s3.head_object(Bucket=app['VoiceBucketName'], Key=audio_key)['ServerSideEncryption'] == 'aws:kms'
        request('POST', f'/{vid}/transcribe', {}, expected=202)
        # Deliberately do not poll the API: completion and cleanup must work with no browser.
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            item = voice_table.get_item(Key={'voice_id': vid}, ConsistentRead=True)['Item']
            if item['status'] == 'done': break
            assert item['status'] == 'pending', 'Voice job failed'
            time.sleep(2)
        else: raise AssertionError('EventBridge completion timed out')
        assert item.get('transcript') and item.get('transcript_english')
        assert any(word in item['transcript'].lower() for word in ['lluvia', 'café', 'cosecha']), 'Unexpected Spanish transcript'
        print('PASS: real Transcribe and English translation completed without browser polling', flush=True)
        for object_key in [audio_key, f'transcripts/{vid}.json']:
            for _ in range(15):
                try: s3.head_object(Bucket=app['VoiceBucketName'], Key=object_key)
                except ClientError as e:
                    if e.response['Error']['Code'] in ['404', 'NoSuchKey']: break
                    raise
                time.sleep(1)
            else: raise AssertionError('Audio/raw transcript not cleaned up')
        result = request('GET', f'/{vid}')
        assert result['status'] == 'done' and result.get('transcript') and result.get('transcript_english')
        assert request('GET', f'/{vid}') == {'status': 'delivered'}
        item = voice_table.get_item(Key={'voice_id': vid}, ConsistentRead=True)['Item']
        assert 'transcript' not in item and 'transcript_english' not in item
        print('PASS: one-time delivery, both transcript fields consumed, audio/raw output deleted', flush=True)
        cancelled = request('POST', body={'content_type': content_type}, expected=201)['voice_id']; voices.append(cancelled)
        request('DELETE', f'/{cancelled}')
        request('POST', f'/{cancelled}/transcribe', {}, expected=409)
        voice_table.update_item(Key={'voice_id': vid}, UpdateExpression='SET expires_at = :past', ExpressionAttributeValues={':past': int(time.time()) - 1})
        request('GET', f'/{vid}', expected=404)
        conversations.update_item(Key={'conversation_id': cid}, UpdateExpression='SET #s = :closed',
            ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':closed': 'closed'})
        request('POST', body={'content_type': content_type}, expected=409)
        print('PASS: cancellation, expiry and closed-conversation rejection', flush=True)
    finally:
        # If a job is still running, retain a cancelled tombstone until TTL so its worker discards the result.
        for vid in voices:
            item = voice_table.get_item(Key={'voice_id': vid}, ConsistentRead=True).get('Item')
            if item:
                for object_key in [item['audio_key'], item['output_key']]:
                    s3.delete_object(Bucket=app['VoiceBucketName'], Key=object_key)
                if item['status'] == 'pending' and item.get('started'):
                    voice_table.update_item(Key={'voice_id': vid}, UpdateExpression='SET #s = :cancelled REMOVE transcript, transcript_english',
                        ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':cancelled': 'cancelled'})
                else: voice_table.delete_item(Key={'voice_id': vid})
        conversations.delete_item(Key={'conversation_id': cid})
        print('Cleaned up synthetic voice conversation ' + cid, flush=True)


if __name__ == '__main__':
    main()
