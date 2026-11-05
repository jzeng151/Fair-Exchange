"""Check deployed analytics authorization and both views without printing passcodes."""
import argparse
import json
import subprocess
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', required=True)
    parser.add_argument('--admin-secret-arn', required=True)
    args = parser.parse_args()
    url = args.api.rstrip('/') + '/analytics'

    def request(query='', headers=None):
        req = urllib.request.Request(url + query, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, None

    status, _ = request()
    if status != 401:
        raise SystemExit(f'FAIL: anonymous analytics returned {status}, expected 401')
    secret = json.loads(subprocess.check_output([
        'aws', 'secretsmanager', 'get-secret-value', '--secret-id',
        args.admin_secret_arn, '--output', 'json', '--no-cli-pager',
    ], text=True))['SecretString']
    for pending in ('false', 'true'):
        status, body = request('?include_pending=' + pending, {'x-demo-admin-passcode': secret})
        if status != 200 or not isinstance(body, dict):
            raise SystemExit(f'FAIL: authenticated analytics include_pending={pending} returned {status}, expected 200 JSON')
        print(f'PASS: authenticated analytics include_pending={pending} returned 200')
    print('PASS: anonymous analytics rejected with 401')


if __name__ == '__main__':
    main()
