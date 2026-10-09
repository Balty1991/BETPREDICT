#!/usr/bin/env python3
"""Trimite mesajul FCM „verifică acum” către toate telefoanele (subiectul bp_all).

Folosit de .github/workflows/push-notify.yml după fiecare rulare reușită a pipeline-ului.
Mesajul e doar de date (fără text): aplicația face imediat verificarea obișnuită (Checker) și
afișează notificările după preferințele utilizatorului. Nimic personal nu trece prin server.

Variabile: FIREBASE_SERVICE_ACCOUNT (JSON-ul contului de serviciu, din secrete), PUSH_KIND (implicit „refresh”).
"""
import json
import os
import sys
import time

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip()
if not raw:
    print("FIREBASE_SERVICE_ACCOUNT lipsește: nu trimit nimic.")
    sys.exit(0)

info = json.loads(raw)
creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
creds.refresh(Request())
project = info["project_id"]
kind = os.environ.get("PUSH_KIND", "refresh")
body = {
    "message": {
        "topic": "bp_all",
        "data": {"kind": kind, "sent_at": str(int(time.time())), "run": os.environ.get("GITHUB_RUN_ID", "")},
        # prioritate mare: telefonul se trezește din Doze ca să verifice imediat; expiră după o oră
        "android": {"priority": "HIGH", "ttl": "3600s", "collapse_key": "bp_refresh"},
    }
}
r = requests.post(
    f"https://fcm.googleapis.com/v1/projects/{project}/messages:send",
    headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
    data=json.dumps(body),
    timeout=30,
)
print(r.status_code, r.text[:500])
r.raise_for_status()
