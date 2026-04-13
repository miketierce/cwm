"""
Shared Firestore submission helpers for CWM plate experiment tools.

Provides anonymous Firebase auth and experiment result submission
to the CWM Lab site API.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

FIREBASE_API_KEY = "AIzaSyCxlNaRNwwOim4-bSYL7MrRuQmDBznlga0"
CWM_SITE_URL = "https://coherent-wave-memory.web.app"


def firebase_anon_auth() -> str:
    """Get an anonymous Firebase ID token."""
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
        f"?key={FIREBASE_API_KEY}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"returnSecureToken": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return resp["idToken"]


def submit_experiment(token: str, experiment_id: str, data: dict,
                      nickname: str = "Mike", notes: str = "") -> dict:
    """Submit one experiment result to Firestore via cwm-site API.

    Auto-refreshes the auth token on 401 and retries once.
    """
    payload = {
        "experimentId": experiment_id,
        "data": data,
        "nickname": nickname or None,
        "notes": notes or None,
    }

    def _do_submit(tk: str) -> dict:
        req = urllib.request.Request(
            f"{CWM_SITE_URL}/api/submit-experiment",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {tk}",
            },
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return {"ok": True, "id": resp.get("id"), "experimentId": experiment_id}

    try:
        return _do_submit(token)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token expired — get a fresh one and retry
            try:
                fresh = firebase_anon_auth()
                return _do_submit(fresh)
            except Exception as e2:
                return {"ok": False, "error": str(e2),
                        "experimentId": experiment_id}
        body = e.read().decode() if e.fp else str(e)
        return {"ok": False, "error": body, "status": e.code,
                "experimentId": experiment_id}
    except Exception as e:
        return {"ok": False, "error": str(e), "experimentId": experiment_id}


def print_result(r: dict) -> None:
    """Print a submission result with error details if failed."""
    if r.get("ok"):
        print(f"  ✓ Submitted → {r.get('id', '?')}")
    else:
        error = r.get("error", "unknown")
        if isinstance(error, str):
            try:
                parsed = json.loads(error)
                error = parsed.get("statusMessage", error)
            except (json.JSONDecodeError, AttributeError):
                pass
        print(f"  ✗ Failed: {error}")
