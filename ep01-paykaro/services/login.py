"""PayKaro app: the login screen. Asks auth for an OTP and tells the user it's on its way."""
import os

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

AUTH_URL = os.environ["AUTH_URL"]
app = FastAPI()


class Login(BaseModel):
    phone: str


@app.post("/login")
def login(body: Login):
    r = httpx.post(f"{AUTH_URL}/otp", json={"phone": body.phone}, timeout=10)
    r.raise_for_status()
    return {"phone": body.phone, "status": "otp_requested"}
