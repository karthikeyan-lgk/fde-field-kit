"""The telecom carrier: delivers SMS to phones. Outside PayKaro and outside OBI's view.

GET /inbox/{phone} plays the user's phone: the messages that actually arrived.
"""
import time
from collections import defaultdict

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
inbox: dict[str, list[dict]] = defaultdict(list)


class Sms(BaseModel):
    to: str
    text: str
    reason: str = "login"


@app.post("/deliver")
def deliver(sms: Sms):
    inbox[sms.to].append({"text": sms.text, "reason": sms.reason, "at": time.time()})
    return {"status": "delivered"}


@app.get("/inbox/{phone}")
def phone_inbox(phone: str, since: float = 0):
    return [m for m in inbox.get(phone, []) if m["at"] >= since]
