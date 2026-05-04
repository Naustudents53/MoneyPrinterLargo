import sys, os
# replicate what api_server.py does
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
for p in (SRC_DIR, ROOT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import json

sys.path[0] = ROOT_DIR

from studio.runners import run_short_job

job_id = "manual-test-1"
cfg = {
    "type": "short",
    "account_id": "f574b4d3-1e23-4d2b-b594-6586769c9d24",
    "topic": "El Sol",
    "voice_id": "es-ES-AlvaroNeural",
    "image_mode": "ai",
    "image_style": "",
}

events = []
statuses = {}
artifacts = {}

def emit(jid, ev):
    events.append(ev)
    print(f"[{ev.get('stage','_')}] {ev.get('type')} - {ev.get('message','')[:80]}")

def set_status(jid, st):
    statuses[jid] = st
    print(f"STATUS -> {st}")

def set_artifact(jid, key, path):
    artifacts.setdefault(jid, {})[key] = path
    print(f"ARTIFACT {key} = {path}")

def get_status(jid):
    return statuses.get(jid)

try:
    run_short_job(
        job_id, cfg, emit, set_status, set_artifact, get_status
    )
except Exception as e:
    import traceback
    traceback.print_exc()
