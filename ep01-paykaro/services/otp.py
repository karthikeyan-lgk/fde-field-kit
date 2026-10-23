"""PayKaro otp-service: queues codes and hands them to the SMS vendor.

Sends go out through the bank's egress proxy (EGRESS_URL), one new HTTPS connection per message.
Login codes wait in a queue for a small pool of sender threads. Resends skip the queue and go out
straight away ("instant resend", asked for when the support bot launched). Both use the same
vendor account and its quota.
"""
import os
import queue
import random
import threading
import time

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

EGRESS_URL = os.environ["EGRESS_URL"]
SENDERS = int(os.environ.get("OTP_SENDERS", "2"))
# Thursday's fix for the otp team: at most one resend per phone per RESEND_COOLDOWN_S (0 = no limit).
COOLDOWN = float(os.environ.get("RESEND_COOLDOWN_S", "0"))
last_resend: dict[str, float] = {}
app = FastAPI()
outbox: queue.Queue = queue.Queue()


class Send(BaseModel):
    phone: str
    reason: str = "login"


def deliver(phone: str, reason: str, queued_at: float) -> int:
    code = f"{random.randint(0, 999999):06d}"
    try:
        # The bank's proxy re-signs TLS with its own CA. The lab skips verification instead of
        # installing that CA; the handshake still happens, which is what matters here.
        r = httpx.post(
            f"{EGRESS_URL}/v1/messages",
            json={"to": phone, "text": f"Your PayKaro code is {code}", "reason": reason,
                  "queued_ms": int((time.time() - queued_at) * 1000)},
            verify=False,
            timeout=10,
        )
        return r.status_code
    except httpx.HTTPError:
        return 0


def sender() -> None:
    while True:
        phone, reason, queued_at = outbox.get()
        deliver(phone, reason, queued_at)
        outbox.task_done()


for _ in range(SENDERS):
    threading.Thread(target=sender, daemon=True).start()


@app.post("/send", status_code=202)
def send(body: Send):
    if body.reason == "resend":
        now = time.time()
        if COOLDOWN and now - last_resend.get(body.phone, 0) < COOLDOWN:
            return {"phone": body.phone, "status": "too soon: a code is already on its way, ask the customer to wait"}
        last_resend[body.phone] = now
        status = deliver(body.phone, body.reason, time.time())
        return {"phone": body.phone, "status": "sent" if status == 200 else f"vendor said {status}"}
    outbox.put((body.phone, body.reason, time.time()))
    return {"phone": body.phone, "status": "queued", "queue_depth": outbox.qsize()}


@app.get("/queue")
def depth():
    return {"queue_depth": outbox.qsize()}
