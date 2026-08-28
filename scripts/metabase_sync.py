import os
import urllib.request, json, sys

port = os.environ.get("METABASE_PORT", "3001")
base_url = f"http://localhost:{port}"

# Get session token
session_data = json.dumps({'username': 'admin@metabase.local', 'password': 'P@ssw0rd!'}).encode()
req = urllib.request.Request(f'{base_url}/api/session', data=session_data, headers={'Content-Type': 'application/json'})
try:
    resp = urllib.request.urlopen(req)
    token = json.loads(resp.read())['id']
    print(f"Session token: {token}")
except Exception as e:
    print(f"Session error: {e}")
    sys.exit(1)

# Trigger schema sync
headers = {'Content-Type': 'application/json', 'X-Metabase-Session': token}
req2 = urllib.request.Request(f'{base_url}/api/database/2/sync_schema', headers=headers, method='POST')
try:
    resp2 = urllib.request.urlopen(req2)
    print(f"Sync response: {resp2.status}")
except urllib.error.HTTPError as e:
    print(f"Sync error: {e.code} {e.read().decode()}")
    sys.exit(1)

print("Database sync triggered successfully!")
