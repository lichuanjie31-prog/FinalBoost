"""Exit nonzero on unavailable or unhealthy HTTP service."""
import json
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1] + '/api/v1/health', timeout=2) as response:
        body = json.load(response)
        if response.status != 200 or body['data']['status'] != 'ok': raise ValueError('unhealthy service')
    print('HEALTH CHECK PASS')
except Exception as exc:
    print('HEALTH CHECK FAIL: ' + type(exc).__name__)
    sys.exit(1)
