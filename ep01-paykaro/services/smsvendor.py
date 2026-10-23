"""A mock SMS vendor. PayKaro's account has one shared quota per minute; past it, every message
gets 429 until the minute rolls over, login codes and resends alike. Accepted messages are handed
to the telecom carrier for delivery.
"""
import os
import threading
import time

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

QUOTA_PER_MIN = int(os.environ.get("SMS_QUOTA_PER_MIN", "90"))
# Thursday's fix for the vendor account: resends get their own per-minute quota (0 = shared with logins).
RESEND_QUOTA_PER_MIN = int(os.environ.get("SMS_RESEND_QUOTA_PER_MIN", "0"))
CARRIER_URL = os.environ["CARRIER_URL"]
app = FastAPI()
lock = threading.Lock()
window = {"minute": 0, "used": 0, "resend_used": 0}
totals = {"accepted": 0, "rejected": 0, "rejected_login": 0, "rejected_resend": 0}


class Message(BaseModel):
    to: str
    text: str
    reason: str = "login"
    queued_ms: int = 0


@app.post("/v1/messages")
def send(msg: Message):
    with lock:
        minute = int(time.time() // 60)
        if window["minute"] != minute:
            window.update(minute=minute, used=0, resend_used=0)
        bucket, limit = ("resend_used", RESEND_QUOTA_PER_MIN) if RESEND_QUOTA_PER_MIN and msg.reason == "resend" \
            else ("used", QUOTA_PER_MIN)
        if window[bucket] >= limit:
            totals["rejected"] += 1
            totals["rejected_resend" if msg.reason == "resend" else "rejected_login"] += 1
            raise HTTPException(429, "quota exceeded for account paykaro")
        window[bucket] += 1
        totals["accepted"] += 1
    httpx.post(f"{CARRIER_URL}/deliver", json={"to": msg.to, "text": msg.text, "reason": msg.reason}, timeout=5)
    return {"status": "accepted"}


@app.get("/account")
def account():
    return {"quota_per_min": QUOTA_PER_MIN, "used_this_minute": window["used"], **totals}
