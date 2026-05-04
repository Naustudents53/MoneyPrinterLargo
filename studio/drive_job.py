"""
End-to-end driver that exercises the SAME endpoints the dashboard wizard
hits. Used to prove the pipeline works without requiring a human to
click through the UI.

Steps:
  1. POST /api/jobs                            (ConfigStage)
  2. wait_gate("script") + POST /continue       (ScriptStage)
  3. wait_gate("prompts") + POST /continue      (ImagesStage)
  4. wait_gate("thumbnail") + POST /continue    (ThumbnailStage)
  5. wait_gate("narration") + POST /continue    (NarrationStage)
  6. wait until render done                     (RenderStage)
  7. POST /api/jobs/{id}/upload                  (UploadStage)
  8. wait until upload done, print final URL
"""

import json
import sys
import time

import requests


API = "http://localhost:8000"
ACCOUNT_ID = "f574b4d3-1e23-4d2b-b594-6586769c9d24"  # Savirox
TOPIC = "Las primeras imágenes del telescopio James Webb"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wait_gate(job_id, expected_stage, timeout_s=900):
    deadline = time.time() + timeout_s
    last_status = ""
    while time.time() < deadline:
        gate = requests.get(f"{API}/api/jobs/{job_id}/gate", timeout=10).json()
        awaiting = gate.get("awaiting")
        if awaiting == expected_stage:
            return True
        # Also detect terminal failure
        job = requests.get(f"{API}/api/jobs/{job_id}", timeout=10).json()
        status = job.get("status", "")
        if status in ("error", "cancelled", "done"):
            log(f"  job ended early: status={status}")
            return False
        if status != last_status:
            log(f"  ...status={status}, awaiting={awaiting or '-'}")
            last_status = status
        time.sleep(5)
    log(f"  TIMEOUT waiting for gate '{expected_stage}'")
    return False


def post_continue(job_id, stage, payload=None):
    r = requests.post(
        f"{API}/api/jobs/{job_id}/continue",
        json={"stage": stage, "payload": payload or {}},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def get_artifact_text(job_id, key):
    r = requests.get(f"{API}/api/jobs/{job_id}/artifact/{key}", timeout=15)
    r.raise_for_status()
    return r.json()


def main():
    # --- 1. create job (ConfigStage equivalent) -------------------------
    log("[1/8] Creating job (POST /api/jobs)...")
    r = requests.post(f"{API}/api/jobs", json={
        "type": "short",
        "topic": TOPIC,
        "account_id": ACCOUNT_ID,
        "image_mode": "ai",
    }, timeout=10)
    r.raise_for_status()
    job_id = r.json()["job_id"]
    log(f"      job_id = {job_id}")

    # --- 2. wait for script gate ---------------------------------------
    log("[2/8] Waiting for script gate (LLM is generating the script)...")
    if not wait_gate(job_id, "script", timeout_s=600):
        log("FAILED at script gate")
        return 1
    script = get_artifact_text(job_id, "script")
    log(f"      script ready: {len(script['script'])} chars, {len(script['sections'])} sections")
    log("      releasing gate (no edits — keeping LLM output as-is)")
    post_continue(job_id, "script", {"script": script["script"]})

    # --- 3. wait for prompts gate --------------------------------------
    log("[3/8] Waiting for prompts gate (metadata + image prompts)...")
    if not wait_gate(job_id, "prompts", timeout_s=300):
        log("FAILED at prompts gate")
        return 1
    prompts_data = get_artifact_text(job_id, "prompts")
    prompts = prompts_data.get("prompts") if isinstance(prompts_data, dict) else prompts_data
    log(f"      prompts ready: {len(prompts)} image prompts")
    log("      releasing gate")
    post_continue(job_id, "prompts", {"prompts": prompts})

    # --- 4. wait for thumbnail gate -------------------------------------
    log("[4/8] Waiting for thumbnail gate (images + thumbnail being generated)...")
    if not wait_gate(job_id, "thumbnail", timeout_s=900):
        log("FAILED at thumbnail gate")
        return 1
    log("      thumbnail ready, releasing gate")
    post_continue(job_id, "thumbnail", {})

    # --- 5. wait for narration gate -------------------------------------
    log("[5/8] Waiting for narration gate (TTS being generated)...")
    if not wait_gate(job_id, "narration", timeout_s=300):
        log("FAILED at narration gate")
        return 1
    log("      narration ready, releasing gate")
    post_continue(job_id, "narration", {})

    # --- 6. wait for render done ----------------------------------------
    log("[6/8] Waiting for render to complete...")
    deadline = time.time() + 600
    while time.time() < deadline:
        job = requests.get(f"{API}/api/jobs/{job_id}", timeout=10).json()
        status = job.get("status", "")
        if status == "done":
            log(f"      render done. artifacts: {list(job.get('artifacts', {}).keys())}")
            break
        if status in ("error", "cancelled"):
            log(f"      render ended badly: {status}")
            return 1
        time.sleep(5)
    else:
        log("      TIMEOUT waiting for render")
        return 1

    # --- 7. trigger upload ----------------------------------------------
    log("[7/8] Triggering upload to YouTube via Selenium...")
    r = requests.post(
        f"{API}/api/jobs/{job_id}/upload",
        json={"confirm": True, "account_id": ACCOUNT_ID},
        timeout=30,
    )
    r.raise_for_status()
    log(f"      upload started: {r.json()}")

    # --- 8. wait for upload done ----------------------------------------
    log("[8/8] Waiting for upload to finish (this can take 5-30 min on YT side)...")
    deadline = time.time() + 2400  # 40 min cap
    last_msg = ""
    final_url = None
    while time.time() < deadline:
        job = requests.get(f"{API}/api/jobs/{job_id}", timeout=10).json()
        status = job.get("status", "")
        if status == "done":
            log("      upload done.")
            # Try to fetch the final URL via the SSE replay (quick scan)
            artifacts = job.get("artifacts", {})
            if artifacts.get("upload_url"):
                final_url = artifacts["upload_url"]
            break
        if status == "error":
            log("      upload failed.")
            return 1
        time.sleep(10)
    else:
        log("      TIMEOUT waiting for upload")
        return 1

    log("=" * 60)
    log("SUCCESS — pipeline complete")
    log(f"  job_id: {job_id}")
    if final_url:
        log(f"  YouTube URL: {final_url}")
    else:
        log("  (URL not in artifacts dict — check YT Studio manually)")
    log("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
