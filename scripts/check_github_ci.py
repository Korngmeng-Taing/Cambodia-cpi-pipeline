import json
import urllib.request

req = urllib.request.Request(
    'https://api.github.com/repos/Korngmeng-Taing/Cambodia-cpi-pipeline/actions/runs',
    headers={'User-Agent': 'Python-Diagnostic'}
)

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        runs = data.get('workflow_runs', [])
        for r in runs[:3]:
            print(f"RUN ID: {r['id']} | SHA: {r['head_sha'][:7]} | STATUS: {r['status']} | CONCLUSION: {r['conclusion']}")
            jobs_req = urllib.request.Request(r['jobs_url'], headers={'User-Agent': 'Python-Diagnostic'})
            with urllib.request.urlopen(jobs_req) as jresp:
                jdata = json.loads(jresp.read().decode('utf-8'))
                for j in jdata.get('jobs', []):
                    print(f"  --> JOB: {j['name']} ({j['status']}, conclusion={j['conclusion']})")
                    for s in j.get('steps', []):
                        if s.get('conclusion') == 'failure' or s.get('status') == 'in_progress':
                            print(f"      STEP: {s['name']} -> {s.get('status')} / {s.get('conclusion')}")
except Exception as e:
    print("Failed to query GitHub:", e)
