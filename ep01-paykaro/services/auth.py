"""PayKaro auth: owns accounts and asks otp-service to send login codes."""
import os

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

OTP_URL = os.environ["OTP_URL"]
app = FastAPI()


class OtpRequest(BaseModel):
    phone: str


@app.post("/otp")
def request_otp(body: OtpRequest):
    r = httpx.post(f"{OTP_URL}/send", json={"phone": body.phone, "reason": "login"}, timeout=10)
    r.raise_for_status()
    return r.json()


@app.get("/account/{phone}")
def account(phone: str):
    # Every phone in the lab is a real, active customer.
    return {"phone": phone, "status": "active", "kyc": "done"}
